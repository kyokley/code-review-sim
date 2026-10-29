"""Focused interface tests for the command-line application."""

import contextlib
import csv
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from code_review_sim import cli
from code_review_sim.model import SimulationConfig


def sample_result():
    strategy = {
        "blocks": [4000],
        "mean_writing_time": 4000.0,
        "mean_review_time": 1000.0,
        "mean_revision_time": 0.0,
        "mean_rereview_time": 0.0,
        "mean_revised_lines": 0.0,
        "mean_review_count": 1.0,
        "total_time": {"mean": 5000.0, "stdev": 0.0, "p05": 5000.0, "p50": 5000.0, "p95": 5000.0},
    }
    delayed = dict(strategy, blocks=[3600, 400])
    delayed["total_time"] = {"mean": 5925.0, "stdev": 0.0, "p05": 5925.0, "p50": 5925.0, "p95": 5925.0}
    return {
        "config": {"trials": 1, "seed": 42, "incremental_block_size": 100},
        "strategies": {"incremental": strategy, "delayed": delayed},
        "comparison": {
            "mean_time_saved": 925.0,
            "mean_percent_saved": 15.61181434599156,
            "paired_savings_ci95": None,
            "incremental_win_probability": 1.0,
            "tie_probability": 0.0,
        },
    }


class CliTests(unittest.TestCase):
    def invoke_with_engine(self, argv, runner):
        module = types.ModuleType("code_review_sim.simulation")
        module.run_simulation = runner
        output = io.StringIO()
        with patch.dict(sys.modules, {"code_review_sim.simulation": module}), contextlib.redirect_stdout(output):
            status = cli.main(argv)
        return status, output.getvalue()

    def test_default_arguments(self):
        captured = []

        def run(config):
            captured.append(config)
            return sample_result()

        status, output = self.invoke_with_engine([], run)
        self.assertEqual(status, 0)
        self.assertEqual(captured, [SimulationConfig()])
        self.assertIn("normalized time units", output)
        self.assertIn("Mean savings", output)
        self.assertIn("Model caveat", output)

    def test_custom_arguments_map_to_config(self):
        captured = []
        self.invoke_with_engine(
            ["--trials", "9", "--seed", "7", "--block-size", "250",
             "--revision-probability", ".2", "--write-time-per-line", "2",
             "--review-time-per-line", ".5", "--revision-time-per-line", "3",
             "--review-setup-time", "4"],
            lambda config: captured.append(config) or sample_result(),
        )
        self.assertEqual(captured, [SimulationConfig(9, 7, 250, .2, 2, .5, 3, 4)])

    def test_json_and_csv_exports(self):
        result = sample_result()
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory, "result.json")
            csv_path = Path(directory, "summary.csv")
            self.invoke_with_engine(["--json", str(json_path), "--csv", str(csv_path)], lambda _: result)
            self.assertEqual(json.loads(json_path.read_text()), result)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["strategy"] for row in rows], ["incremental", "delayed"])
            self.assertEqual(rows[0]["total_time_mean"], "5000.0")
            self.assertEqual(rows[1]["total_time_p95"], "5925.0")

    def test_engine_validation_error_is_argparse_error(self):
        stderr = io.StringIO()
        module = types.ModuleType("code_review_sim.simulation")
        module.run_simulation = lambda _: (_ for _ in ()).throw(ValueError("trials must be positive"))
        with patch.dict(sys.modules, {"code_review_sim.simulation": module}), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                cli.main([])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("error: trials must be positive", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_export_io_failure_is_argparse_error(self):
        stderr = io.StringIO()
        module = types.ModuleType("code_review_sim.simulation")
        module.run_simulation = lambda _: sample_result()
        with patch.dict(sys.modules, {"code_review_sim.simulation": module}), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--json", "/missing-directory/result.json"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("error:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_module_entry_point_help_does_not_import_engine(self):
        result = subprocess.run(
            [sys.executable, "-m", "code_review_sim", "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--block-size", result.stdout)
        self.assertIn("--json PATH", result.stdout)


if __name__ == "__main__":
    unittest.main()
