"""Integration surface checks, not actual optimizer/rollout resume qualification."""
import unittest
import train_candidate


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trainer, cls.binding = train_candidate.install()

    def test_default_unchanged(self):
        self.assertEqual(self.trainer.OpponentPool().strategy, 'loss-kbest')

    def test_explicit_cli(self):
        parser = self.trainer.argparse.ArgumentParser()
        parser.add_argument('--pool-strategy', choices=('latest', 'loss-kbest', 'elo-kbest'), default='loss-kbest', help='Pool.')
        self.assertEqual(parser.parse_args([]).pool_strategy, 'loss-kbest')
        self.assertEqual(parser.parse_args(['--pool-strategy', 'anchor-latest']).pool_strategy, 'anchor-latest')

    def test_replacement_and_identity_mapping(self):
        pool = self.trainer.OpponentPool(k=3, strategy='anchor-latest')
        pool.snapshots = [
            {'id': 0, 'score_components': {'kind': 'initial_external_opponent'}},
            {'id': 4}, {'id': 3},
        ]
        pool._prune()
        self.assertEqual(pool.active_ids(), [0, 4, 3])
        pool.snapshots.append({'id': 5})
        pool._prune()
        self.assertEqual(pool.active_ids(), [0, 5, 4])
        rewards, counts = self.trainer.reconcile_adaptive_league_state(
            [0, 4, 3], pool.active_ids(), [1., 2., 3.], [10, 20, 30])
        self.assertEqual(rewards, [1., 0., 2.])
        self.assertEqual(counts, [10, 0, 20])

    def test_invalid_capacity(self):
        for k in [0, -1, True]:
            with self.assertRaises(ValueError):
                self.trainer.OpponentPool(k=k, strategy='anchor-latest')


if __name__ == '__main__':
    unittest.main()
