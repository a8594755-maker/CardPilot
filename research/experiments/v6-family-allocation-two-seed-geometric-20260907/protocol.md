# Fixed family-allocation paired trial

One variable: flat per-snapshot hardness allocation versus conditional family
masses original=0.50, added=0.25, recent=0.25; preserve within-family ratios.
Both arms capacity9, seven identical fixed opponents plus two recent models.
The normalization changes the global per-slot floor; self-play fraction and
all learner/model/optimizer/reference/replay/execution settings remain unchanged.

Seeds1/3 start at iteration3116 original expanded roots (14,695,135 and
14,694,500 physical hands). Stratified parents differ only in allocation weights.
Never start from smoke descendants. Legacy directory label `expanded` means
stratified in this experiment; `control` means flat capacity9, NOT capacity5.
Train262144 additional physical hands, then1048576 cumulative additional hands
from each root. Count whole-iteration overshoot, no counter/replay reset.
Stage1 order S1control,S1expanded,S3expanded,S3control; stage2 reverse.
No automatic retries; preserve managed attempt namespaces and all raw prefixes.

Each stage evaluates all four endpoints against eight fixed anchors:
Standard10,CFR4,legacy_iter16,legacy_mixed65k,moving_s1,moving_s3,half_lr_s1,
half_lr_s3. Use1024 paired decks/anchor, both seats, root comparator+endpoint:
32768 executed hands/job,131072/stage,262144 total. Seed20267000+10*seed+stage,
anchor offset1000003, same decks across paired arms, fresh versus retained corpus.
Greedy physical200bb legacy_v4 observation contract, no new Slumbot hands.
The four siblings are training opponents; this is adaptation, not unseen transfer.
The original four-anchor panel is a recurring development preservation proxy.

Report stratified-minus-flat, each-minus-root, both seats and anchor groups.
Primary question: can original-panel preservation improve without losing added
family adaptation? No aggregate-only promotion. Conditional paired normal95CIs
describe fixed policies/decks, not the population of training seeds.
Continue to1M unless predeclared broad collapse (existing qualified definition)
on the preservation panel or adaptation panel of either seed. Early absolute
negative scores alone do not reject learning. Complete terminal raw/hash/command/
assignment and accounting review before closing. No automatic4M or final Slumbot
qualification; next scaling decision needs replicated breadth and curve evidence.
