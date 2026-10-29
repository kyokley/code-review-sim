# Code review Monte Carlo simulator

A dependency-free Python application comparing agile code review with
waterfall reviews started after 90% of a project is written. Projects contain
4,000 lines by default; set `--total-lines` to change the size.

Requires Python 3.10 or newer. Run from this directory:

```sh
python3 -m code_review_sim
python3 -m code_review_sim --help
```

Optional installation provides the `code-review-sim` command:

```sh
python3 -m pip install .
code-review-sim --trials 10000 --seed 42
```

## Experiments

The default experiment runs 1,000 paired trials with agile reviews whose
nominal block size is 200 lines and a 10% probability that each line needs
revision.

```sh
# Compare blocks with a nominal mean of 250 lines against waterfall reviews.
python3 -m code_review_sim --trials 10000 --seed 42 --block-size 250

# Change the revision probability and effort assumptions.
python3 -m code_review_sim --revision-probability 0.2 \
  --write-time-per-line 1 --review-time-per-line 0.25 \
  --revision-time-per-line 2 --review-setup-time 5

# Export machine-readable results while printing the comparison.
python3 -m code_review_sim --json results.json --csv results.csv

# Generate a self-contained visual report.
python3 -m code_review_sim --html report.html

# Run 10,000 trials for a 5,000-line project and generate its report.
python3 -m code_review_sim --trials 10000 --seed 42 --total-lines 5000 \
  --html report.html

# Deterministic sanity check: no revision work.
python3 -m code_review_sim --trials 1 --revision-probability 0
```

With the final command, writing contributes 4,000 units to each strategy.
Waterfall effort is **5,925 time units**: initial review contributes 1,925.
Agile effort depends on the sampled partition; its zero-revision review cost is
computed from each sampled block.

## What the model assumes

Each trial creates `total_lines` original lines (4,000 by default). Agile
review sizes are sampled from `Binomial(2 * agile_block_size, 0.5)`.
The configured size is the uncapped
distribution mean. Zero-sized samples are redrawn to ensure progress, and a
final positive sample is capped at the remaining lines. Agile partitions are
sampled anew for every trial. Waterfall reviews cover the first 90% of the
project, rounded down, and then the remaining lines. For 4,000 lines, those
reviews cover 3,600 and 400 lines.

Initial review cost is proportional to block size:

| Block size | Base review-time multiplier |
| --- | ---: |
| 1–100 lines | 1× |
| 101–500 lines | 1.25× |
| 501–1,000 lines | 1.5× |
| More than 1,000 lines | 2× |

After each initial review, each line independently needs revision with the
configured probability. A block's revision count therefore follows a binomial
distribution. Strategies share the same random per-line outcomes within each
trial, so they review equally difficult code. A fixed seed reproduces a run
in the same Python environment.

Revisions change existing lines; they do not increase the original code target.
Revised lines receive one follow-up review, using their own block size and
the same multipliers. That follow-up is assumed accepted. Blocks with no
revisions need no follow-up. Optional setup effort applies to every initial
and nonempty follow-up review.

Default costs are illustrative **normalized time units**, not measured hours:
writing costs 1 unit/line, base review costs 0.25 units/line, revision costs
1 unit/line, and setup costs 0. Set all rates to measured minutes/line to
interpret results in minutes instead.

The simulation reports **serial total effort**, not calendar duration or
parallel reviewer/developer scheduling. It does not assume late feedback
causes extra defects, dependency rework, or more expensive revisions. Shared
revision outcomes mean writing and revision effort are identical across the
paired strategies; review batching and setup costs drive their differences.
Higher setup costs can offset the advantage of small review blocks.

## Reading the results

- Each strategy reports mean total effort, standard deviation, and the
  5th, 50th, and 95th percentiles of simulated total effort.
- Component means separate writing, initial review, revision, and follow-up
  review effort. Review counts include follow-ups.
- Time saved is **waterfall effort minus agile effort**. Positive means
  agile reviews require less effort; negative means they require more.
- Percentage saved divides mean paired savings by waterfall mean total effort.
- The 95% confidence interval describes uncertainty in **mean paired savings**,
  using a normal approximation. It is not the range containing 95% of projects,
  and is unavailable for one trial. More trials reduce Monte Carlo noise, not
  uncertainty in the assumptions.
- Win probability is the fraction of trials where agile effort is
  strictly lower. Ties are reported separately.

JSON contains configuration, both strategy summaries, per-review-ordinal
average lifecycle data (`average_run` for each strategy), and comparison
statistics. Agile `blocks` and `average_run` rows are averages across trials,
not a single partition. Missing ordinal reviews contribute zero lines and
effort, with their boundaries at `total_lines`.
CSV contains one flattened summary row per strategy. Neither export contains
individual trial records.

## Visual reports

```sh
python3 -m code_review_sim --trials 10000 --seed 42 \
  --html report.html --json results.json --csv results.csv
```

Open `report.html` in a web browser. The report works offline, needs no server
or plotting packages, and contains:

- Mean effort broken down into writing, initial review, revision, and follow-up
  review, with comparable scales for both strategies.
- An embedded average-run timeline image for each method, showing writing,
  review, revision, and follow-up review in their lifecycle order.
- The 5th, 50th, and 95th percentiles of total simulated effort.
- Paired mean savings, their 95% confidence interval when available, and
  win/tie probabilities.
- The experiment configuration and model assumptions needed to interpret it.

HTML, JSON, and CSV exports from one command use the same simulation results.
The charts show summary statistics, not individual trials or a reconstructed
probability distribution. Percentile ranges describe variation across trials;
the confidence interval describes uncertainty in mean paired savings.

The average-run images use mean effort by review ordinal across the same
trials. They are not selected individual trials, and average block sizes,
boundaries, and revision counts can be fractional. Missing trailing reviews
contribute zero effort and use the project end as both boundaries. Both methods
share an effort scale; code-progress milestones identify when reviews start.
Waterfall review first starts after 90% of the original lines, then covers the
remainder. For 4,000 lines, its boundary is 3,600. A final agile block may be
shorter than its nominal mean.

Regenerate existing HTML reports with `--html report.html` to include the new
images. Legacy summary dictionaries without block averages still render the
other charts, but cannot supply average-run images.

These experiments compare the stated assumptions; they do not establish a
universal best code review process. See [SPEC.md](SPEC.md) for the model contract.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
