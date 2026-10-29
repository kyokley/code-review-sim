"""Self-contained HTML rendering for simulation summaries."""

import html
import math


_COMPONENTS = (
    ("Writing", "mean_writing_time", "#173b52"),
    ("Initial review", "mean_review_time", "#168b83"),
    ("Revision", "mean_revision_time", "#d98745"),
    ("Follow-up review", "mean_rereview_time", "#8b6bb1"),
)


def _text(value):
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return html.escape(str(value), quote=True)


def _num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _raw_num(value):
    return format(_num(value), ".15g")


def _svg(result):
    strategies = result["strategies"]
    totals = [max(0.0, _num(s["total_time"]["mean"])) for s in strategies.values()]
    maximum = max(totals, default=0.0)
    # Keep room at the right for the total label, even when the bar is maximal.
    scale = 480 / maximum if maximum else 0
    parts = ['<svg viewBox="0 0 720 184" role="img" aria-labelledby="effort-title effort-desc"><title id="effort-title">Mean effort by component</title><desc id="effort-desc">Stacked bars compare mean writing, initial review, revision, and follow-up review effort. Shared horizontal scale starts at zero.</desc>']
    for index, (name, strategy) in enumerate(strategies.items()):
        y = 40 + index * 66
        parts.append(f'<text x="8" y="{y+17}" class="svg-label">{html.escape(name.title())}</text>')
        x = 145
        for label, key, color in _COMPONENTS:
            width = max(0.0, _num(strategy.get(key, 0))) * scale
            parts.append(f'<rect x="{x:.3f}" y="{y}" width="{width:.3f}" height="28" fill="{color}" stroke="#fff" stroke-width="1"><title>{html.escape(name.title())} — {label}: {_text(strategy.get(key, 0))}</title></rect>')
            x += width
        parts.append(f'<text x="{min(704, max(155, x+7)):.3f}" y="{y+18}" class="svg-value">{_text(strategy["total_time"]["mean"])}</text>')
    parts.append('<line x1="145" y1="166" x2="625" y2="166" stroke="#89969a"/><text x="145" y="181" class="svg-small">0</text>')
    parts.append(f'<text x="625" y="181" text-anchor="end" class="svg-small">{_text(maximum)} (shared scale)</text></svg>')
    return "".join(parts)


def _range_svg(strategies):
    values = []
    for s in strategies.values():
        t = s["total_time"]
        values.extend(_num(t[k]) for k in ("p05", "p50", "p95"))
    data_lo, data_hi = min(values), max(values)
    padding = max((data_hi - data_lo) * 0.08, abs(data_lo) * 0.002, 1.0)
    lo, hi = data_lo - padding, data_hi + padding
    left, right = 155.0, 690.0
    x = lambda v: left + (v-lo)/(hi-lo)*(right-left)
    out = ['<svg viewBox="0 0 720 208" role="img" aria-labelledby="range-title range-desc"><title id="range-title">Observed total-effort percentiles</title><desc id="range-desc">Each line spans the reported fifth to ninety-fifth percentile, with the median marked. Each row lists exact p05, p50, and p95 values. This is a shared zoomed scale, not a reconstructed distribution.</desc>']
    for i, (name, s) in enumerate(strategies.items()):
        y=56+i*55; t=s["total_time"]; a,b,c=(x(_num(t[k])) for k in ("p05","p50","p95"))
        out.append(f'<text x="8" y="{y+5}" class="svg-label">{html.escape(name.title())}</text><line x1="{a:.3f}" y1="{y}" x2="{c:.3f}" y2="{y}" stroke="#168b83" stroke-width="9" stroke-linecap="round"/><line x1="{a:.3f}" y1="{y-9}" x2="{a:.3f}" y2="{y+9}" stroke="#173b52" stroke-width="2"/><line x1="{c:.3f}" y1="{y-9}" x2="{c:.3f}" y2="{y+9}" stroke="#173b52" stroke-width="2"/><path d="M {b:.3f} {y-8} L {b+8:.3f} {y} L {b:.3f} {y+8} L {b-8:.3f} {y} Z" fill="#d98745" stroke="#173b52"><title>{html.escape(name.title())} median: {_text(t["p50"])}</title></path><text x="155" y="{y+24}" class="svg-small">p05 {_text(t["p05"])}</text><text x="422" y="{y+24}" class="svg-small" text-anchor="middle">p50 {_text(t["p50"])}</text><text x="690" y="{y+24}" class="svg-small" text-anchor="end">p95 {_text(t["p95"])}</text>')
    out.append(f'<line x1="155" y1="25" x2="690" y2="25" stroke="#89969a"/><text x="155" y="16" class="svg-small">Shared zoomed scale: {_text(lo)} to {_text(hi)} (not zero-based)</text></svg>')
    return "".join(out)


def _timeline_svg(name, run, effort_scale):
    """Draw each block's serial mean stages; row position tracks code progress."""
    stages = (
        ("Writing", "mean_writing_time", "#173b52"),
        ("Initial review", "mean_review_time", "#168b83"),
        ("Revision", "mean_revision_time", "#d98745"),
        ("Follow-up review", "mean_rereview_time", "#8b6bb1"),
    )
    left, right = 190.0, 850.0
    scale = (right - left) / effort_scale if effort_scale else 0.0
    row_height = 14 if len(run) <= 50 else 3
    top = 58
    height = top + max(1, len(run)) * row_height + 46
    end_time = sum(sum(_num(block.get(key, 0)) for _, key, _ in stages) for block in run)
    svg_id = f"{name}-timeline"
    out = [f'<svg id="{svg_id}" viewBox="0 0 900 {height}" role="img" aria-labelledby="{svg_id}-title {svg_id}-desc" data-effort-scale="{_raw_num(effort_scale)}" data-effort-end="{_raw_num(end_time)}"><title id="{svg_id}-title">{html.escape(name.title())} average lifecycle timeline</title><desc id="{svg_id}-desc">Average across trials, not a sampled run. Each row is one original-code block. Horizontal position and width show cumulative serial effort on the same scale as the other strategy; row position and milestone labels show code progress in lines. Stages: Writing, Initial review, Revision, Follow-up review.</desc>']
    out.append(f'<text x="{left}" y="19" class="svg-small">Serial effort (time units), common scale ends at {_text(effort_scale)}</text>')
    out.append(f'<line x1="{left}" y1="34" x2="{right}" y2="34" stroke="#89969a"/><line x1="{left}" y1="40" x2="{left}" y2="{height-16}" stroke="#89969a"/>')
    out.append(f'<text x="8" y="43" class="svg-small">Code progress</text><text x="{left}" y="{height-2}" class="svg-small">Effort 0</text><text x="{right}" y="{height-2}" text-anchor="end" class="svg-small">Shared effort scale</text>')
    total_lines = max((_num(block.get("end_line", 0)) for block in run), default=0)
    elapsed = 0.0
    for index, block in enumerate(run):
        start, end = _num(block.get("start_line", 0)), _num(block.get("end_line", 0))
        y = top + index * row_height
        x = left + elapsed * scale
        for label, key, color in stages:
            duration = max(0.0, _num(block.get(key, 0)))
            width = duration * scale
            stage_id = label.lower().replace(" ", "-")
            revised_detail = f'; {_text(block.get("mean_revised_lines", 0))} revised lines' if label == "Revision" else ""
            title = f'<title>{html.escape(name.title())}, lines {int(start)}–{int(end)} — {label}: {_text(block.get(key, 0))} time units{revised_detail}</title>'
            if width > 0:
                out.append(f'<rect x="{x:.3f}" y="{y}" width="{width:.3f}" height="{max(1, row_height-1)}" fill="{color}" stroke="#fff" stroke-width=".4" data-stage="{stage_id}" data-start="{int(start)}" data-end="{int(end)}">{title}</rect>')
            else:
                out.append(f'<line x1="{x:.3f}" y1="{y}" x2="{x:.3f}" y2="{y+max(1,row_height-1)}" stroke="{color}" stroke-width="1" stroke-dasharray="1 1" data-stage="{stage_id}" data-start="{int(start)}" data-end="{int(end)}">{title}</line>')
            x += width
            elapsed += duration
        if index == 0 or end == total_lines or (total_lines > 1000 and end % 1000 == 0):
            out.append(f'<text x="8" y="{y+max(8,row_height-2)}" class="svg-small">{int(start)}–{int(end)} lines</text>')
    out.append("</svg>")
    return "".join(out)


def _timelines(strategies):
    if not all(isinstance(strategy.get("average_run"), list) for strategy in strategies.values()):
        return '<p class="muted">Average lifecycle timeline unavailable: summary has no average_run block data.</p>'
    totals = [sum(sum(max(0.0, _num(block.get(key, 0))) for _, key, _ in _COMPONENTS)
                  for block in strategy["average_run"]) for strategy in strategies.values()]
    shared_scale = max(totals, default=0.0) or 1.0
    parts = ['<p class="muted">Each image shows averages across trials, not an actual sampled run. Fractional revised-line averages are expected. Rows are original-code blocks; vertical milestones are code progress, while horizontal position is serial effort in time units. Both images use the same effort scale. Stage order: Writing → Initial review → Revision → Follow-up review.</p>']
    for name in ("agile", "waterfall"):
        run = strategies[name]["average_run"]
        if run:
            parts.append(f'<figure class="timeline"><figcaption>{html.escape(name.title())} method · {len(run)} original-code blocks</figcaption><div class="chart">{_timeline_svg(name, run, shared_scale)}</div></figure>')
        else:
            parts.append(f'<p class="muted">{html.escape(name.title())} lifecycle timeline unavailable: no block summaries.</p>')
    return "".join(parts)


def render_html(result: dict) -> str:
    """Render a simulation summary as an accessible, dependency-free HTML report."""
    cfg, comp, strategies = result["config"], result["comparison"], result["strategies"]
    ci = comp.get("paired_savings_ci95")
    ci_text = "Not available (one trial)" if ci is None else f"[{_text(ci[0])}, {_text(ci[1])}]"
    saving = _num(comp.get("mean_time_saved", 0))
    signed = ("+" if saving > 0 else "−" if saving < 0 else "") + _text(abs(saving))
    config_rows = "".join(f"<div><dt>{html.escape(str(k).replace('_',' ').title())}</dt><dd>{html.escape(str(v), quote=True)}</dd></div>" for k,v in cfg.items())
    bars = "".join(f'<li><span class="swatch" style="--swatch:{color}"></span>{label}</li>' for label,_,color in _COMPONENTS)
    cards = "".join(f'<article class="strategy"><h3>{html.escape(name.title())}</h3><p class="total">{_text(s["total_time"]["mean"])} <small>mean units</small></p><p>Median {_text(s["total_time"]["p50"])} · { _text(s["mean_revised_lines"])} revised lines · {_text(s["mean_review_count"])} reviews</p></article>' for name,s in strategies.items())
    component_rows = "".join(f'<tr><th scope="row">{label}</th>{"".join(f"<td>{_text(s.get(key, 0))}</td>" for s in strategies.values())}</tr>' for label,key,_ in _COMPONENTS)
    component_heads = "".join(f'<th scope="col">{html.escape(name.title())}</th>' for name in strategies)
    timelines = _timelines(strategies)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Code review effort report</title><style>
:root{{--ink:#173b52;--paper:#f4f2ec;--card:#fff;--muted:#586970;--accent:#168b83}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}header{{padding:clamp(2rem,7vw,5rem) max(6vw,calc((100vw - 1080px)/2));background:var(--ink);color:white}}header h1{{font:clamp(2.3rem,6vw,4.6rem)/1.02 Georgia,serif;max-width:760px;margin:0 0 1rem;letter-spacing:-.04em}}header p{{max-width:650px;color:#d4e4e2;margin:0}}main{{max-width:1080px;margin:auto;padding:2rem 1.25rem 4rem}}section{{margin:0 0 2rem}}h2{{font:2rem/1.15 Georgia,serif;margin:0 0 1rem}}h3{{margin:.1rem 0;color:var(--muted);font-size:.9rem;text-transform:uppercase;letter-spacing:.08em}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}}.strategy,.panel{{background:var(--card);border:1px solid #d7dedb;border-radius:12px;padding:1.25rem;box-shadow:0 8px 24px #173b520c}}.total{{font:2rem Georgia,serif;margin:.25rem 0}}small,.muted{{color:var(--muted);font: .85rem system-ui}}.metric{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.8rem}}.metric div{{padding:1rem;border-left:3px solid var(--accent);background:white}}.metric strong{{display:block;font:1.35rem Georgia,serif}}.chart{{overflow-x:auto}}svg{{display:block;width:100%;min-width:560px;height:auto}}.svg-label{{font:14px system-ui;fill:var(--ink)}}.svg-value{{font:12px system-ui;fill:var(--ink)}}.svg-small{{font:11px system-ui;fill:var(--muted)}}.legend{{display:flex;flex-wrap:wrap;gap:.6rem 1.3rem;list-style:none;padding:0;margin:.8rem 0 0}}.legend li{{display:flex;align-items:center;gap:.45rem}}.swatch{{width:14px;height:14px;background:var(--swatch);border:1px solid var(--ink)}}.config{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.25rem 1.5rem}}.config div{{display:flex;justify-content:space-between;gap:.7rem;border-bottom:1px solid #e2e7e4;padding:.4rem 0}}dt{{color:var(--muted)}}dd{{margin:0;text-align:right;font-variant-numeric:tabular-nums}}.note{{border-left:4px solid #d98745;padding:.8rem 1rem;background:#fff8ef}}@media(max-width:600px){{main{{padding:1.3rem .8rem 2rem}}.config{{grid-template-columns:1fr}}}}@media print{{body{{background:white;color:#111}}header{{background:white;color:#111;padding:1rem 0;border-bottom:2px solid}}header p{{color:#333}}main{{padding:1rem 0}}.strategy,.panel{{box-shadow:none;break-inside:avoid}}}}
</style></head><body><header><h1>Code review, in units of effort.</h1><p>Paired simulation report · { _text(cfg.get('trials','—'))} trials · { _text(cfg.get('total_lines','—'))} original lines</p></header><main>
<section><h2>At a glance</h2><div class="cards">{cards}</div></section><section class="metric" aria-label="Paired comparison"><div><span>Mean effort saved</span><strong>{signed} units</strong><small>Waterfall minus agile · {_text(comp.get('mean_percent_saved',0))}%</small></div><div><span>Paired 95% confidence interval</span><strong>{ci_text}</strong><small>Normal approximation for mean paired savings</small></div><div><span>Win probability · tie probability</span><strong>{_text(_num(comp.get('agile_win_probability',0))*100)}% · {_text(_num(comp.get('tie_probability',0))*100)}%</strong><small>Win means lower effort than waterfall</small></div></section>
<section class="panel"><h2>What makes up mean effort</h2><p class="muted">Stacked component means use one shared scale beginning at zero.</p><div class="chart">{_svg(result)}</div><ul class="legend">{bars}</ul><table class="component-table"><caption>Mean component effort (time units)</caption><thead><tr><th scope="col">Component</th>{component_heads}</tr></thead><tbody>{component_rows}</tbody></table></section><section class="panel"><h2>How total effort varied</h2><p class="muted">Lines span the reported p05–p95 range; diamond marks p50. Exact values are listed per row. Shared axis is zoomed to the reported values and does not start at zero. Quantiles do not describe an invented distribution.</p><div class="chart">{_range_svg(strategies)}</div></section>
<section class="panel"><h2>Experiment configuration</h2><dl class="config">{config_rows}</dl></section><section class="panel"><h2>Average review lifecycle</h2>{timelines}</section><section class="note"><strong>Read this as a model, not a forecast.</strong> Results are serial total effort in normalized time units, not elapsed calendar time. Inputs are illustrative, not measured productivity data. Shared per-line revision outcomes pair the strategies. The model omits defect propagation, context-switch costs, and benefits of earlier feedback; it cannot establish a universal best workflow. The confidence interval is uncertainty in mean paired savings, not the range containing 95% of projects.</section>
</main></body></html>'''
