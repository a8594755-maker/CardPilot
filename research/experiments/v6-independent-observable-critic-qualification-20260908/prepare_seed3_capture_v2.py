"""Preserve failed pre-worker capture; repair comparison container type only."""
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    variants = [
        ('derive_capture_check.py', 'derive_capture_check_v2.py',
         "{k:v for k,v in initial['model'].items() if not k.startswith(prefix)}",
         "type(parent['model'])((k,v) for k,v in initial['model'].items() if not k.startswith(prefix))"),
        ('train_capture_derivation.py', 'train_capture_derivation_v2.py',
         'from derive_capture_check import verify', 'from derive_capture_check_v2 import verify'),
        ('run_seed3.py', 'run_seed3_v2.py', "'seed3_first_capture'", "'seed3_first_capture_v2'"),
    ]
    for source, target, old, new in variants:
        text = (BASE/source).read_text()
        assert text.count(old) == 1
        text = text.replace(old, new)
        if target == 'run_seed3_v2.py':
            text = text.replace("'train_capture_derivation.py'", "'train_capture_derivation_v2.py'")
        with (BASE/target).open('x', encoding='utf-8') as handle:
            handle.write(text)


if __name__ == '__main__':
    main()
