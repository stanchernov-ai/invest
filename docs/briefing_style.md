# Briefing Visual Style — SSOT

**Status:** Active  
**Last updated:** May 30, 2026  
**Code SSOT:** `src/output/briefing_style.py`  
**Avatar art direction:** [`briefing_avatars.md`](briefing_avatars.md)  
**Consumers:** `src/output/reporting.py` (HTML), `src/core/agents.py` (Graphics Designer QA), `src/qa/visual_audit.py` (deterministic theme checks)

---

## Design intent

**Stealth Wealth** — quiet authority and institutional wealth for premium subscribers. Dark premium board pack with low eye strain, matte sage brand accent. Charts render natively on `#121212` via QuickChart (Chart.js). **Never** apply CSS filters to chart images — filters ruin categorical color fidelity.

---

## Stealth Wealth palette

| Role | Hex | Usage |
|------|-----|--------|
| Canvas body | `#121212` | `<body>` outer background |
| App container | `#1e1e1e` | Main `.container` card — elevation layer |
| Elevated surface | `#27272a` | Metric boxes, chart cards, chairman box |
| Primary text | `#a1a1aa` | Body copy, footer, muted labels |
| High-contrast text | `#f4f4f5` | `<strong>`, critical numbers, h3 |
| Matte sage (brand) | `#95b8a2` | h1, h2, chart titles, primary headers |
| Subtle border | `#3f3f46` | Dividers, chart borders, table rows |
| Bull text / bg | `#6ee7b7` / `#064e3b` | Buy pills, champion quotes, SoTU 4-star (bg at 50% alpha) |
| Bear text / bg | `#fca5a5` / `#450a0a` | Sell pills, dissent, red team, SoTU 1–2 star (bg at 50% alpha) |
| Warn text / bg | `#fcd34d` / `#3f2c12` | Hedge mandate, Trim pills |

**State of the Union quote rows:** background uses the semantic fill at **50% opacity** (`SOTU_BG_ALPHA = 0.5` via `rgba(...)`); left border stays solid for stance color.

---

## CSS variables (drop-in)

```css
:root {
    --bg-canvas: #121212;
    --bg-container: #1e1e1e;
    --bg-surface: #27272a;
    --text-primary: #a1a1aa;
    --text-highlight: #f4f4f5;
    --brand-sage: #95b8a2;
    --border-subtle: #3f3f46;
    --bull-text: #6ee7b7;
    --bull-bg: #064e3b;
    --bear-text: #fca5a5;
    --bear-bg: #450a0a;
    --warn-text: #fcd34d;
    --warn-bg: #3f2c12;
}
```

---

## Chart engine rules

Charts **must** be built with a native JavaScript charting engine (QuickChart / Chart.js). All chart types — line, bar, and pie — render on `#121212` with off-white labels.

**Prohibited:** CSS `filter` rules on static chart images. Do not force dark mode via invert/hue-rotate/grayscale — this destroys gain/loss color semantics on pie and bar charts.

```css
.chart-img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
}
```

**Graphics Designer QA:** Flag CRITICAL if chart CSS includes `filter:` on `.chart-img` or if pie/bar colors appear washed out from post-processing.

---

## Chart typography (QuickChart)

**SSOT:** `src/output/briefing_style.py` — consumed by `src/output/reporting.py`.

Credibility rule: if a board member has to squint at a label or legend, the chart fails QA.

| Element | Dark canvas (all chart types) |
|---------|-------------------------------|
| Canvas | `#121212` (`CHART_CANVAS_DARK`) |
| Data labels | Off-white `#f4f4f5`, weight **700**, size **13px** |
| Pie outlabels | Off-white `#f4f4f5`, weight **700**, min **13px** / max **18px** |
| Legend (line chart) | Off-white `#f4f4f5`, size **14px**, weight **600** |
| Axis ticks | `#a1a1aa`, 11px |

Bar and pie charts use `colors_for_metric(..., theme="dark")` gain/loss ramps (`#86efac`→`#22c55e`, `#fca5a5`→`#ef4444`).

---

## Agent / QA wiring

| Consumer | How palette is applied |
|----------|------------------------|
| Executive briefing HTML | `executive_briefing_css()` + `verdict_pill_styles()` |
| QA dashboard HTML | `qa_dashboard_css()` (same brand, internal ops) |
| Graphics Designer QA | `GRAPHICS_QA_STYLE_MANDATE` appended to system prompt |
| Deterministic visual QA | `audit_briefing_theme()` in `visual_audit.py` |
| QA integrity auditor | Validates Graphics findings against rendered HTML excerpt |

---

## Related docs

| Doc | Section |
|-----|---------|
| [`briefing_charts_handoff.md`](briefing_charts_handoff.md) | QuickChart config, chart inventory |
| [`engineering_playbook.md`](engineering_playbook.md) | Email-safe layout (tables, no flex) |
| [`agent_architecture.md`](agent_architecture.md) | Graphics QA pipeline |

---

## Change process

1. Edit constants in `src/output/briefing_style.py` only.
2. Run `python -m unittest tests.test_briefing_style tests.test_reporting_briefing -v`.
3. Update this doc if tokens change.
4. Re-run deliver on a checkpoint to validate Graphics QA acceptance.
