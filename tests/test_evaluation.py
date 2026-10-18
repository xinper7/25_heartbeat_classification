"""Check that multilabel evaluation does not confuse label and record accuracy."""

import unittest

import numpy as np

from scripts.evaluate_ptbxl import metrics


class MultilabelMetricTests(unittest.TestCase):
    def test_one_missing_label_changes_record_match_and_micro_f1(self):
        truth = np.array([[1, 1, 0, 0, 0], [0, 0, 1, 1, 1]], dtype=bool)
        predicted = np.array([[1, 0, 0, 0, 0], [0, 0, 1, 1, 1]], dtype=bool)
        result = metrics(truth, predicted)
        self.assertEqual(result["exact_match_accuracy"], 0.5)
        self.assertEqual(result["hamming_loss"], 0.1)
        self.assertEqual(result["macro_f1"], 0.8)
        self.assertAlmostEqual(result["micro_f1"], 8 / 9)
        self.assertEqual(result["per_class"]["MI"]["fn"], 1)

    def test_no_predicted_positives_is_finite_and_zero_f1(self):
        truth = np.ones((2, 5), dtype=bool)
        result = metrics(truth, np.zeros_like(truth))
        self.assertEqual(result["macro_f1"], 0)
        self.assertEqual(result["micro_f1"], 0)
        self.assertEqual(result["macro_precision"], 0)
        self.assertEqual(result["exact_match_accuracy"], 0)


if __name__ == "__main__":
    unittest.main()
