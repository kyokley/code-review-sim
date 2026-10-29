import unittest
from dataclasses import replace
import math
import random
import json
import statistics
from unittest.mock import patch

from code_review_sim import simulation
from code_review_sim.model import SimulationConfig
from code_review_sim.simulation import (
    _sample_agile_blocks,
    _sample_binomial,
    review_multiplier,
    run_simulation,
)


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
    def test_binomial_sampler_counts_controlled_bernoulli_draws(self):
        class ControlledRng:
            def __init__(self, values):
                self.values = iter(values)

            def random(self):
                return next(self.values)

        self.assertEqual(_sample_binomial(ControlledRng([0.1, 0.6, 0.4, 0.9]), 4), 2)

    def test_agile_partition_redraws_zero_samples_and_caps_final_block(self):
        class ControlledRng:
            def __init__(self, values):
                self.values = iter(values)

            def random(self):
                return next(self.values)

        rng = ControlledRng([0.9] * 4 + [0.1, 0.1, 0.9, 0.9] + [0.1] * 4)
        blocks = _sample_agile_blocks(rng, mean_block_size=2, total_lines=5)
        self.assertEqual(blocks, [2, 3])
        self.assertEqual(sum(blocks), 5)

    def test_nominal_binomial_mean_is_200(self):
        rng = random.Random(2026)
        samples = [_sample_binomial(rng, 400) for _ in range(1000)]
        self.assertLess(abs(statistics.mean(samples) - 200), 2.0)

    def test_agile_blocks_are_sampled_each_trial_and_seed_reproducible(self):
        config = SimulationConfig(trials=20, seed=31, agile_block_size=200)
        partitions = []
        sampler = simulation._sample_agile_blocks

        def record_partition(rng, mean_block_size):
            blocks = sampler(rng, mean_block_size)
            partitions.append(blocks)
            return blocks

        with patch.object(simulation, "_sample_agile_blocks", side_effect=record_partition):
            first = run_simulation(config)
        self.assertEqual(first, run_simulation(config))
        self.assertEqual(len(partitions), config.trials)
        self.assertGreater(len({tuple(blocks) for blocks in partitions}), 1)
        blocks = first["strategies"]["agile"]["blocks"]
        self.assertAlmostEqual(sum(blocks), 4000)
        self.assertGreater(len(set(blocks[:-1])), 1)
        self.assertTrue(all(size > 0 for size in blocks))

    def test_agile_average_includes_missing_tail_reviews_as_zero(self):
        partitions = iter(([1000, 3000], [4000]))
        with patch(
            "code_review_sim.simulation._sample_agile_blocks",
            side_effect=lambda *_args, **_kwargs: next(partitions),
        ):
            result = run_simulation(SimulationConfig(trials=2, revision_probability=0))
        rows = result["strategies"]["agile"]["average_run"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["line_count"], 1500)
        self.assertEqual(rows[1]["start_line"], 2500)
        self.assertEqual(rows[1]["end_line"], 4000)
        self.assertEqual(rows[1]["mean_writing_time"], 1500)
        self.assertEqual(rows[1]["mean_review_time"], 750)
        self.assertEqual(sum(row["line_count"] for row in rows), 4000)

    def test_later_longer_partition_averages_prior_missing_boundaries_at_end(self):
        partitions = iter(([4000], [1000, 3000]))
        with patch(
            "code_review_sim.simulation._sample_agile_blocks",
            side_effect=lambda *_args, **_kwargs: next(partitions),
        ):
            result = run_simulation(SimulationConfig(trials=2, revision_probability=0))
        strategy = result["strategies"]["agile"]
        rows = strategy["average_run"]
        self.assertEqual((rows[1]["start_line"], rows[1]["end_line"]), (2500, 4000))
        for previous, current in zip(rows, rows[1:]):
            self.assertEqual(previous["end_line"], current["start_line"])
        for row in rows:
            self.assertEqual(row["end_line"] - row["start_line"], row["line_count"])
        for component in ("writing_time", "review_time", "revision_time", "rereview_time"):
            self.assertAlmostEqual(
                sum(row[f"mean_{component}"] for row in rows),
                strategy[f"mean_{component}"],
            )

    def test_agile_average_costs_average_actual_nonlinear_trial_costs(self):
        partitions = iter(([100, 3900], [500, 3500]))
        with patch(
            "code_review_sim.simulation._sample_agile_blocks",
            side_effect=lambda *_args, **_kwargs: next(partitions),
        ):
            result = run_simulation(SimulationConfig(
                trials=2, revision_probability=0, review_time_per_line=0.25,
            ))
        first_row = result["strategies"]["agile"]["average_run"][0]
        self.assertEqual(first_row["line_count"], 300)
        self.assertEqual(first_row["mean_review_time"], 90.625)
        self.assertNotEqual(first_row["mean_review_time"], 93.75)

    def test_public_schema_uses_agile_and_waterfall_names(self):
        result = run_simulation(SimulationConfig(trials=1))
        self.assertEqual(result["config"]["agile_block_size"], 200)
        self.assertEqual(list(result["strategies"]), ["agile", "waterfall"])
        self.assertIn("agile_win_probability", result["comparison"])

    def test_average_run_boundaries_and_conservation(self):
        default = run_simulation(SimulationConfig(trials=2, revision_probability=0))
        agile = default["strategies"]["agile"]["average_run"]
        self.assertGreater(len(agile), 1)
        self.assertEqual(agile[0]["start_line"], 0)
        self.assertEqual(agile[-1]["end_line"], 4000)
        self.assertAlmostEqual(sum(block["line_count"] for block in agile), 4000)
        for previous, current in zip(agile, agile[1:]):
            self.assertAlmostEqual(previous["end_line"], current["start_line"])

        partial = run_simulation(SimulationConfig(trials=2, agile_block_size=333))
        blocks = partial["strategies"]["agile"]["average_run"]
        self.assertEqual(blocks[0]["start_line"], 0)
        self.assertEqual(blocks[-1]["end_line"], 4000)
        self.assertAlmostEqual(sum(block["line_count"] for block in blocks), 4000)

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
        agile_rows = zero["strategies"]["agile"]["average_run"]
        self.assertEqual(agile_rows[0]["start_line"], 0)
        self.assertEqual(agile_rows[-1]["end_line"], 4000)
        self.assertAlmostEqual(sum(row["mean_writing_time"] for row in agile_rows), 4000)
        self.assertAlmostEqual(sum(row["mean_review_time"] for row in agile_rows), zero["strategies"]["agile"]["mean_review_time"])
        self.assertTrue(all(row["mean_revision_time"] == row["mean_rereview_time"] == 0 for row in agile_rows))
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
        agile_full = full["strategies"]["agile"]
        self.assertAlmostEqual(sum(block["mean_revision_time"] for block in agile_full["average_run"]), 4000)
        self.assertAlmostEqual(sum(block["mean_revised_lines"] for block in agile_full["average_run"]), 4000)

    def test_average_run_rereview_means_average_actual_trial_costs(self):
        config = SimulationConfig(trials=5, seed=17, agile_block_size=4000)
        with patch("code_review_sim.simulation._sample_agile_blocks", return_value=[4000]):
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
        self.assertEqual(zero["strategies"]["agile"]["mean_writing_time"], 4000)
        self.assertEqual(zero["strategies"]["agile"]["total_time"]["mean"], 4000 + zero["strategies"]["agile"]["mean_review_time"])
        self.assertEqual(zero["strategies"]["waterfall"]["total_time"]["mean"], 5925)
        self.assertGreater(zero["strategies"]["agile"]["mean_review_count"], 0)
        self.assertEqual(zero["strategies"]["waterfall"]["mean_review_count"], 2)

        full = run_simulation(SimulationConfig(trials=1, revision_probability=1))
        self.assertEqual(full["strategies"]["agile"]["mean_revised_lines"], 4000)
        self.assertEqual(full["strategies"]["agile"]["mean_review_time"], zero["strategies"]["agile"]["mean_review_time"])
        self.assertEqual(full["strategies"]["agile"]["total_time"]["mean"], 8000 + full["strategies"]["agile"]["mean_review_time"] + full["strategies"]["agile"]["mean_rereview_time"])
        self.assertEqual(full["strategies"]["waterfall"]["total_time"]["mean"], 11850)
        self.assertEqual(full["strategies"]["agile"]["mean_review_count"], 2 * len(full["strategies"]["agile"]["blocks"]))
        self.assertEqual(full["strategies"]["waterfall"]["mean_review_count"], 4)

    def test_partial_blocks_conserve_lines_and_paired_revisions(self):
        result = run_simulation(SimulationConfig(trials=40, seed=9, agile_block_size=333))
        agile = result["strategies"]["agile"]
        waterfall = result["strategies"]["waterfall"]
        self.assertAlmostEqual(sum(agile["blocks"]), 4000)
        self.assertAlmostEqual(sum(agile["blocks"]), sum(row["line_count"] for row in agile["average_run"]))
        self.assertGreater(len(set(agile["blocks"][:-1])), 1)
        self.assertEqual(sum(waterfall["blocks"]), 4000)
        self.assertEqual(agile["mean_revised_lines"], waterfall["mean_revised_lines"])

    def test_agile_sizing_does_not_change_seeded_waterfall_results(self):
        config = SimulationConfig(trials=7, seed=221, agile_block_size=200)
        result = run_simulation(config)
        rng = random.Random(config.seed)
        expected_totals = []
        expected_review = []
        expected_rereview = []
        for _ in range(config.trials):
            flags = [rng.random() < config.revision_probability for _ in range(4000)]
            revised_counts = [sum(flags[:3600]), sum(flags[3600:])]
            initial = 3600 * 0.25 * 2 + 400 * 0.25 * 1.25
            rereview = sum(
                count * 0.25 * (1 if count <= 100 else 1.25 if count <= 500 else 1.5 if count <= 1000 else 2)
                for count in revised_counts
            )
            expected_review.append(initial)
            expected_rereview.append(rereview)
            expected_totals.append(4000 + initial + sum(revised_counts) + rereview)
        waterfall = result["strategies"]["waterfall"]
        self.assertEqual(waterfall["mean_review_time"], statistics.mean(expected_review))
        self.assertEqual(waterfall["mean_rereview_time"], statistics.mean(expected_rereview))
        self.assertEqual(waterfall["total_time"]["mean"], statistics.mean(expected_totals))

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
        self.assertEqual(result["strategies"]["agile"]["total_time"]["mean"], result["strategies"]["agile"]["mean_review_count"] * 2)
        self.assertEqual(result["strategies"]["waterfall"]["total_time"]["mean"], 4)
        self.assertEqual(
            result["comparison"]["mean_percent_saved"],
            100 * result["comparison"]["mean_time_saved"] / result["strategies"]["waterfall"]["total_time"]["mean"],
        )

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
