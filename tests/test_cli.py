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
from code_review_sim.simulation import run_simulation


def sample_result():
    strategy = {
        "blocks": [2000.25, 1999.75],
        "mean_writing_time": 4000.0,
        "mean_review_time": 1000.0,
        "mean_revision_time": 0.0,
        "mean_rereview_time": 0.0,
        "mean_revised_lines": 0.0,
        "mean_review_count": 1.0,
        "total_time": {"mean": 5000.0, "stdev": 0.0, "p05": 5000.0, "p50": 5000.0, "p95": 5000.0},
    }
    waterfall = dict(strategy, blocks=[3600, 400])
    waterfall["total_time"] = {"mean": 5925.0, "stdev": 0.0, "p05": 5925.0, "p50": 5925.0, "p95": 5925.0}
    return {
        "config": {"trials": 1, "seed": 42, "agile_block_size": 200},
        "strategies": {"agile": strategy, "waterfall": waterfall},
        "comparison": {
            "mean_time_saved": 925.0,
            "mean_percent_saved": 15.61181434599156,
            "paired_savings_ci95": None,
            "agile_win_probability": 1.0,
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
            ["--trials", "9", "--seed", "7", "--block-size", "250", "--total-lines", "5000",
             "--revision-probability", ".2", "--write-time-per-line", "2",
             "--review-time-per-line", ".5", "--revision-time-per-line", "3",
             "--review-setup-time", "4"],
            lambda config: captured.append(config) or sample_result(),
        )
        self.assertEqual(captured, [SimulationConfig(9, 7, 250, .2, 2, .5, 3, 4, 5000)])

    def test_json_and_csv_exports(self):
        result = sample_result()
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory, "result.json")
            csv_path = Path(directory, "summary.csv")
            self.invoke_with_engine(["--json", str(json_path), "--csv", str(csv_path)], lambda _: result)
            self.assertEqual(json.loads(json_path.read_text()), result)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["strategy"] for row in rows], ["agile", "waterfall"])
            self.assertEqual(rows[0]["total_time_mean"], "5000.0")
            self.assertEqual(rows[1]["total_time_p95"], "5925.0")
            self.assertEqual(json.loads(rows[0]["blocks"]), [2000.25, 1999.75])

    def test_exports_preserve_simulated_mean_agile_blocks(self):
        result = run_simulation(SimulationConfig(trials=5, seed=73))
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory, "result.json")
            csv_path = Path(directory, "summary.csv")
            self.invoke_with_engine(
                ["--json", str(json_path), "--csv", str(csv_path)],
                lambda _: result,
            )
            exported = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["strategies"]["agile"]["blocks"], result["strategies"]["agile"]["blocks"])
            self.assertAlmostEqual(sum(exported["strategies"]["agile"]["blocks"]), 4000)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(
                json.loads(rows[0]["blocks"]),
                result["strategies"]["agile"]["blocks"],
            )

    def test_5000_line_cli_exports_preserve_dynamic_waterfall(self):
        config = SimulationConfig(trials=2, seed=73, total_lines=5000)
        result = run_simulation(config)
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory, "result.json")
            csv_path = Path(directory, "summary.csv")
            self.invoke_with_engine(
                ["--total-lines", "5000", "--json", str(json_path), "--csv", str(csv_path)],
                lambda _: result,
            )
            exported = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(exported["config"]["total_lines"], 5000)
            self.assertEqual(exported["strategies"]["waterfall"]["blocks"], [4500, 500])
            self.assertAlmostEqual(sum(exported["strategies"]["agile"]["blocks"]), 5000)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(json.loads(rows[1]["blocks"]), [4500, 500])

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
        self.assertIn("Compare agile and waterfall", result.stdout)
        self.assertIn("--block-size", result.stdout)
        self.assertIn("nominal agile review block size", result.stdout)
        self.assertIn("average this many lines", result.stdout)
        self.assertIn("default: 200", result.stdout)
        self.assertIn("--total-lines TOTAL_LINES", result.stdout)
        self.assertIn("default: 4000", result.stdout)
        self.assertIn("--json PATH", result.stdout)

    def test_new_strategy_terms_are_exposed_in_cli_and_exports(self):
        result = sample_result()
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory, "summary.csv")
            status, output = self.invoke_with_engine([], lambda _: result)
            self.assertEqual(status, 0)
            self.assertIn("agile", output)
            self.assertIn("waterfall", output)
            self.invoke_with_engine(["--csv", str(csv_path)], lambda _: result)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["strategy"] for row in rows], ["agile", "waterfall"])

    def test_html_help_mentions_path(self):
        result = subprocess.run(
            [sys.executable, "-m", "code_review_sim", "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--html PATH", result.stdout)

    def test_html_renderer_receives_result_and_writes_utf8(self):
        result = sample_result()
        observed = []
        renderer = types.ModuleType("code_review_sim.visualization")

        def render_html(value):
            observed.append(value)
            return "<html>café</html>"

        renderer.render_html = render_html
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory, "report.html")
            json_path = Path(directory, "result.json")
            csv_path = Path(directory, "summary.csv")
            simulation = types.ModuleType("code_review_sim.simulation")
            simulation.run_simulation = lambda _: result
            output = io.StringIO()
            with patch.dict(sys.modules, {
                "code_review_sim.simulation": simulation,
                "code_review_sim.visualization": renderer,
            }), contextlib.redirect_stdout(output):
                status = cli.main([
                    "--json", str(json_path), "--csv", str(csv_path), "--html", str(html_path),
                ])
            self.assertEqual(status, 0)
            self.assertEqual(observed, [result])
            self.assertIs(observed[0], result)
            self.assertEqual(html_path.read_text(encoding="utf-8"), "<html>café</html>")
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), result)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)
            self.assertIn("Code review effort comparison", output.getvalue())

    def test_html_renderer_not_loaded_for_plain_run(self):
        # A plain run must work even when the optional renderer cannot import.
        with patch.dict(sys.modules, {"code_review_sim.visualization": None}):
            status, _ = self.invoke_with_engine([], lambda _: sample_result())
        self.assertEqual(status, 0)

    def test_html_io_failure_is_argparse_error(self):
        stderr = io.StringIO()
        simulation = types.ModuleType("code_review_sim.simulation")
        simulation.run_simulation = lambda _: sample_result()
        renderer = types.ModuleType("code_review_sim.visualization")
        renderer.render_html = lambda _: "<html></html>"
        with patch.dict(sys.modules, {
            "code_review_sim.simulation": simulation,
            "code_review_sim.visualization": renderer,
        }), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--html", "/missing-directory/report.html"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("error:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
