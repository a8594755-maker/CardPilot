# Independent observable critic real-worker smoke

Continue the existing qualification, not a strength test. First seed1 fixed2M
parent SHA 52501761b214aafc00caea3cba14e6d51c8f176d33c612914d6916fd939bbcf2,
then seed3 only after the first actual path is healthy. For the first attempt
target 8192 new physical executions with whole-iteration overshoot permitted and
600 seconds wall cap. No automatic retry. Preserve every failed attempt.

Use the exact parent's registered command except the new isolated wrapper and
independent-critic opt-in, run/output/registry paths, parent checkpoint, physical
target and wall bound. Remove the old wrapper's zero opponent-mixture argument:
zero had no transformation, and the same frozen ordinary inference routine is
retained. Keep 12 workers, 8 environments each, worker seeds and run ID, 4096-hand
iterations, full network, PPO2/batch16384, source current-to-reference KL1,
entropy .005/floor .05, Adam actual LR1e-4, cap9 anchor-latest pool, replay .5/2.
No reset optimizer/counters/replay/reference. The architecture derivation adds new
encoder parameters with lazy zero Adam moments; old states must remain exact.

Copy—not rewrite—the parent's complete metrics and assignment evidence prefixes
into the new attempt directory, bind their hashes, and append there. Managed
attempts generate new namespaces, hence statistical continuation, not bitwise
worker RNG or unique physical training deck proof. Freeze local candidate source
hashes before launching. The relocated LG002-only workspace lookup is outside
this run's disabled LG002 contract; it does not govern managed attempt paths.

After natural termination inspect return code, source/parent/prefix hashes,
initial/final checkpoint weights/Adam/reference/replay/counters, assignment and
metrics suffixes, actual physical hands and replay counts. Require actual new
encoder updates and all finite states. Before production also test extended-state
restart in a new namespace without losing optimizer/replay or prior evidence.
No poker-strength evaluation or Slumbot access during qualification. Passing
mechanics permits a preregistered learning curve, not a claim of stronger play.
