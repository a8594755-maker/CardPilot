"""Diagnostic-only fault injection; never imported by production training."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts/alpha_holdem'))


def main():
    import torch
    from scripts.alpha_holdem import train_v5_managed_candidate as trainer

    def wrap(original):
        def interrupted(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            print('DIAGNOSTIC: one actual optimizer step applied; injecting KeyboardInterrupt', flush=True)
            raise KeyboardInterrupt('intentional isolated partial-update fault')
        return interrupted
    torch.optim.Adam.step = wrap(torch.optim.Adam.step)
    torch.optim.AdamW.step = wrap(torch.optim.AdamW.step)
    trainer.main()


if __name__ == '__main__':
    main()
