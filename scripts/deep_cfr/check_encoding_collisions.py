"""Check for encoding collisions in the Leduc encoder.
Two different info sets (info_keys) should never map to the same 25-dim feature vector.
If they do, the neural network literally cannot distinguish them."""

from collections import defaultdict
import numpy as np
from scripts.deep_cfr.game_state import LeducGameState
from scripts.deep_cfr.encoding import LeducEncoder


def enumerate_all_states(state: LeducGameState, depth: int = 0):
    """Enumerate all reachable game states via DFS."""
    if state.is_terminal():
        return

    yield state

    for action in state.legal_actions():
        child = state.apply(action)
        yield from enumerate_all_states(child, depth + 1)


# Enumerate all possible deals
cards = list(range(6))
import itertools

encoding_to_infokeys: dict[str, list[str]] = defaultdict(list)
infokey_to_encoding: dict[str, np.ndarray] = {}
total_states = 0

for p0, p1, board in itertools.permutations(cards, 3):
    state = LeducGameState()
    state.hole_cards = [p0, p1]
    remaining = [c for c in cards if c not in (p0, p1, board)]
    state.deck = remaining[:2] + [board] + remaining[2:]

    for s in enumerate_all_states(state):
        info_key = s.to_info_key()
        encoding = LeducEncoder.encode(s)
        encoding_str = np.array2string(encoding, precision=6, separator=',')

        encoding_to_infokeys[encoding_str].append(info_key)
        if info_key not in infokey_to_encoding:
            infokey_to_encoding[info_key] = encoding
        total_states += 1

print(f"Total game states visited: {total_states}")
print(f"Unique info keys: {len(infokey_to_encoding)}")
print(f"Unique encodings: {len(encoding_to_infokeys)}")

# Check for collisions
collisions = 0
for enc_str, keys in encoding_to_infokeys.items():
    unique_keys = set(keys)
    if len(unique_keys) > 1:
        collisions += 1
        if collisions <= 20:  # Print first 20
            print(f"\nCOLLISION ({len(unique_keys)} info sets -> same encoding):")
            for k in sorted(unique_keys):
                print(f"  {k}")
            print(f"  Encoding: {enc_str[:80]}...")

if collisions == 0:
    print("\nNo encoding collisions found! Neural net CAN distinguish all info sets.")
else:
    print(f"\n{collisions} encoding collisions found! Neural net CANNOT distinguish some info sets.")
