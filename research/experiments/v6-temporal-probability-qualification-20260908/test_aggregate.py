import unittest
import torch
from qualify import ProbabilityAggregate


class Fixed(torch.nn.Module):
    def __init__(self, values):
        super().__init__()
        self.values = torch.tensor([values], dtype=torch.float64)

    def forward(self, cards, actions, extras, mask):
        return self.values.expand(mask.shape[0], -1), torch.zeros((mask.shape[0], 1))


class AggregateTests(unittest.TestCase):
    def query(self, models, mask):
        return ProbabilityAggregate(models)(None, None, None, torch.tensor(mask))[0]

    def test_empty_members(self):
        with self.assertRaises(ValueError):
            ProbabilityAggregate([])

    def test_empty_support(self):
        with self.assertRaises(ValueError):
            self.query([Fixed([0, 1])], [[0, 0]])

    def test_nonfinite_legal(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                self.query([Fixed([value, 0])], [[1, 1]])

    def test_nonfinite_illegal_masked(self):
        output = self.query([Fixed([float('nan'), 0])], [[0, 1]])
        torch.testing.assert_close(output.exp(), torch.tensor([[0., 1.]], dtype=torch.float64))

    def test_bad_shape(self):
        with self.assertRaises(ValueError):
            self.query([Fixed([0, 1, 2])], [[1, 1]])

    def test_position_mismatch(self):
        first, second = Fixed([0, 1]), Fixed([0, 1])
        second.requires_position_feature = True
        with self.assertRaises(ValueError):
            ProbabilityAggregate([first, second])

    def test_probability_not_logit_average(self):
        models = [Fixed([0, 2]), Fixed([0, -8])]
        output = self.query(models, [[1, 1]]).exp()
        expected = torch.stack([m.values.softmax(-1) for m in models]).mean(0)
        torch.testing.assert_close(output, expected)
        self.assertFalse(torch.allclose(output, torch.stack([m.values for m in models]).mean(0).softmax(-1)))

    def test_extreme_logits_batch_and_ties(self):
        out = self.query([Fixed([10000, 10000, -10000])], [[1, 1, 0], [0, 0, 1]])
        torch.testing.assert_close(out.exp(), torch.tensor([[.5, .5, 0], [0, 0, 1]], dtype=torch.float64))
        self.assertEqual(out.argmax(-1).tolist(), [0, 2])


if __name__ == '__main__':
    unittest.main()
