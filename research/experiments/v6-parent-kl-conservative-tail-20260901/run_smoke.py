"""Parent-referenced strong-KL specialization of the reviewed tail runner."""
import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = ROOT / "research/experiments/v6-actor-low-lr-tail-20260901/run_tail.py"
TARGET = 196608
KL_COEF = ".1"


def main():
    spec = importlib.util.spec_from_file_location("optimizer_continuous_tail_engine", ENGINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = BASE
    module.TARGET_PHYSICAL = TARGET
    module.PAIRS = 1024
    original = module.training_command

    def command(frozen, run):
        values = original(frozen, run)
        values[values.index("--total-environment-hands") + 1] = str(TARGET)
        values[values.index("--source-policy-kl-coef") + 1] = KL_COEF
        values[values.index("--source-policy-reference-checkpoint") + 1] = str(frozen / "parent_raw.pt")
        return values

    module.training_command = command
    module.main()


if __name__ == "__main__":
    main()

