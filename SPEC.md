# Code review Monte Carlo model

## Scope and assumptions

Each trial creates exactly 4,000 original lines. Compare incremental reviews
(100-line blocks by default, configurable) with reviews after 3,600 lines and
after the final 400 lines. Reviews and revisions are serial: reported time is
total effort, not elapsed calendar time with concurrent developers/reviewers.

A review of a block costs `lines * review_time_per_line * multiplier`, plus
optional per-review setup time. Multipliers are 1 for 1–100 lines, 1.25 for
101–500, 1.5 for 501–1,000, and 2 for more than 1,000. This resolves the
overlapping thresholds in the request using inclusive upper bounds.

After each block's initial review, each original line independently needs
revision with probability `revision_probability` (default 0.1). Thus the random
revision count is binomial. Paired strategies use the same per-line revision
flags within a trial; neither strategy gets artificially easier code.
Revising a line changes existing code, not the 4,000-line target.

Revision effort is `revised_lines * revision_time_per_line`. Revised lines form
one follow-up review block, using their own count to select its multiplier.
No follow-up review occurs when zero lines need revision. That follow-up is
assumed accepted: revisions do not recursively create more revisions.

Defaults use normalized time units: writing 1 unit/line, base review 0.25
units/line, revision 1 unit/line, setup 0 units/review. These are illustrative
inputs, not measured productivity data. All rates and setup cost are tunable.
The model assumes no added defect propagation, context-switch penalty, review
fatigue beyond the stated tiers, or benefit from earlier feedback. It tests
these assumptions; it cannot establish a universal best workflow.

## Public Python interface

`code_review_sim.model.SimulationConfig` is a frozen dataclass with fields:
`trials: int = 1000`, `seed: int = 42`, `incremental_block_size: int = 100`,
`revision_probability: float = 0.1`, `write_time_per_line: float = 1.0`,
`review_time_per_line: float = 0.25`, `revision_time_per_line: float = 1.0`,
`review_setup_time: float = 0.0`.

`code_review_sim.simulation.run_simulation(config) -> dict` returns JSON-safe
data: `config` (all fields plus `total_lines: 4000`), `strategies` (keys
`incremental` and `delayed`), and `comparison`.

Each strategy contains `blocks` (list of original block sizes),
`mean_writing_time`, `mean_review_time` (initial reviews), `mean_revision_time`,
`mean_rereview_time`, `mean_revised_lines`, `mean_review_count` (including
follow-ups), and `total_time` with `mean`, `stdev`, `p05`, `p50`, `p95`.

Comparison fields: `mean_time_saved` (delayed minus incremental),
`mean_percent_saved` (100 * mean_time_saved / delayed mean; zero if both zero),
`paired_savings_ci95` (two-element normal-approximation confidence interval
for the mean paired difference; null if trials < 2),
`incremental_win_probability`, and `tie_probability`.

Invalid configuration raises `ValueError`. Integer counts reject booleans;
block size is 1–4,000; trials is positive; seed is an integer; probability is
finite in [0, 1]; time inputs are finite and nonnegative. No third-party runtime
dependencies. Python 3.10+.

## Visual report

`code_review_sim.visualization.render_html(result) -> str` returns a complete
self-contained HTML report from the unchanged simulation summary. The CLI's
`--html PATH` writes this report as UTF-8 while retaining normal console output.
It can be combined with JSON and CSV exports without running new trials.

Visualizations compare mean effort components and total-effort p05/p50/p95
summaries, with signed paired savings, confidence intervals, and experiment
configuration. Percentile ranges must not be labeled as confidence intervals.
No raw-trial distributions are inferred from the summaries. Reports work
offline without runtime dependencies, including for zero effort, tied results,
negative incremental savings, and a single trial without a confidence interval.

## Verification ownership

Engine lane: tier boundaries, deterministic zero/full revision cases,
4,000-line conservation including partial blocks, paired fairness, input
validation, reproducibility, and uncertainty statistics. CLI lane: argument
handling, JSON/CSV exports, executable entry points, and clear failure output.
Integrator: inspect artifacts, run the full unittest suite once after lane
reconciliation, exercise documented commands, and compare a zero-revision
trial to hand-computed totals (incremental 5,000; delayed 5,925).

Visualization renderer: focused checks for metric fidelity, self-containment,
accessible chart descriptions, and valid geometry at zero effort. CLI: HTML
flag wiring, shared result identity, UTF-8 output, and concise I/O errors.
Integrator: reconcile both lanes, run full tests once, generate reports from
real default and boundary simulations, and inspect rendered reports when a
browser is available.
