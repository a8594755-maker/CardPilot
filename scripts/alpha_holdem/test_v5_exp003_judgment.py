import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_exp003_judgment import build_judgment, effect_status, mirror_effects, value_loss_support


class Exp003JudgmentMathTest(unittest.TestCase):
    def test_effect_status_uses_strict_interval(self):
        self.assertEqual(effect_status(11.0, 10.0), "PASS")
        self.assertEqual(effect_status(-11.0, 10.0), "REGRESSION")
        self.assertEqual(effect_status(10.0, 10.0), "INCONCLUSIVE")

    def test_native_axis_uses_rss_halfwidth_and_direct_lower_bound(self):
        bundle = {
            "roles": {
                "pre_vs_native": {"candidate_bb100": -60.0, "candidate_ci95_bb100": 12.0},
                "post_vs_native": {"candidate_bb100": -30.0, "candidate_ci95_bb100": 16.0},
                "post_vs_pre_direct": {"candidate_bb100": 25.0, "candidate_ci95_bb100": 20.0},
            }
        }
        result = mirror_effects(bundle)
        self.assertAlmostEqual(result["native_axis"]["combined_ci95_halfwidth_bb100"], 20.0)
        self.assertEqual(result["native_axis"]["status"], "PASS")
        self.assertEqual(result["direct_causal"]["status"], "PASS")

    def test_value_loss_bootstrap_is_deterministic(self):
        pre = [100.0 + (index % 5) for index in range(200)]
        post = [50.0 + (index % 5) for index in range(200)]
        first = value_loss_support(pre, post)
        second = value_loss_support(pre, post)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PASS")
        self.assertGreater(first["ci95_lower"], 0.0)

    def test_value_loss_overlap_is_inconclusive(self):
        values = [100.0 + (index % 7) for index in range(200)]
        result = value_loss_support(values, list(values))
        self.assertEqual(result["status"], "INCONCLUSIVE")


def log_line(iteration: int, hands: int, value_loss: float, *, exp003: bool) -> str:
    counters = "mirror=1/1 aiev=1:100 aiev_skip=0:0 " if exp003 else ""
    return (
        f"[{iteration}] hands={hands:,} rew=+0.100 rew100=+0.100 ploss=0.0010 "
        f"vloss={value_loss:.4f} ent=1.0000 eps=0.000 pool=5 {counters}"
        "trans=100 terms=50 mix=F0.250/C0.250/R0.450/A0.050 "
        "pmix=F0.300/C0.300/R0.350/A0.050 xmix=F0.250/C0.300/R0.400/A0.050 "
        "h/s=3000 tdec/s=5000 inf_bs=200.0 collect=0.02s ppo=0.03s"
    )


class Exp003JudgmentIntegrationTest(unittest.TestCase):
    def test_review_ready_bundle_reaches_schema_valid_adopt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            baseline_dir = root / "baseline"
            run_dir.mkdir()
            baseline_dir.mkdir()
            candidate_iteration = 22000
            candidate_hands = 408_100_000
            baseline_lines = [
                log_line(iteration, 350_000_000 + (iteration - 21600) * 100, 100.0, exp003=False)
                for iteration in range(21601, 21801)
            ]
            candidate_lines = [
                log_line(iteration, 358_064_575 + (iteration - 21800) * 100, 50.0, exp003=True)
                for iteration in range(21801, candidate_iteration + 1)
            ]
            (baseline_dir / "latest_train.log").write_text("\n".join(baseline_lines) + "\n", encoding="utf-8")
            (run_dir / "latest_train.log").write_text("\n".join(candidate_lines) + "\n", encoding="utf-8")
            (run_dir / "console.err.log").write_text("", encoding="utf-8")
            (run_dir / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "config": {
                            "rollout_mode": "multi",
                            "rollout_envs_per_worker": 16,
                            "inference_min_batch_slots": 256,
                            "inference_batch_deadline_us": 1000.0,
                            "mirror_self_play_deals": True,
                            "allin_runout_ev": True,
                            "allin_runout_ev_max_runouts": 200,
                            "preflop_action_prior_coef": 0.01,
                            "postflop_action_prior_coef": 0.02,
                            "workers": 22,
                            "starting_stack": 200.0,
                        }
                    }
                ),
                encoding="utf-8",
            )
            for iteration in (21800, 21900, 22000):
                (run_dir / f"gate_{iteration}_status.json").write_text(
                    json.dumps(
                        {
                            "overall": "PASS",
                            "health_overall": "PASS",
                            "checkpoint_iteration": iteration,
                            "checkpoint_hands": candidate_hands if iteration == candidate_iteration else 400_000_000,
                            "checkpoint": {
                                "fresh_from_zero_lineage": True,
                                "actual_hand_accounting": True,
                            },
                        }
                    ),
                    encoding="utf-8",
                )
            frozen = run_dir / "post.pt"
            frozen.write_bytes(b"post")
            roles = {}
            for name, point, halfwidth in (
                ("pre_vs_native", -60.0, 10.0),
                ("post_vs_native", -20.0, 10.0),
                ("post_vs_pre_direct", 30.0, 10.0),
            ):
                primary = run_dir / f"{name}.json"
                primary.write_text("{}", encoding="utf-8")
                companions = {}
                for suffix in ("md", "stdout.log", "stderr.log", "execution.json"):
                    companion = run_dir / f"{name}.{suffix}"
                    companion.write_text("", encoding="utf-8")
                    companions[suffix] = str(companion)
                roles[name] = {
                    "path": str(primary),
                    "companion_paths": companions,
                    "candidate_bb100": point,
                    "candidate_ci95_bb100": halfwidth,
                }
            bundle = {
                "status": "REVIEW_READY",
                "freeze": {
                    "archive_iteration": candidate_iteration,
                    "archive_hands": candidate_hands,
                    "archive_path": str(frozen),
                    "archive_sha256": "ab" * 32,
                },
                "roles": roles,
            }
            args = argparse.Namespace(run_dir=str(run_dir), baseline_run_dir=str(baseline_dir))
            with patch("v5_exp003_judgment.exp003_mirror_bundle_status", return_value=bundle), patch(
                "v5_exp003_judgment.artifact_guard",
                return_value={"status": "PASS", "path": "fixture", "actual_sha256": "ok"},
            ):
                result = build_judgment(args)

        self.assertEqual(result["schema_version"], "v5.exp003.judgment.v1")
        self.assertEqual(result["measurement_status"], "REVIEW_READY")
        self.assertEqual(result["decision"], "ADOPT")
        self.assertTrue(result["decision_valid"])


if __name__ == "__main__":
    unittest.main()
