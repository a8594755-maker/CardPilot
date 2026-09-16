import torch
import torch.nn as nn
import numpy as np
from typing import Generator, Any, List, Tuple, Dict, Callable
import time

# Import your existing game components
from .game_state import HUNLGameState, LeducGameState, Action, ActionType
from .encoding import HUNLEncoder, LeducEncoder, encode_legal_mask_from_actions, actions_to_slots
from .reservoir import ReservoirBuffer, AdvantageSample

class BatchedTraversalAgent:
    """
    Manages multiple parallel game traversals (coroutines) to maximize GPU throughput.
    
    Architecture:
    - N 'workers' (generators), each running a single MCCFR traversal.
    - When a worker needs an NN evaluation, it yields the state.
    - The main loop collects yielded states from all workers.
    - Batches them into a single GPU forward pass.
    - Sends advantages back to workers to resume them.
    """
    
    def __init__(
        self, 
        game_cls: type, 
        encoder_cls: type,
        models: List[nn.Module], 
        device: torch.device,
        batch_size: int = 1024,
        max_actions: int = 6,
        is_leduc: bool = False
    ):
        self.game_cls = game_cls
        self.encoder_cls = encoder_cls
        self.models = models  # [p0_model, p1_model]
        self.device = device
        self.batch_size = batch_size
        self.max_actions = max_actions
        self.is_leduc = is_leduc
        
    def traverse_batch(
        self,
        num_traversals: int,
        traverser: int,
        iteration: int,
        adv_buffer: ReservoirBuffer,
        game_config_factory: Callable = None
    ) -> float:
        """
        Execute `num_traversals` in batches.
        Returns average EV.
        """
        # Pool of active generators
        active_workers: List[Generator] = []
        
        # Stats
        total_ev = 0.0
        finished_traversals = 0
        
        # Fill the pool initially
        # We process 'batch_size' games in parallel
        # Note: 'batch_size' here is the concurrency level (N workers)
        # Ideally, N should be large enough to saturate GPU (e.g., 512-4096)
        
        current_iter_count = 0
        
        def create_worker():
            if self.is_leduc:
                state = self.game_cls().deal_new_hand()
                return self._traverse_recursive(state, traverser, iteration, adv_buffer)
            else:
                config = game_config_factory() if game_config_factory else None
                state = self.game_cls(config).deal_new_hand()
                return self._traverse_recursive(state, traverser, iteration, adv_buffer)

        # Initial population
        while len(active_workers) < self.batch_size and current_iter_count < num_traversals:
            active_workers.append(create_worker())
            current_iter_count += 1
            
        while active_workers:
            # 1. Advance all workers to their next yield point
            #    We separate them into those needing P0 eval, P1 eval, or finished.
            
            p0_eval_requests = []  # List of (worker_idx, state_encoding, legal_mask, slots)
            p1_eval_requests = []
            
            completed_indices = []
            
            # Temporary list to rebuild active_workers
            still_active_workers = []
            
            for i, worker in enumerate(active_workers):
                try:
                    # Resume worker. If it's just starting, send None.
                    # If it yielded last time, we would have sent the result back then.
                    # But here, we are assuming we handle the 'send' logic after batch inference.
                    # Wait, standard generator usage:
                    # val = next(w) -> runs to yield -> returns yielded value
                    # w.send(result) -> returns next yielded value
                    
                    # We need to track what each worker is waiting for.
                    # Actually, we can just process them in the batching block below.
                    pass
                except StopIteration as e:
                    # Worker finished, e.value is the EV
                    total_ev += e.value
                    finished_traversals += 1
                    
                    # Replace with new worker if needed
                    if current_iter_count < num_traversals:
                        active_workers[i] = create_worker()
                        current_iter_count += 1
                        # Mark as "needs start" - implied by being a fresh generator
                    else:
                        completed_indices.append(i)
            
            # Prune completed workers (in reverse order to keep indices valid)
            for idx in sorted(completed_indices, reverse=True):
                active_workers.pop(idx)
                
            if not active_workers:
                break
                
            # Run the batch step
            self._step_batch(active_workers, p0_eval_requests, p1_eval_requests)
            
        return total_ev / max(1, finished_traversals)

    def _step_batch(self, workers, p0_reqs, p1_reqs):
        """
        Advance all workers. Collect evaluation requests. Batch evaluate. Send results back.
        This is a bit tricky: some workers are 'fresh', some are 'waiting for value'.
        We store the 'next_send_value' alongside the worker?
        
        Better approach:
        The 'workers' list contains Generators that are currently PAUSED at a `yield` statement.
        The `yield` statement returned a Request object (e.g. "Evaluate this state for P0").
        
        Wait, we need to store the state of the batch loop.
        Let's refactor: `traverse_batch` manages the loop.
        """
        pass # Replaced by logic in traverse_batch_v2 for clarity

    def traverse_batch_v2(
        self,
        num_traversals: int,
        traverser: int,
        iteration: int,
        adv_buffer: ReservoirBuffer,
        game_config_factory: Callable = None
    ) -> float:
        
        total_ev = 0.0
        finished_count = 0
        
        # worker_state: (generator, last_yielded_value)
        # If last_yielded_value is ('eval', p, state, mask), we need to send advantages.
        # If last_yielded_value is None (fresh), we iterate with next().
        
        workers = []
        worker_requests = [] # Parallel list to workers
        
        next_traversal_idx = 0
        
        # Fill pool
        while len(workers) < self.batch_size and next_traversal_idx < num_traversals:
            if self.is_leduc:
                state = self.game_cls().deal_new_hand()
            else:
                config = game_config_factory() if game_config_factory else None
                state = self.game_cls(config).deal_new_hand()
            
            gen = self._traverse_recursive(state, traverser, iteration, adv_buffer)
            workers.append(gen)
            worker_requests.append(None) # None means "just start/resume without input"
            next_traversal_idx += 1
            
        while workers:
            # 1. Collect inputs for the batch (P0 and P1)
            p0_inputs = {'states': [], 'masks': [], 'indices': []}
            p1_inputs = {'states': [], 'masks': [], 'indices': []}
            
            # Indices of workers that finished this step
            finished_indices = []
            
            # Iterate over all workers
            for i in range(len(workers)):
                gen = workers[i]
                req = worker_requests[i]
                
                try:
                    # Resume generator
                    if req is None:
                        # First run or resume without data
                        response = next(gen)
                    else:
                        # Resume with advantages
                        response = gen.send(req)
                        
                    # Handle response
                    # Expected response: ('eval', player_id, raw_state, legal_mask)
                    tag, pid, raw, mask = response
                    
                    if tag == 'eval':
                        # Queue for batch inference
                        if pid == 0:
                            target = p0_inputs
                        else:
                            target = p1_inputs
                            
                        target['states'].append(raw)
                        target['masks'].append(mask)
                        target['indices'].append(i) # Remember who asked
                        
                        # Clear request for now, will be filled after inference
                        worker_requests[i] = 'WAITING' 
                        
                except StopIteration as e:
                    # Worker finished
                    total_ev += e.value
                    finished_count += 1
                    finished_indices.append(i)
            
            # 2. Refill pool with new workers at the slots of finished ones
            # (To maintain high batch size)
            for i in finished_indices:
                if next_traversal_idx < num_traversals:
                    if self.is_leduc:
                        state = self.game_cls().deal_new_hand()
                    else:
                        config = game_config_factory() if game_config_factory else None
                        state = self.game_cls(config).deal_new_hand()
                    
                    gen = self._traverse_recursive(state, traverser, iteration, adv_buffer)
                    workers[i] = gen
                    worker_requests[i] = None # Start fresh
                    
                    # IMMEDIATELY advance the new worker to its first yield point
                    # so it joins the current batch if possible? 
                    # Simpler to just let it catch up next loop.
                    # But we need to be careful not to overwrite a valid request if we do that?
                    # No, we just replaced the worker and request.
                    
                    # Let's just 'prime' it now to maximize utilization
                    try:
                        response = next(gen)
                        tag, pid, raw, mask = response
                        if tag == 'eval':
                             if pid == 0: target = p0_inputs
                             else: target = p1_inputs
                             target['states'].append(raw)
                             target['masks'].append(mask)
                             target['indices'].append(i)
                             worker_requests[i] = 'WAITING'
                    except StopIteration as e:
                        # Game ended immediately (unlikely but possible)
                        total_ev += e.value
                        finished_count += 1
                        workers[i] = None # Will be cleaned up
                        next_traversal_idx += 1 
                        
                else:
                    workers[i] = None # Mark for removal

            # Cleanup None workers
            workers = [w for w in workers if w is not None]
            worker_requests = [r for r in worker_requests if r is not None] # Note: 'WAITING' is not None
            
            if not workers:
                break
                
            # 3. Run Batch Inference
            self._run_inference(p0_inputs, self.models[0], worker_requests)
            self._run_inference(p1_inputs, self.models[1], worker_requests)
            
        return total_ev / max(1, finished_count)

    def _run_inference(self, inputs, model, worker_requests):
        if not inputs['states']:
            return
            
        states = np.stack(inputs['states'])
        masks = np.stack(inputs['masks'])
        indices = inputs['indices']
        
        # GPU Forward
        with torch.inference_mode():
            s_t = torch.from_numpy(states).to(self.device)
            m_t = torch.from_numpy(masks).to(self.device)
            advantages = model(s_t, m_t).cpu().numpy()
            
        # Distribute results
        for idx_in_batch, worker_idx in enumerate(indices):
            worker_requests[worker_idx] = advantages[idx_in_batch]

    def _traverse_recursive(
        self, 
        state, 
        traverser: int, 
        iteration: int, 
        adv_buffer: ReservoirBuffer
    ) -> Generator:
        """
        Coroutine version of traverse().
        Yields ('eval', player, state, mask) when it needs an advantage vector.
        Receives advantages (np.ndarray) from yield return.
        Returns EV (float).
        """
        if state.is_terminal():
            return state.payoff(traverser)

        actions = state.legal_actions()
        if not actions:
            return 0.0

        # Current player needs strategy
        # We YIELD to the manager to get advantages
        if self.is_leduc:
            raw = self.encoder_cls.encode(state)
            legal_mask = self.encoder_cls.encode_legal_mask(state, self.max_actions)
        else:
            raw = self.encoder_cls.encode(state)
            legal_mask = encode_legal_mask_from_actions(actions, self.max_actions)
            
        # --- PAUSE HERE for GPU ---
        advantages = yield ('eval', state.current_player, raw, legal_mask)
        # --- RESUME ---

        # Regret Match (CPU - cheap)
        strategy = self._regret_match(advantages, legal_mask)
        
        if self.is_leduc:
            action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
            slots = [action_slot_map[a] for a in actions]
        else:
            slots = actions_to_slots(actions)

        if state.current_player == traverser:
            # External Sampling: traverse ALL actions
            values = np.zeros(self.max_actions, dtype=np.float32)
            
            for i, action in enumerate(actions):
                child = state.apply(action)
                # Recursively yield from child
                # In Python 3.3+, yield from delegates to sub-generator
                values[slots[i]] = yield from self._traverse_recursive(child, traverser, iteration, adv_buffer)
            
            ev = np.sum(strategy * values)
            inst_advantages = (values - ev) * legal_mask
            
            # Add to buffer
            sample = AdvantageSample(
                state=raw,
                advantages=inst_advantages,
                legal_mask=legal_mask,
                iteration=iteration + 1
            )
            adv_buffer.add(sample)
            return ev
            
        else:
            # Opponent: Sample ONE action
            slot_probs = np.array([strategy[slots[i]] for i in range(len(actions))])
            sum_probs = slot_probs.sum()
            if sum_probs > 0:
                slot_probs /= sum_probs
            else:
                slot_probs = np.ones(len(actions)) / len(actions)
                
            action_idx = np.random.choice(len(actions), p=slot_probs)
            child = state.apply(actions[action_idx])
            
            return (yield from self._traverse_recursive(child, traverser, iteration, adv_buffer))

    @staticmethod
    def _regret_match(advantages: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
        # Same logic as before
        positive = np.maximum(advantages, 0) * legal_mask
        total = positive.sum()
        if total > 0:
            return positive / total
        
        # Fallback to max advantage action (approximate Nash) or Uniform
        # Using the same fix we applied in train.py
        masked = np.where(legal_mask > 0, advantages, -np.inf)
        best = np.argmax(masked)
        result = np.zeros_like(advantages)
        result[best] = 1.0
        return result
