import unittest
from dataclasses import replace
import math
import random
import json

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
    def test_public_schema_uses_agile_and_waterfall_names(self):
        result = run_simulation(SimulationConfig(trials=1))
        self.assertEqual(result["config"]["agile_block_size"], 100)
        self.assertEqual(list(result["strategies"]), ["agile", "waterfall"])
        self.assertIn("agile_win_probability", result["comparison"])

    def test_average_run_boundaries_and_conservation(self):
        default = run_simulation(SimulationConfig(trials=2, revision_probability=0))
        agile = default["strategies"]["agile"]["average_run"]
        self.assertEqual(len(agile), 40)
        self.assertEqual(
            [(block["start_line"], block["end_line"], block["line_count"]) for block in agile[:2]],
            [(0, 100, 100), (100, 200, 100)],
        )
        self.assertEqual((agile[-1]["start_line"], agile[-1]["end_line"]), (3900, 4000))

        partial = run_simulation(SimulationConfig(trials=2, agile_block_size=333))
        blocks = partial["strategies"]["agile"]["average_run"]
        self.assertEqual((blocks[-1]["start_line"], blocks[-1]["end_line"], blocks[-1]["line_count"]), (3996, 4000, 4))
        self.assertEqual(sum(block["line_count"] for block in blocks), 4000)

        waterfall = default["strategies"]["waterfall"]["average_run"]
        self.assertEqual(
            [(block["start_line"], block["end_line"], block["line_count"]) for block in waterfall],
            [(0, 3600, 3600), (3600, 4000, 400)],
        )
        for strategy in default["strategies"].values():
            self.assertEqual(strategy["average_run"][0].keys(), {
                "start_line", "end_line", "line_count", "mean_writing_time",
                "mean_review_time", "mean_revision_time", "mean_rereview_time",
                "mean_revised_lines",
            })
            for key in ("writing_time", "review_time", "revision_time", "rereview_time"):
                self.assertAlmostEqual(
                    sum(block[f"mean_{key}"] for block in strategy["average_run"]),
                    strategy[f"mean_{key}"],
                )
        json.dumps(default)

    def test_average_run_exact_zero_and_full_revision_costs_with_setup(self):
        config = SimulationConfig(trials=1, revision_probability=0, review_setup_time=2)
        zero = run_simulation(config)
        self.assertEqual(
            zero["strategies"]["agile"]["average_run"][0],
            {
                "start_line": 0, "end_line": 100, "line_count": 100,
                "mean_writing_time": 100, "mean_review_time": 27,
                "mean_revision_time": 0, "mean_rereview_time": 0,
                "mean_revised_lines": 0,
            },
        )
        self.assertEqual(
            [(block["mean_review_time"], block["mean_rereview_time"]) for block in zero["strategies"]["waterfall"]["average_run"]],
            [(1802, 0), (127, 0)],
        )

        full = run_simulation(replace(config, revision_probability=1))
        self.assertEqual(
            [(block["mean_revision_time"], block["mean_rereview_time"], block["mean_revised_lines"])
             for block in full["strategies"]["waterfall"]["average_run"]],
            [(3600, 1802, 3600), (400, 127, 400)],
        )
        self.assertEqual(
            [(block["mean_revision_time"], block["mean_rereview_time"], block["mean_revised_lines"])
             for block in full["strategies"]["agile"]["average_run"][:2]],
            [(100, 27, 100), (100, 27, 100)],
        )

    def test_average_run_rereview_means_average_actual_trial_costs(self):
        config = SimulationConfig(trials=5, seed=17, agile_block_size=4000)
        result = run_simulation(config)
        rng = random.Random(config.seed)
        revision_counts = []
        for _ in range(config.trials):
            revision_counts.append(sum(rng.random() < config.revision_probability for _ in range(4000)))

        def review_cost(lines):
            if lines == 0:
                return 0
            multiplier = 1 if lines <= 100 else 1.25 if lines <= 500 else 1.5 if lines <= 1000 else 2
            return lines * config.review_time_per_line * multiplier + config.review_setup_time

        expected = sum(review_cost(count) for count in revision_counts) / config.trials
        block = result["strategies"]["agile"]["average_run"][0]
        self.assertEqual(block["mean_rereview_time"], expected)

    def test_average_run_component_sums_match_seeded_strategy_means(self):
        result = run_simulation(SimulationConfig(trials=37, seed=202, agile_block_size=333))
        for strategy in result["strategies"].values():
            for component in ("writing_time", "review_time", "revision_time", "rereview_time"):
                self.assertAlmostEqual(
                    sum(block[f"mean_{component}"] for block in strategy["average_run"]),
                    strategy[f"mean_{component}"],
                )

    def test_zero_and_full_revisions_match_hand_totals(self):
        zero = run_simulation(SimulationConfig(trials=1, revision_probability=0))
        self.assertEqual(zero["strategies"]["agile"]["total_time"]["mean"], 5000)
        self.assertEqual(zero["strategies"]["waterfall"]["total_time"]["mean"], 5925)
        self.assertEqual(zero["strategies"]["agile"]["mean_review_count"], 40)
        self.assertEqual(zero["strategies"]["waterfall"]["mean_review_count"], 2)

        full = run_simulation(SimulationConfig(trials=1, revision_probability=1))
        self.assertEqual(full["strategies"]["agile"]["mean_revised_lines"], 4000)
        self.assertEqual(full["strategies"]["agile"]["total_time"]["mean"], 10000)
        self.assertEqual(full["strategies"]["waterfall"]["total_time"]["mean"], 11850)
        self.assertEqual(full["strategies"]["agile"]["mean_review_count"], 80)
        self.assertEqual(full["strategies"]["waterfall"]["mean_review_count"], 4)

    def test_partial_blocks_conserve_lines_and_paired_revisions(self):
        result = run_simulation(SimulationConfig(trials=40, seed=9, agile_block_size=333))
        agile = result["strategies"]["agile"]
        waterfall = result["strategies"]["waterfall"]
        self.assertEqual(agile["blocks"], [333] * 12 + [4])
        self.assertEqual(sum(agile["blocks"]), 4000)
        self.assertEqual(sum(waterfall["blocks"]), 4000)
        self.assertEqual(agile["mean_revised_lines"], waterfall["mean_revised_lines"])

    def test_seed_reproducibility_and_non_degenerate_randomness(self):
        config = SimulationConfig(trials=100, seed=31)
        first = run_simulation(config)
        self.assertEqual(first, run_simulation(config))
        totals = first["strategies"]["agile"]["total_time"]
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
        self.assertEqual(result["strategies"]["agile"]["total_time"]["mean"], 80)
        self.assertEqual(result["strategies"]["waterfall"]["total_time"]["mean"], 4)
        self.assertEqual(result["comparison"]["mean_percent_saved"], -1900)

    def test_invalid_configurations_raise_value_error(self):
        invalid = [
            {"trials": True},
            {"trials": 0},
            {"seed": False},
            {"agile_block_size": 0},
            {"agile_block_size": 4001},
            {"agile_block_size": 1.5},
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
