# Native-sampled Standard10 pilot: infrastructure abort

Decision: **ABORTED_INFRASTRUCTURE_NONQUALIFYING**. Not a policy-strength failure or a completed20k result.

Preserved **4,168 complete raw hands**. The integrity stop was requested before inspecting interim winrate/CI. No raw row, checkpoint, session seed or frozen execution source was changed; no supplement or restart was used.

Part04 attempt127 failed to establish a new HTTPS connection(WinError10048) and was skipped. Successful hand127 is attempted hand128; the fixed2500-attempt loop could no longer reach2500successful hands. The affected owned PID was stopped after ownership verification, and the original wrapper stopped its other clients. All clients are terminal; the record retains their actual nonzero exit codes.

Exploratory subtotal only, calculated after stopping: -11.1867bb/100, naive raw95% CI [-73.8572, +51.4838]. This unplanned truncated subtotal does not satisfy the registered pilot and admits no formal100k test.

## Next

Separately log and test persistent per-process HTTP connection reuse with no automatic POST retries, plus strict immediate failure on hand/transport errors. Do not alter Windows networking settings or unrelated processes. Only after validation choose a new independently preregistered test with fresh sessions/evidence; never continue these interrupted files.

The actual connection setup failure is proven. The client uses per-call requests.post; observed TIME_WAIT churn motivates pooling. System-wide ephemeral-port exhaustion is not established. [Requests connection reuse](https://requests.readthedocs.io/en/stable/user/advanced/) and [Microsoft diagnostic guidance](https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/tcp-ip-port-exhaustion-troubleshooting) support investigating connection churn,not asserting a broader unverified cause.

Goal remains unachieved: a qualifying fixed-policy fresh100k result is still required.
