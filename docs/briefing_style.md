# Briefing Visual Style — SSOT

**Status:** Active  
**Last updated:** May 29, 2026  
**Code SSOT:** `src/output/briefing_style.py`  
**Consumers:** `src/output/reporting.py` (HTML), `src/core/agents.py` (Graphics Designer QA), `src/qa/visual_audit.py` (deterministic theme checks)

---

## Design intent

Dark premium board pack — institutional, low eye strain, matte sage brand accent. QuickChart PNGs stay **white-background**; the email applies a CSS filter on `.chart-img` so charts match the cool green palette without rebuilding the chart engine.

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

## Token map

| Role | Hex | Usage |
|------|-----|--------|
| Canvas body | `#121212` | `<body>` outer background |
| App container | `#1e1e1e` | Main `.container` card |
| Elevated surface | `#27272a` | Metric box, chart cards, chairman box |
| Primary text | `#a1a1aa` | Body copy, footer, muted labels |
| Highlight text | `#f4f4f5` | `<strong>`, critical numbers, h3 |
| Matte sage | `#95b8a2` | h1, h2, chart titles, brand accent |
| Subtle border | `#3f3f46` | Dividers, chart borders, table rows |
| Bull text / bg | `#6ee7b7` / `#064e3b` | Buy pills, champion quotes, SoTU 4-star |
| Bear text / bg | `#fca5a5` / `#450a0a` | Sell pills, dissent, red team, SoTU 1–2 star |
| Warn text / bg | `#fcd34d` / `#3f2c12` | Hedge mandate, Trim pills |

---

## Chart dark mode (CSS filter)

QuickChart images are **not** regenerated for dark mode. Apply to every briefing chart:

```css
.chart-img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
    filter: invert(0.9) hue-rotate(180deg) grayscale(0.6);
}
```

**Graphics Designer QA:** Filter-toned chart PNGs in multimodal review are **intentional** — do not flag as broken unless unreadable.

**Gain/loss chart data colors** (QuickChart config) remain in `reporting.py` (`GAIN_GREEN_*`, `LOSS_RED_*`) on white canvas; the filter harmonizes them in the email.

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
