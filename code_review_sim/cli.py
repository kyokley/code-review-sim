"""Command-line interface for the code review simulation."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .model import SimulationConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-review-sim",
        description="Compare agile and waterfall code review effort.",
    )
    parser.add_argument("--trials", type=int, default=1000, help="number of trials (default: 1000)")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    parser.add_argument(
        "--block-size", type=int, default=100,
        help="agile review block size in lines (default: 100)",
    )
    parser.add_argument(
        "--revision-probability", type=float, default=0.1,
        help="per-line revision probability (default: 0.1)",
    )
    parser.add_argument(
        "--write-time-per-line", type=float, default=1.0,
        help="writing time per line (default: 1.0)",
    )
    parser.add_argument(
        "--review-time-per-line", type=float, default=0.25,
        help="base review time per line (default: 0.25)",
    )
    parser.add_argument(
        "--revision-time-per-line", type=float, default=1.0,
        help="revision time per line (default: 1.0)",
    )
    parser.add_argument(
        "--review-setup-time", type=float, default=0.0,
        help="setup time per review (default: 0.0)",
    )
    parser.add_argument("--json", metavar="PATH", help="write exact simulation result as JSON")
    parser.add_argument("--csv", metavar="PATH", help="write per-strategy summary as CSV")
    parser.add_argument("--html", metavar="PATH", help="write a self-contained visual report as HTML")
    return parser


def _csv_rows(result: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    fields = [
        "strategy", "blocks", "mean_writing_time", "mean_review_time",
        "mean_revision_time", "mean_rereview_time", "mean_revised_lines",
        "mean_review_count", "total_time_mean", "total_time_stdev",
        "total_time_p05", "total_time_p50", "total_time_p95",
    ]
    for name, strategy in result["strategies"].items():
        row = {
            "strategy": name,
            "blocks": json.dumps(strategy["blocks"], separators=(",", ":")),
            "mean_writing_time": strategy["mean_writing_time"],
            "mean_review_time": strategy["mean_review_time"],
            "mean_revision_time": strategy["mean_revision_time"],
            "mean_rereview_time": strategy["mean_rereview_time"],
            "mean_revised_lines": strategy["mean_revised_lines"],
            "mean_review_count": strategy["mean_review_count"],
        }
        row.update({f"total_time_{key}": value for key, value in strategy["total_time"].items()})
        rows.append(row)
    return fields, rows


def _write_json(path: str, result: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


def _write_csv(path: str, result: dict[str, Any]) -> None:
    fields, rows = _csv_rows(result)
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _print_report(result: dict[str, Any], stream: Any = None) -> None:
    if stream is None:
        stream = sys.stdout
    print("Code review effort comparison (normalized time units)", file=stream)
    print(
        f"{'Strategy':<12} {'Mean total':>12} {'p05':>12} {'p50':>12} {'p95':>12}"
        f" {'Writing':>12} {'Review':>12} {'Revision':>12} {'Rereview':>12}",
        file=stream,
    )
    for name, strategy in result["strategies"].items():
        total = strategy["total_time"]
        print(
            f"{name:<12} {total['mean']:>12.2f} {total['p05']:>12.2f}"
            f" {total['p50']:>12.2f} {total['p95']:>12.2f}"
            f" {strategy['mean_writing_time']:>12.2f}"
            f" {strategy['mean_review_time']:>12.2f}"
            f" {strategy['mean_revision_time']:>12.2f}"
            f" {strategy['mean_rereview_time']:>12.2f}",
            file=stream,
        )
    comparison = result["comparison"]
    interval = comparison["paired_savings_ci95"]
    interval_text = "unavailable" if interval is None else f"[{interval[0]:.2f}, {interval[1]:.2f}]"
    print(
        f"Mean savings (waterfall - agile): {comparison['mean_time_saved']:.2f} "
        f"({comparison['mean_percent_saved']:.2f}%); paired 95% CI: {interval_text}",
        file=stream,
    )
    print(
        f"Agile win probability: {comparison['agile_win_probability']:.1%}; "
        f"tie probability: {comparison['tie_probability']:.1%}",
        file=stream,
    )
    print(
        "Model caveat: illustrative assumptions only; this comparison cannot "
        "establish a universally best workflow.",
        file=stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    config = SimulationConfig(
        trials=args.trials,
        seed=args.seed,
        agile_block_size=args.block_size,
        revision_probability=args.revision_probability,
        write_time_per_line=args.write_time_per_line,
        review_time_per_line=args.review_time_per_line,
        revision_time_per_line=args.revision_time_per_line,
        review_setup_time=args.review_setup_time,
    )

    try:
        # Import lazily so --help works without loading the simulation engine.
        from .simulation import run_simulation

        result = run_simulation(config)
        if args.json:
            _write_json(args.json, result)
        if args.csv:
            _write_csv(args.csv, result)
        if args.html:
            from .visualization import render_html

            Path(args.html).write_text(render_html(result), encoding="utf-8")
        _print_report(result)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
