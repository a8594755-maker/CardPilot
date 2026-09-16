# Independent review attempt 1

The first independent review recomputed all saved-array statistics successfully,
then failed its additional 64-state endpoint-linkage assertion because that
review-only assertion required repeat inference to match at absolute tolerance
2e-7. The attempt made 64 CPU and 64 GPU model-state queries. This tolerance was
not a preregistered scientific or backend-materiality gate; no reviewed result was
written. The retry records the actual repeat-inference deltas and bounds them by
the already preregistered 1e-4 materiality scale.
