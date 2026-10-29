"""Monte Carlo engine for the code review effort model."""

import math
import random
import statistics
from dataclasses import fields

from .model import SimulationConfig


TOTAL_LINES = 4000


def review_multiplier(lines):
    """Return the review-effort multiplier for a block of ``lines`` lines."""
    if lines <= 100:
        return 1.0
    if lines <= 500:
        return 1.25
    if lines <= 1000:
        return 1.5
    return 2.0


def _validate_config(config):
    if not isinstance(config, SimulationConfig):
        raise ValueError("config must be a SimulationConfig")

    for name in ("trials", "agile_block_size", "seed"):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if config.trials <= 0:
        raise ValueError("trials must be positive")
    if not 1 <= config.agile_block_size <= TOTAL_LINES:
        raise ValueError("agile_block_size must be between 1 and 4000")
    if not isinstance(config.revision_probability, (int, float)) or isinstance(
        config.revision_probability, bool
    ):
        raise ValueError("revision_probability must be a finite number in [0, 1]")
    if not math.isfinite(config.revision_probability) or not 0 <= config.revision_probability <= 1:
        raise ValueError("revision_probability must be a finite number in [0, 1]")
    for name in (
        "write_time_per_line",
        "review_time_per_line",
        "revision_time_per_line",
        "review_setup_time",
    ):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be finite and nonnegative")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")


def _sample_binomial(rng, trials, probability=0.5):
    """Sample a binomial count using Python 3.10-compatible Bernoulli draws."""
    return sum(rng.random() < probability for _ in range(trials))


def _sample_agile_blocks(rng, mean_block_size, total_lines=TOTAL_LINES):
    """Draw positive binomial blocks until they cover the original code."""
    blocks = []
    remaining = total_lines
    while remaining:
        size = 0
        while size == 0:
            size = _sample_binomial(rng, 2 * mean_block_size)
        size = min(size, remaining)
        blocks.append(size)
        remaining -= size
    return blocks


def _block_accumulator():
    return {
        "start_line": 0.0,
        "end_line": 0.0,
        "line_count": 0.0,
        "writing_time": 0.0,
        "review_time": 0.0,
        "revision_time": 0.0,
        "rereview_time": 0.0,
        "revised_lines": 0.0,
    }


def _review_cost(lines, config):
    if lines == 0:
        return 0.0
    return (
        lines * config.review_time_per_line * review_multiplier(lines)
        + config.review_setup_time
    )


def _summarize(values):
    ordered = sorted(values)

    def quantile(probability):
        position = (len(ordered) - 1) * probability
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return float(ordered[lower])
        return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))

    return {
        "mean": statistics.mean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "p05": quantile(0.05),
        "p50": quantile(0.50),
        "p95": quantile(0.95),
    }


def run_simulation(config):
    """Run paired review-strategy trials and return JSON-safe summaries."""
    _validate_config(config)
    waterfall_blocks = [3600, 400]
    strategies = {
        "agile": {
            "blocks": [],
            "block_sums": [],
            "writing": [],
            "review": [],
            "revision": [],
            "rereview": [],
            "revised": [],
            "review_count": [],
            "total": [],
        },
        "waterfall": {
            "blocks": waterfall_blocks,
            "block_sums": [_block_accumulator() for _ in waterfall_blocks],
            "writing": [],
            "review": [],
            "revision": [],
            "rereview": [],
            "revised": [],
            "review_count": [],
            "total": [],
        },
    }

    # Keep revision outcomes on their original stream; block sizing uses a
    # separate deterministic stream so it cannot perturb waterfall results.
    rng = random.Random(config.seed)
    agile_rng = random.Random(config.seed ^ 0x9E3779B97F4A7C15)
    for trial_index in range(config.trials):
        # One shared vector preserves paired per-line revisions across partitions.
        revision_flags = [rng.random() < config.revision_probability for _ in range(TOTAL_LINES)]
        agile_blocks = _sample_agile_blocks(agile_rng, config.agile_block_size)
        for name, block_sizes in (("agile", agile_blocks), ("waterfall", waterfall_blocks)):
            result = strategies[name]
            if name == "agile":
                while len(result["block_sums"]) < len(block_sizes):
                    block = _block_accumulator()
                    block["start_line"] = trial_index * TOTAL_LINES
                    block["end_line"] = trial_index * TOTAL_LINES
                    result["block_sums"].append(block)
            cursor = 0
            initial_review = 0.0
            revised_lines = 0
            rereview = 0.0
            review_count = 0
            for block_index, size in enumerate(block_sizes):
                revised = sum(revision_flags[cursor : cursor + size])
                cursor += size
                revised_lines += revised
                initial_block_review = _review_cost(size, config)
                rereview_block = _review_cost(revised, config)
                initial_review += initial_block_review
                review_count += 1
                rereview += rereview_block
                if revised:
                    review_count += 1

                block = result["block_sums"][block_index]
                block["start_line"] += cursor - size
                block["end_line"] += cursor
                block["line_count"] += size
                block["writing_time"] += size * config.write_time_per_line
                block["review_time"] += initial_block_review
                block["revision_time"] += revised * config.revision_time_per_line
                block["rereview_time"] += rereview_block
                block["revised_lines"] += revised

            if name == "agile":
                for block in result["block_sums"][len(block_sizes):]:
                    block["start_line"] += TOTAL_LINES
                    block["end_line"] += TOTAL_LINES

            writing = TOTAL_LINES * config.write_time_per_line
            revision = revised_lines * config.revision_time_per_line
            total = writing + initial_review + revision + rereview
            result["writing"].append(writing)
            result["review"].append(initial_review)
            result["revision"].append(revision)
            result["rereview"].append(rereview)
            result["revised"].append(revised_lines)
            result["review_count"].append(review_count)
            result["total"].append(total)

    output_strategies = {}
    for name, result in strategies.items():
        if name == "agile":
            result["blocks"] = [block["line_count"] / config.trials for block in result["block_sums"]]
        output_strategies[name] = {
            "blocks": result["blocks"],
            "average_run": [
                {
                    "start_line": block["start_line"] / config.trials,
                    "end_line": block["end_line"] / config.trials,
                    "line_count": block["line_count"] / config.trials,
                    "mean_writing_time": block["writing_time"] / config.trials,
                    "mean_review_time": block["review_time"] / config.trials,
                    "mean_revision_time": block["revision_time"] / config.trials,
                    "mean_rereview_time": block["rereview_time"] / config.trials,
                    "mean_revised_lines": block["revised_lines"] / config.trials,
                }
                for block in result["block_sums"]
            ],
            "mean_writing_time": statistics.mean(result["writing"]),
            "mean_review_time": statistics.mean(result["review"]),
            "mean_revision_time": statistics.mean(result["revision"]),
            "mean_rereview_time": statistics.mean(result["rereview"]),
            "mean_revised_lines": statistics.mean(result["revised"]),
            "mean_review_count": statistics.mean(result["review_count"]),
            "total_time": _summarize(result["total"]),
        }

    agile_totals = strategies["agile"]["total"]
    waterfall_totals = strategies["waterfall"]["total"]
    paired_savings = [waterfall - agile for waterfall, agile in zip(waterfall_totals, agile_totals)]
    mean_saved = statistics.mean(paired_savings)
    waterfall_mean = statistics.mean(waterfall_totals)
    if config.trials < 2:
        confidence_interval = None
    else:
        margin = 1.96 * statistics.stdev(paired_savings) / math.sqrt(config.trials)
        confidence_interval = [mean_saved - margin, mean_saved + margin]

    return {
        "config": {**{field.name: getattr(config, field.name) for field in fields(config)}, "total_lines": TOTAL_LINES},
        "strategies": output_strategies,
        "comparison": {
            "mean_time_saved": mean_saved,
            "mean_percent_saved": 100 * mean_saved / waterfall_mean if waterfall_mean else 0.0,
            "paired_savings_ci95": confidence_interval,
            "agile_win_probability": sum(value > 0 for value in paired_savings) / config.trials,
            "tie_probability": sum(value == 0 for value in paired_savings) / config.trials,
        },
    }
