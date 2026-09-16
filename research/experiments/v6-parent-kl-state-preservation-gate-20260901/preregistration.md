# Parent-KL outcome-free state-preservation gate

Replay candidate SHA256
`1c050edb088eaaf4bdc653a7b7b4708191854a7ca216f913ca2b7c1c6cd412c4`
and parent SHA256
`9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4`
on every decision from the parent's completed audited generic-greedy fresh5k.
The corpus contains 15,056 parent on-policy decisions and is used without hand
outcomes.  Verify every hand, checkpoint, and audit identity.

Compute candidate/parent entropy, bidirectional KL, total variation, greedy
disagreement, and probability/action-slot mixes overall and by street/seat.
Make zero network calls, new Slumbot hands, training updates, or endpoint changes.

Pass only if overall TV is at most 0.01, overall greedy disagreement at most 1%,
and every partition with at least 100 states has TV at most 0.025 and greedy
disagreement at most 5%.  These are stricter than the failed weak-KL tail's
observed TV 0.01923, disagreement 1.591%, and maximum partition TV 0.04552.
A pass admits one separate fixed fresh5k pilot; it is not strength evidence.

