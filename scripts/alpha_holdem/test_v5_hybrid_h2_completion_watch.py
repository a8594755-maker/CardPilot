from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from v5_hybrid_h2_completion_watch import (
    MIRROR_LOCK_SHA,
    exact_endpoint,
    exact_protocol,
    mirror_complete,
    preserve_invalid,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        checkpoint = root / "endpoint.pt"
        checkpoint.write_bytes(b"exact")
        checkpoint_sha = hashlib.sha256(b"exact").hexdigest()
        endpoint_path = root / "endpoint.json"
        endpoint_path.write_text(json.dumps({
            "overall": "PASS",
            "state": "ARM_ENDPOINT_FROZEN",
            "arm": "treatment",
            "checkpoint_path": str(checkpoint),
            "checkpoint_sha256": checkpoint_sha,
        }), encoding="utf-8")
        assert exact_endpoint(endpoint_path, "treatment") is not None

        protocol_path = root / "protocol.json"
        protocol_path.write_text(json.dumps({
            "overall": "PASS",
            "first60": {"status": "PASS"},
        }), encoding="utf-8")
        assert exact_protocol(protocol_path, "treatment") is not None

        rows = root / "pairs.jsonl"
        rows.write_text("{}\n" * 40_000, encoding="utf-8")
        rows_sha = hashlib.sha256(rows.read_bytes()).hexdigest()
        rows.with_suffix(".summary.json").write_text(json.dumps({
            "pairs": 40_000,
            "rows_sha256": rows_sha,
            "measurement_lock_sha256": MIRROR_LOCK_SHA,
            "tool_sha256": "0e1dc76bfc8e23f0493435e520fdffa78bc9f840417067646338cdea77bf1231",
        }), encoding="utf-8")
        assert mirror_complete(rows)

        partial = root / "partial.jsonl"
        partial.write_text("partial\n", encoding="utf-8")
        preserved = preserve_invalid(partial)
        assert len(preserved) == 1 and not partial.exists() and Path(preserved[0]).exists()

        pending = root / "pending.json"
        pending.write_text(json.dumps({"overall": "PENDING"}), encoding="utf-8")
        assert exact_endpoint(pending, "control") is None

        bad = json.loads(endpoint_path.read_text(encoding="utf-8"))
        bad["checkpoint_sha256"] = "0" * 64
        endpoint_path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            exact_endpoint(endpoint_path, "treatment")
            raise AssertionError("bad checkpoint identity passed")
        except ValueError as exc:
            assert "checkpoint_identity" in str(exc)

    print("PASS 12/12 H2 completion watcher identity/resume assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
