import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_meas001_common_deal_eval as meas


def fake_policy(label: str, sha_digit: str, iteration: int, hands: int):
    return SimpleNamespace(
        label=label,
        path=Path(f"{label}.pt"),
        sha256=sha_digit * 64,
        checkpoint={
            "iteration": iteration,
            "total_hands": hands,
            "version": "v5.zero",
            "env_version": "v55",
            "obs_version": "v55",
            "action_space_version": "9slot_v5",
            "starting_stack_bb": 200.0,
            "fresh_from_zero_lineage": True,
            "run_id": f"run-{label}",
        },
        env_version="v55",
        obs_version="v55",
    )


def bindings():
    return {
        "pre": {
            "label": "pre",
            "path": "pre.pt",
            "sha256": "1" * 64,
            "iteration": 100,
            "total_hands": 1_000,
        },
        "post": {
            "label": "post",
            "path": "post.pt",
            "sha256": "2" * 64,
            "iteration": 200,
            "total_hands": 2_000,
        },
        "native": {
            "label": "native",
            "path": "native.pt",
            "sha256": "3" * 64,
            "iteration": 50,
            "total_hands": 500,
        },
    }


def source_binding():
    return {
        "path": "source_bundle.json",
        "sha256": "4" * 64,
        "payload_sha256": "5" * 64,
    }


def fake_play_hand(*, env, deck, candidate, anchor, candidate_seat):
    del env
    role_base = {
        ("pre", "native"): 0.10,
        ("post", "native"): 0.40,
        ("post", "pre"): 0.25,
    }[(candidate.label, anchor.label)]
    # Both seats see the same deterministic deal term, proving pair alignment
    # without making the unit fixture depend on the poker engine.
    reward = role_base + (deck[0] % 5) * 0.01 + candidate_seat * 0.02
    return {
        "candidate_reward_bb": reward,
        "decisions": 3,
        "policy_decisions": {"candidate": 2, "anchor": 1},
        "ood_nodes": {"candidate": 0, "anchor": 0},
    }


class DealManifestTest(unittest.TestCase):
    def test_manifest_is_deterministic_unique_and_common_seeded(self):
        kwargs = {
            "pairs": 8,
            "seed": 20260710,
            "starting_stack": 200.0,
            "bindings": bindings(),
            "evaluator_path": Path(meas.__file__),
            "source_bundle_binding": source_binding(),
            "created_at": "2026-07-10T00:00:00+00:00",
        }
        first = meas.build_deal_manifest(**kwargs)
        second = meas.build_deal_manifest(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(meas.verify_manifest_integrity(first), [])
        self.assertEqual(first["role_seeds"], {role: 20260710 for role in meas.ROLE_NAMES})
        self.assertEqual(len({row["deal_id"] for row in first["deals"]}), 8)

        changed = meas.build_deal_manifest(**{**kwargs, "seed": 20260711})
        self.assertNotEqual(first["deal_stream_sha256"], changed["deal_stream_sha256"])

    def test_manifest_tamper_is_rejected(self):
        manifest = meas.build_deal_manifest(
            pairs=2,
            seed=1,
            starting_stack=200.0,
            bindings=bindings(),
            evaluator_path=Path(meas.__file__),
            source_bundle_binding=source_binding(),
            created_at="fixed",
        )
        manifest["deals"][0]["deal_id"] = "tampered"
        self.assertIn("manifest payload hash mismatch", meas.verify_manifest_integrity(manifest))


class IdentityTest(unittest.TestCase):
    def test_exact_checkpoint_identity_passes_and_late_checkpoint_fails(self):
        policy = fake_policy("pre", "1", 100, 1_000)
        result = meas.require_exact_policy_identity(
            policy,
            role="pre",
            expected_iteration=100,
            expected_hands=1_000,
        )
        self.assertEqual(result["identity_status"], "PASS")
        with self.assertRaisesRegex(ValueError, "late"):
            meas.require_exact_policy_identity(
                policy,
                role="pre",
                expected_iteration=99,
                expected_hands=1_000,
            )

    def test_duplicate_checkpoint_hashes_are_rejected(self):
        values = bindings()
        values["post"]["sha256"] = values["pre"]["sha256"]
        with self.assertRaisesRegex(ValueError, "distinct"):
            meas.require_distinct_checkpoint_hashes(values)


class CommonDealEvaluationTest(unittest.TestCase):
    def make_manifest(self, pairs: int = 6, source_bundle_binding=None):
        return meas.build_deal_manifest(
            pairs=pairs,
            seed=20260710,
            starting_stack=200.0,
            bindings=bindings(),
            evaluator_path=Path(meas.__file__),
            source_bundle_binding=source_bundle_binding or source_binding(),
            created_at="2026-07-10T00:00:00+00:00",
        )

    def make_policies(self):
        return {
            "pre": fake_policy("pre", "1", 100, 1_000),
            "post": fake_policy("post", "2", 200, 2_000),
            "native": fake_policy("native", "3", 50, 500),
        }

    def test_three_roles_share_deals_and_retain_aligned_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            pairs_path = Path(tmp) / "pairs.jsonl"
            manifest = self.make_manifest()
            result = meas.evaluate_common_deals(
                manifest=manifest,
                policies=self.make_policies(),
                pairs_jsonl_path=pairs_path,
                play_hand_fn=fake_play_hand,
            )
            validation = meas.validate_aligned_pairs(
                manifest=manifest,
                pairs_jsonl_path=pairs_path,
                expected_sha256=result["pairs_jsonl"]["sha256"],
            )
            records = [json.loads(line) for line in pairs_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(validation["status"], "PASS")
        self.assertEqual(validation["rows"], 6)
        self.assertEqual(result["pairs"], 6)
        self.assertTrue(all(set(row["roles"]) == set(meas.ROLE_NAMES) for row in records))
        self.assertTrue(all(row["seat_order"] == [0, 1] for row in records))
        for row in records:
            expected_delta = (
                row["roles"]["post_vs_native"]["pair_mean_bb_per_hand"]
                - row["roles"]["pre_vs_native"]["pair_mean_bb_per_hand"]
            )
            self.assertAlmostEqual(row["native_axis_delta_bb_per_hand"], expected_delta)
            self.assertAlmostEqual(
                row["direct_causal_bb_per_hand"],
                row["roles"]["post_vs_pre_direct"]["pair_mean_bb_per_hand"],
            )
        self.assertAlmostEqual(
            result["primary_effects"]["paired_native_axis_delta"]["mean_bb100"],
            30.0,
        )
        expected_direct_mean = (
            sum(row["direct_causal_bb_per_hand"] for row in records) / len(records) * 100.0
        )
        self.assertAlmostEqual(
            result["primary_effects"]["post_vs_pre_direct"]["mean_bb100"],
            expected_direct_mean,
        )

    def test_partial_duplicate_and_mismatched_pairs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_manifest(pairs=4)
            original = root / "original.jsonl"
            result = meas.evaluate_common_deals(
                manifest=manifest,
                policies=self.make_policies(),
                pairs_jsonl_path=original,
                play_hand_fn=fake_play_hand,
            )
            rows = original.read_text(encoding="utf-8").splitlines()

            partial = root / "partial.jsonl"
            partial.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
            partial_validation = meas.validate_aligned_pairs(
                manifest=manifest,
                pairs_jsonl_path=partial,
            )

            duplicate = root / "duplicate.jsonl"
            changed = [json.loads(line) for line in rows]
            changed[1]["deal_id"] = changed[0]["deal_id"]
            duplicate.write_text(
                "\n".join(json.dumps(row, sort_keys=True) for row in changed) + "\n",
                encoding="utf-8",
            )
            duplicate_validation = meas.validate_aligned_pairs(
                manifest=manifest,
                pairs_jsonl_path=duplicate,
                expected_sha256=result["pairs_jsonl"]["sha256"],
            )

        self.assertEqual(partial_validation["status"], "FAIL")
        self.assertTrue(any("row count" in error for error in partial_validation["errors"]))
        self.assertEqual(duplicate_validation["status"], "FAIL")
        self.assertTrue(any("duplicate" in error for error in duplicate_validation["errors"]))
        self.assertTrue(any("hash mismatch" in error for error in duplicate_validation["errors"]))

    def test_completed_bundle_audit_recomputes_every_hash_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            source_bundle_path = root / "source_bundle.json"
            pairs_path = root / "pairs.jsonl"
            summary_path = root / "summary.json"
            execution_path = root / "execution.json"
            source_bundle = meas.build_source_bundle(created_at="2026-07-10T00:00:00+00:00")
            meas.write_json_exclusive(source_bundle_path, source_bundle)
            frozen_source_binding = {
                "path": str(source_bundle_path.resolve()),
                "sha256": meas.sha256_file(source_bundle_path),
                "payload_sha256": source_bundle["source_bundle_payload_sha256"],
            }
            manifest = self.make_manifest(pairs=5, source_bundle_binding=frozen_source_binding)
            meas.write_json_exclusive(manifest_path, manifest)
            evidence = meas.evaluate_common_deals(
                manifest=manifest,
                policies=self.make_policies(),
                pairs_jsonl_path=pairs_path,
                play_hand_fn=fake_play_hand,
            )
            validation = meas.validate_aligned_pairs(
                manifest=manifest,
                pairs_jsonl_path=pairs_path,
                expected_sha256=evidence["pairs_jsonl"]["sha256"],
            )
            measurement = meas.classify_measurement(
                primary_effects=evidence["primary_effects"],
                role_summaries=evidence["roles"],
                bundle_validation=validation,
                ci95_halfwidth_max_bb100=20.0,
                anchor_ood_max=0.15,
            )
            summary = {
                "schema_version": meas.SCHEMA_VERSION,
                "design_id": "MEAS-001",
                "pairs": manifest["pairs"],
                "seed": manifest["seed"],
                "bindings": manifest["bindings"],
                "manifest": {
                    "sha256": meas.sha256_file(manifest_path),
                    "payload_sha256": manifest["manifest_payload_sha256"],
                    "deal_stream_sha256": manifest["deal_stream_sha256"],
                },
                **evidence,
                "bundle_validation": validation,
                "measurement": measurement,
            }
            summary["result_payload_sha256"] = meas.payload_sha256(summary)
            meas.write_json_exclusive(summary_path, summary)
            meas.write_json_exclusive(
                execution_path,
                {
                    "status": "COMPLETED",
                    "measurement_status": measurement["status"],
                    "summary_sha256": meas.sha256_file(summary_path),
                },
            )
            passed = meas.audit_completed_bundle(
                summary_path=summary_path,
                manifest_path=manifest_path,
                source_bundle_path=source_bundle_path,
                pairs_jsonl_path=pairs_path,
                execution_path=execution_path,
            )

            with pairs_path.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            failed = meas.audit_completed_bundle(
                summary_path=summary_path,
                manifest_path=manifest_path,
                source_bundle_path=source_bundle_path,
                pairs_jsonl_path=pairs_path,
                execution_path=execution_path,
            )

        self.assertEqual(passed["status"], "PASS")
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("hash mismatch" in error for error in failed["errors"]))


class DecisionAndOneShotTest(unittest.TestCase):
    @staticmethod
    def effects(mean: float, halfwidth: float):
        return {
            name: {
                "mean_bb100": mean,
                "ci95_halfwidth_bb100": halfwidth,
                "ci95_lower_bb100": mean - halfwidth,
                "ci95_upper_bb100": mean + halfwidth,
            }
            for name in ("paired_native_axis_delta", "post_vs_pre_direct")
        }

    @staticmethod
    def roles():
        return {role: {"anchor_ood_node_rate": 0.0} for role in meas.ROLE_NAMES}

    def classify(self, effects, validation=None):
        return meas.classify_measurement(
            primary_effects=effects,
            role_summaries=self.roles(),
            bundle_validation=validation or {"status": "PASS", "rows": 100_000},
            ci95_halfwidth_max_bb100=20.0,
            anchor_ood_max=0.15,
        )

    def test_terminal_classification(self):
        self.assertEqual(self.classify(self.effects(30.0, 10.0))["status"], "PASS")
        self.assertEqual(self.classify(self.effects(30.0, 21.0))["status"], "INCONCLUSIVE")
        self.assertEqual(self.classify(self.effects(-30.0, 10.0))["status"], "FAIL")
        self.assertEqual(
            self.classify(self.effects(30.0, 10.0), {"status": "FAIL", "rows": 99_999})["status"],
            "FAIL",
        )

    def test_exclusive_artifact_write_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            meas.write_json_exclusive(path, {"first": True})
            with self.assertRaises(FileExistsError):
                meas.write_json_exclusive(path, {"second": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"first": True})

    def test_registered_cli_contract_rejects_smaller_posthoc_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = argparse.Namespace(
                pairs=25_000,
                starting_stack=200.0,
                device="cpu",
                priority="below-normal",
                anchor_ood_max=0.15,
                out_source_bundle=str(root / "source_bundle.json"),
                out_manifest=str(root / "manifest.json"),
                out_pairs_jsonl=str(root / "pairs.jsonl"),
                out_json=str(root / "summary.json"),
                out_md=str(root / "summary.md"),
                execution_json=str(root / "execution.json"),
            )
            with self.assertRaisesRegex(ValueError, "exactly 100000"):
                meas.validate_registered_args(args)


if __name__ == "__main__":
    unittest.main()
