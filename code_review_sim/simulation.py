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

    for name in ("trials", "incremental_block_size", "seed"):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if config.trials <= 0:
        raise ValueError("trials must be positive")
    if not 1 <= config.incremental_block_size <= TOTAL_LINES:
        raise ValueError("incremental_block_size must be between 1 and 4000")
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


def _blocks(size):
    return [min(size, TOTAL_LINES - start) for start in range(0, TOTAL_LINES, size)]


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
    incremental_blocks = _blocks(config.incremental_block_size)
    delayed_blocks = [3600, 400]
    strategies = {
        "incremental": {
            "blocks": incremental_blocks,
            "block_sums": [
                {
                    "start_line": sum(incremental_blocks[:index]),
                    "end_line": sum(incremental_blocks[: index + 1]),
                    "line_count": size,
                    "writing_time": 0.0,
                    "review_time": 0.0,
                    "revision_time": 0.0,
                    "rereview_time": 0.0,
                    "revised_lines": 0.0,
                }
                for index, size in enumerate(incremental_blocks)
            ],
            "writing": [],
            "review": [],
            "revision": [],
            "rereview": [],
            "revised": [],
            "review_count": [],
            "total": [],
        },
        "delayed": {
            "blocks": delayed_blocks,
            "block_sums": [
                {
                    "start_line": sum(delayed_blocks[:index]),
                    "end_line": sum(delayed_blocks[: index + 1]),
                    "line_count": size,
                    "writing_time": 0.0,
                    "review_time": 0.0,
                    "revision_time": 0.0,
                    "rereview_time": 0.0,
                    "revised_lines": 0.0,
                }
                for index, size in enumerate(delayed_blocks)
            ],
            "writing": [],
            "review": [],
            "revision": [],
            "rereview": [],
            "revised": [],
            "review_count": [],
            "total": [],
        },
    }

    rng = random.Random(config.seed)
    for _ in range(config.trials):
        # One shared vector preserves paired per-line revisions across partitions.
        revision_flags = [rng.random() < config.revision_probability for _ in range(TOTAL_LINES)]
        for name, block_sizes in (("incremental", incremental_blocks), ("delayed", delayed_blocks)):
            result = strategies[name]
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
                block["writing_time"] += size * config.write_time_per_line
                block["review_time"] += initial_block_review
                block["revision_time"] += revised * config.revision_time_per_line
                block["rereview_time"] += rereview_block
                block["revised_lines"] += revised

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
        output_strategies[name] = {
            "blocks": result["blocks"],
            "average_run": [
                {
                    "start_line": block["start_line"],
                    "end_line": block["end_line"],
                    "line_count": block["line_count"],
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

    incremental_totals = strategies["incremental"]["total"]
    delayed_totals = strategies["delayed"]["total"]
    paired_savings = [delayed - incremental for delayed, incremental in zip(delayed_totals, incremental_totals)]
    mean_saved = statistics.mean(paired_savings)
    delayed_mean = statistics.mean(delayed_totals)
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
            "mean_percent_saved": 100 * mean_saved / delayed_mean if delayed_mean else 0.0,
            "paired_savings_ci95": confidence_interval,
            "incremental_win_probability": sum(value > 0 for value in paired_savings) / config.trials,
            "tie_probability": sum(value == 0 for value in paired_savings) / config.trials,
        },
    }
