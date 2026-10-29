import unittest
from dataclasses import replace
import math

from code_review_sim.model import SimulationConfig
from code_review_sim.simulation import run_simulation, review_multiplier


class ReviewMultiplierTests(unittest.TestCase):
    def test_exact_tier_boundaries(self):
        self.assertEqual(review_multiplier(1), 1.0)
        self.assertEqual(review_multiplier(100), 1.0)
        self.assertEqual(review_multiplier(101), 1.25)
        self.assertEqual(review_multiplier(500), 1.25)
        self.assertEqual(review_multiplier(501), 1.5)
        self.assertEqual(review_multiplier(1000), 1.5)
        self.assertEqual(review_multiplier(1001), 2.0)


class SimulationTests(unittest.TestCase):
    def test_zero_and_full_revisions_match_hand_totals(self):
        zero = run_simulation(SimulationConfig(trials=1, revision_probability=0))
        self.assertEqual(zero["strategies"]["incremental"]["total_time"]["mean"], 5000)
        self.assertEqual(zero["strategies"]["delayed"]["total_time"]["mean"], 5925)
        self.assertEqual(zero["strategies"]["incremental"]["mean_review_count"], 40)
        self.assertEqual(zero["strategies"]["delayed"]["mean_review_count"], 2)

        full = run_simulation(SimulationConfig(trials=1, revision_probability=1))
        self.assertEqual(full["strategies"]["incremental"]["mean_revised_lines"], 4000)
        self.assertEqual(full["strategies"]["incremental"]["total_time"]["mean"], 10000)
        self.assertEqual(full["strategies"]["delayed"]["total_time"]["mean"], 11850)
        self.assertEqual(full["strategies"]["incremental"]["mean_review_count"], 80)
        self.assertEqual(full["strategies"]["delayed"]["mean_review_count"], 4)

    def test_partial_blocks_conserve_lines_and_paired_revisions(self):
        result = run_simulation(SimulationConfig(trials=40, seed=9, incremental_block_size=333))
        incremental = result["strategies"]["incremental"]
        delayed = result["strategies"]["delayed"]
        self.assertEqual(incremental["blocks"], [333] * 12 + [4])
        self.assertEqual(sum(incremental["blocks"]), 4000)
        self.assertEqual(sum(delayed["blocks"]), 4000)
        self.assertEqual(incremental["mean_revised_lines"], delayed["mean_revised_lines"])

    def test_seed_reproducibility_and_non_degenerate_randomness(self):
        config = SimulationConfig(trials=100, seed=31)
        first = run_simulation(config)
        self.assertEqual(first, run_simulation(config))
        totals = first["strategies"]["incremental"]["total_time"]
        self.assertGreater(totals["stdev"], 0)
        self.assertLess(totals["p05"], totals["p95"])
        interval = first["comparison"]["paired_savings_ci95"]
        self.assertEqual(len(interval), 2)
        self.assertTrue(all(math.isfinite(value) for value in interval))
        self.assertLessEqual(interval[0], first["comparison"]["mean_time_saved"])
        self.assertGreaterEqual(interval[1], first["comparison"]["mean_time_saved"])

    def test_single_trial_has_no_confidence_interval(self):
        result = run_simulation(SimulationConfig(trials=1, revision_probability=0))
        self.assertIsNone(result["comparison"]["paired_savings_ci95"])

    def test_zero_costs_and_setup_count(self):
        config = SimulationConfig(
            trials=3,
            revision_probability=0,
            write_time_per_line=0,
            review_time_per_line=0,
            revision_time_per_line=0,
            review_setup_time=2,
        )
        result = run_simulation(config)
        self.assertEqual(result["strategies"]["incremental"]["total_time"]["mean"], 80)
        self.assertEqual(result["strategies"]["delayed"]["total_time"]["mean"], 4)
        self.assertEqual(result["comparison"]["mean_percent_saved"], -1900)

    def test_invalid_configurations_raise_value_error(self):
        invalid = [
            {"trials": True},
            {"trials": 0},
            {"seed": False},
            {"incremental_block_size": 0},
            {"incremental_block_size": 4001},
            {"incremental_block_size": 1.5},
            {"revision_probability": math.nan},
            {"revision_probability": math.inf},
            {"revision_probability": -0.1},
            {"revision_probability": 1.1},
            {"write_time_per_line": math.inf},
            {"review_time_per_line": math.nan},
            {"revision_time_per_line": -1},
            {"review_setup_time": True},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    run_simulation(replace(SimulationConfig(), **changes))


if __name__ == "__main__":
    unittest.main()
