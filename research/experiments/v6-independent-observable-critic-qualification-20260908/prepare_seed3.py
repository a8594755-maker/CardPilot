"""Exclusive mechanical capture/launcher variants; original evidence stays immutable."""
from pathlib import Path

BASE = Path(__file__).resolve().parent


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    text = (BASE / 'train_capture.py').read_text()
    start = text.index('            keys = [')
    end = text.index("            initial = args.run_dir", start)
    text = text[:start] + '            from derive_capture_check import verify\n            keys = verify(parent, payload, transfer.equal_tree)\n' + text[end:]
    with (BASE / 'train_capture_derivation.py').open('x', encoding='utf-8') as handle:
        handle.write(text)
    text = (BASE / 'run_restart.py').read_text()
    start = text.index("    parent_dir = BASE / 'seed1_first_smoke'")
    end = text.index('    conflicts = ', start)
    text = text[:start] + "    parent_dir = BASE.parent / 'v6-fixed-regimen-two-seed-2m-20260908/seed3_control_stage1'\n    review = {'checkpoint_sha256': 'c23b7db58802e67c1bcb94f7418ff980db7ec981cab9ca171bb37cc574514d94'}\n    assert sha(parent_dir / 'latest.pt') == review['checkpoint_sha256']\n" + text[end:]
    text = replace(text, "folder = BASE / 'seed1_extended_restart'", "folder = BASE / 'seed3_first_capture'")
    text = replace(text, "str(BASE / 'train_capture.py')", "str(BASE / 'train_capture_derivation.py')")
    text = replace(text, "    write_new(folder / 'command.json', argv)", "    index = argv.index('--opponent-greedy-mixture')\n    assert float(argv[index+1]) == 0\n    del argv[index:index+2]\n    argv.append('--independent-observable-critic')\n    set_option(argv, '--deal-attempt-registry', BASE / 'attempt_registry')\n    set_option(argv, '--max-runtime-seconds', 600)\n    write_new(folder / 'command.json', argv)")
    with (BASE / 'run_seed3.py').open('x', encoding='utf-8') as handle:
        handle.write(text)


if __name__ == '__main__':
    main()
