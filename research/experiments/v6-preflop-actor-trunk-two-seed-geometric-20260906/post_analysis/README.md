# Independent milestone review, outside frozen training dependencies

No competing experiment logger writer while owner PID57824/create_time1788676494.1425543
is live. These files neither change live training sources nor select models or add
poker hands. Review and curve math are adapted from the completed LR experiment;
raw statistic/counter/Adam logic is reused, with gradient-arm/metadata checks added.

Run offline qualification once:

    python -B research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/post_analysis/qualify_review.py

Only after the exact controller and all recorded children are terminal, verify
qualification.json and its source/XML hashes, then run review.py once. It rejects
live owners before reading outcomes and refuses existing output. On a terminal
mechanics failure, preserve evidence and perform a failure-specific review instead
of forcing the successful-run reviewer. If stage1 hit the registered severe gate,
review only that completed stage; do not run the two-stage curve utility.

    python -B research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/post_analysis/review.py
    python -B research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/post_analysis/curve_comparison.py

The curve command requires two verified disjoint stages. Report both seeds, both
arms, per-anchor and relative-seat learning, preservation and realized update dose.
No automatic larger allocation, external test or qualification. After substantive
research decision, finish the SAME experiment and run its audit; logging of the
qualification, exact nested pytest argv, actual reviewer/curve commands and these
artifacts is deferred until owner exit. No one-shot duplicate reviewer is installed.
