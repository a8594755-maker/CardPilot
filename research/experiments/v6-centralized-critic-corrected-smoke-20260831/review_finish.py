"""Independent review using the preregistered CTDE raw-evidence reviewer."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "research/experiments/v6-centralized-critic-matched-smoke-20260831/review_finish.py"
spec = importlib.util.spec_from_file_location("ctde_smoke_parent_reviewer", SOURCE)
impl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impl)


def main():
    impl.main()


if __name__ == "__main__":
    main()
