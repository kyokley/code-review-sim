import html.parser
import re
import unittest

from code_review_sim.visualization import render_html


def sample_result(trials=12, saved=15.0, ci=[10.0, 20.0]):
    return {
        "config": {"trials": trials, "seed": 7, "agile_block_size": 250,
                   "revision_probability": 0.2, "write_time_per_line": 1,
                   "review_time_per_line": 0.25, "revision_time_per_line": 2,
                   "review_setup_time": 3, "total_lines": 4000},
        "strategies": {
            "agile": {"blocks": [250] * 16, "mean_writing_time": 4000,
                "mean_review_time": 1100, "mean_revision_time": 1600,
                "mean_rereview_time": 200, "mean_revised_lines": 800,
                "mean_review_count": 32, "total_time": {"mean": 6900, "stdev": 30,
                    "p05": 6840, "p50": 6900, "p95": 6960}},
            "waterfall": {"blocks": [3600, 400], "mean_writing_time": 4000,
                "mean_review_time": 1900, "mean_revision_time": 1600,
                "mean_rereview_time": 400, "mean_revised_lines": 800,
                "mean_review_count": 4, "total_time": {"mean": 7900, "stdev": 50,
                    "p05": 7800, "p50": 7900, "p95": 8000}},
        },
        "comparison": {"mean_time_saved": saved, "mean_percent_saved": saved / 79,
            "paired_savings_ci95": ci, "agile_win_probability": 0.6,
            "tie_probability": 0.1},
    }


class SvgParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.svg = 0
        self.rects = 0
        self.invalid = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "svg": self.svg += 1
        if tag in ("rect", "line", "circle"):
            if tag == "rect": self.rects += 1
            for key, value in attrs.items():
                if key in {"x", "y", "width", "height", "cx", "cy", "r", "x1", "x2", "y1", "y2"}:
                    if value and not re.fullmatch(r"-?\d+(?:\.\d+)?", value): self.invalid.append(value)
                    elif value and abs(float(value)) > 1e8: self.invalid.append(value)


class VisualizationTests(unittest.TestCase):
    def test_average_run_timelines_are_paired_accessible_and_on_common_scale(self):
        result = sample_result()
        def block(start, end, write, review, revise, rereview, revised):
            return {"start_line": start, "end_line": end, "line_count": end-start,
                    "mean_writing_time": write, "mean_review_time": review,
                    "mean_revision_time": revise, "mean_rereview_time": rereview,
                    "mean_revised_lines": revised}
        result["strategies"]["agile"]["average_run"] = [
            block(0, 100, 100, 25, 10, 3, 10),
            block(100, 200, 100, 25, 10, 3, 10),
        ]
        result["strategies"]["waterfall"]["average_run"] = [
            block(0, 3600, 3600, 1800, 360, 100, 360),
            block(3600, 4000, 400, 100, 40, 10, 40),
        ]
        result["strategies"]["agile"].update(
            mean_writing_time=200, mean_review_time=50,
            mean_revision_time=20, mean_rereview_time=6,
        )
        result["strategies"]["agile"]["total_time"]["mean"] = 276
        result["strategies"]["waterfall"].update(
            mean_writing_time=4000, mean_review_time=1900,
            mean_revision_time=400, mean_rereview_time=110,
        )
        result["strategies"]["waterfall"]["total_time"]["mean"] = 6410
        source = render_html(result)
        self.assertIn("<h3>Agile</h3>", source)
        self.assertIn("<h3>Waterfall</h3>", source)
        self.assertIn("Waterfall minus agile", source)
        self.assertIn("Agile Block Size", source)
        parser = SvgParser(); parser.feed(source)
        self.assertEqual(parser.svg, 4)
        for svg_id in ("agile-timeline", "waterfall-timeline"):
            self.assertRegex(source, rf'<svg id="{svg_id}"[^>]+role="img"')
        self.assertIn("averages across trials", source)
        self.assertIn("0–100", source)
        self.assertIn("0–3600 lines", source)
        self.assertIn("3600–4000 lines", source)
        self.assertIn("data-start=\"3600\"", source)
        self.assertIn("data-effort-end=\"276\"", source)
        self.assertIn("data-effort-end=\"6410\"", source)
        self.assertEqual(source.count('data-effort-scale="6410"'), 2)
        self.assertIn("Writing → Initial review → Revision → Follow-up review", source)
        self.assertEqual(parser.invalid, [])

    def test_legacy_summary_has_no_fabricated_lifecycle_images(self):
        source = render_html(sample_result())
        self.assertNotIn('id="agile-timeline"', source)
        self.assertNotIn('id="waterfall-timeline"', source)
        self.assertIn("Average lifecycle timeline unavailable", source)

    def test_agile_random_block_averages_preserve_fractional_progress(self):
        result = sample_result()
        def block(start, end, count, writing):
            return {"start_line": start, "end_line": end, "line_count": count,
                    "mean_writing_time": writing, "mean_review_time": 0,
                    "mean_revision_time": 0, "mean_rereview_time": 0,
                    "mean_revised_lines": 0}
        result["strategies"]["agile"]["average_run"] = [
            block(0, 199.5, 199.5, 199.5), block(199.5, 4000, 3800.5, 3800.5),
        ]
        result["strategies"]["waterfall"]["average_run"] = [
            block(0, 3600, 3600, 3600), block(3600, 4000, 400, 400),
        ]
        source = render_html(result)
        self.assertIn('data-start="0" data-end="199.5"', source)
        self.assertIn('data-start="199.5" data-end="4000"', source)
        self.assertIn("lines 0–199.5", source)
        self.assertIn("199.5–4000 lines", source)
        self.assertIn("mean review ordinal 1, lines 0–199.5", source)
        self.assertIn("mean review-ordinal blocks, not a fixed partition", source)
        self.assertIn("fresh random binomial sizes with nominal mean", source)
        self.assertIn("Agile Block Size (nominal mean)", source)
        self.assertIn('data-effort-end="4000"', source)
        self.assertEqual(source.count('data-effort-scale="4000"'), 2)
        parser = SvgParser(); parser.feed(source)
        self.assertEqual(parser.invalid, [])

    def test_zero_effort_and_zero_revision_timeline_geometry(self):
        result = sample_result(1)
        zero_block = {"start_line": 0, "end_line": 4000, "line_count": 4000,
                      "mean_writing_time": 0, "mean_review_time": 0,
                      "mean_revision_time": 0, "mean_rereview_time": 0,
                      "mean_revised_lines": 0}
        for strategy in result["strategies"].values():
            strategy["average_run"] = [zero_block]
            strategy["mean_writing_time"] = strategy["mean_review_time"] = 0
            strategy["mean_revision_time"] = strategy["mean_rereview_time"] = 0
            strategy["total_time"] = {"mean": 0, "stdev": 0, "p05": 0, "p50": 0, "p95": 0}
        parser = SvgParser(); parser.feed(render_html(result))
        self.assertEqual(parser.invalid, [])
        self.assertEqual(parser.svg, 4)

    def test_metrics_configuration_and_self_contained_accessible_report(self):
        source = render_html(sample_result())
        self.assertIn("<!doctype html>", source.lower())
        self.assertIn("6900", source)
        self.assertIn("7800", source)
        self.assertIn("6960", source)
        self.assertIn("15", source)
        self.assertIn("250", source)
        self.assertIn("0.2", source)
        self.assertIn("95% confidence interval", source)
        self.assertIn("Win probability", source)
        self.assertIn("serial total effort", source.lower())
        self.assertIn("normalized time units", source.lower())
        self.assertNotRegex(source, r"https?://|<script")
        self.assertIn("@media print", source)
        self.assertRegex(source, r"<svg[^>]+role=\"img\"")

    def test_svg_is_parseable_and_geometry_finite_for_zero_and_single_trial(self):
        result = sample_result(1, -25, None)
        for strategy in result["strategies"].values():
            for key in ("mean_writing_time", "mean_review_time", "mean_revision_time", "mean_rereview_time"):
                strategy[key] = 0
            strategy["total_time"] = {"mean": 0, "stdev": 0, "p05": 0, "p50": 0, "p95": 0}
        source = render_html(result)
        parser = SvgParser(); parser.feed(source)
        self.assertGreaterEqual(parser.svg, 2)
        self.assertGreater(parser.rects, 0)
        self.assertEqual(parser.invalid, [])
        self.assertIn("Not available", source)
        self.assertIn("−25", source)

    def test_escapes_dynamic_configuration(self):
        result = sample_result()
        result["config"]["label"] = '<img src=x onerror="bad">'
        result["config"]["revision_probability"] = 0.000123
        source = render_html(result)
        self.assertIn("&lt;img src=x onerror=&quot;bad&quot;&gt;", source)
        self.assertNotIn('<img src=x', source)
        self.assertIn("<dd>0.000123</dd>", source)

    def test_close_and_equal_quantiles_keep_exact_labels_separate(self):
        result = sample_result()
        result["strategies"]["agile"]["total_time"].update(
            p05=6900, p50=6900, p95=6900
        )
        result["strategies"]["waterfall"]["total_time"].update(
            p05=7900, p50=7901, p95=7902
        )
        source = render_html(result)
        self.assertIn("p05 6900", source)
        self.assertIn("p50 6900", source)
        self.assertIn("p95 6900", source)
        self.assertIn("p05 7900", source)
        self.assertIn("p50 7901", source)
        self.assertIn("p95 7902", source)
        self.assertIn("not zero-based", source)
        parser = SvgParser(); parser.feed(source)
        self.assertEqual(parser.invalid, [])
        # Exact table labels and figures keep component meaning independent of color.
        self.assertIn("Mean component effort (time units)", source)
        self.assertIn("<td>1100</td>", source)
        comparison = source.split('<section class="metric"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(comparison.count("<div>"), comparison.count("</div>"))

    def test_large_finite_values_have_finite_svg_geometry(self):
        result = sample_result()
        large = 1e200
        for strategy in result["strategies"].values():
            strategy["total_time"] = {"mean": large, "stdev": 0, "p05": large,
                                      "p50": large, "p95": large}
            strategy["mean_writing_time"] = large
            strategy["mean_review_time"] = 0
            strategy["mean_revision_time"] = 0
            strategy["mean_rereview_time"] = 0
        parser = SvgParser(); parser.feed(render_html(result))
        self.assertEqual(parser.invalid, [])


if __name__ == "__main__":
    unittest.main()
