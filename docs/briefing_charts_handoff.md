# Briefing Charts & Layout — Session Handoff

**Status:** Active  
**Last updated:** May 30, 2026 (deploy batch staged — GFX-4 / UNICORN-1 local)  
**SSOT for:** QuickChart configuration, briefing section order, gain/loss color rules, and validation runs for executive briefing visuals.

**Code:** `src/output/reporting.py` (chart builders) · **`src/output/briefing_style.py`** (HTML palette SSOT)  
**Style doc:** [`briefing_style.md`](briefing_style.md)  
**Tests:** `tests/test_reporting_briefing.py`, `tests/test_briefing_style.py`

---

## Start here

1. Read this doc for chart behavior and design rules.
2. Run tests: `python -m pytest tests/test_reporting_briefing.py -v`
3. After deploy, validate with deliver-only re-run or full pipeline — Graphics QA is the acceptance gate.
4. Pull artifacts: `.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id <run_id>`

---

## What shipped

### May 29, 2026 — chart palette sprint

| Commit | Summary |
|--------|---------|
| `ce577bf` | Dark green/red gain-loss palette on white (pies); bar Y-axis `Return (%)`; hide bar legend |
| `a91b05a` | Move **State of the Union** before Action Plan; CAGR `12.00%` not `12.00 percent` |
| `41cc31d` | Remove pie chart top legends (`plugins.legend: false` boolean); taller pie canvas 600×420 |
| `3f66433` | Dark canvas line + bar charts; compact `May '25` dates; bar `%` datalabels; handout doc |

### May 30, 2026 — briefing layout + Action Plan

| Commit | Summary |
|--------|---------|
| `e044bde` | Section order: pies → SoTU → Action Plan (metric box + charts unchanged) |
| `04af83d` | Remove Symbol/Action summary table; remove **Time-Weighted Returns table** (returns data still feeds mandate + charts) |
| `cfe55fd`, `380427f` | Three-layer Action Plan per symbol: **Strategic Context** (Flash) + **Champion** + **Dissent** (R2 JSON) |

**Enrichment code:** `src/output/briefing_enrichment.py` — wired in `src/jobs/deliver.py` before `generate_html_briefing`.

### Validation runs

| Run ID | Pipeline | Charts / QA notes |
|--------|----------|-------------------|
| `20260529_152151` | success | Chart sprint baseline; Graphics still flags bar Y-axis |
| `20260529_225159` | **success** — **canonical layout** | Action Plan 8/8 enriched; no TWR table; Debate complete |
| `20260529_214609` | Supervisor BLOCKED | Pre-layout; Integrity TSM false positive (R1 vs R2) |

**Note:** `wait_for_run.py --timeout 660` can false-timeout when debate queue delay (~10 min post-deploy) eats the budget. Poll from debate start or use `--timeout 900`.

---

## Chart inventory

| Chart | Builder | Canvas | Color rule |
|-------|---------|--------|------------|
| Performance vs. Benchmark | `build_benchmark_line_chart()` | **Dark** `#121212` | Lines: blue / gray / mint; legend 14px off-white |
| Personal Return by Asset | `build_returns_bar_chart()` | **Dark** `#121212` | Green/red ramp via `colors_for_metric(..., theme="dark")`; datalabels off-white weight 700 |
| Unrealized Gains (pie) | `build_portfolio_pie_chart()` | **White** | Green/red ramp via `colors_for_metric(..., theme="light")` |
| 12M Return by Account (pie) | `build_account_allocation_pie()` | **White** | Same light-theme ramp on 12M TWR |

**Design intent:** All charts render natively on `#121212` via QuickChart (Chart.js). **No CSS filters** on chart images — filters ruin categorical color fidelity. **Typography SSOT:** [`briefing_style.md`](briefing_style.md) § Chart typography.

---

## Chart typography (QuickChart)

| Element | Line / bar (dark canvas) | Pies (white canvas) |
|---------|--------------------------|---------------------|
| Data labels | `#f4f4f5`, weight 700, 13px | Outlabels `#18181b`, weight 700, 13–18px |
| Legend | 14px, weight 600 (line only) | Hidden |

Line and bar PNGs skip the email CSS filter so off-white labels stay crisp.

---

## Color palettes (gain / loss only)

**HTML/email dark theme:** see [`briefing_style.md`](briefing_style.md) — canvas `#121212`, sage `#95b8a2`, chart `.chart-img` CSS filter.

QuickChart **data** colors (white canvas PNGs):

No third hue for gain/loss charts. Semantic: **green = gains, red = losses**.

### Light theme (pies)

| Role | High (better) | Low (worse) |
|------|---------------|-------------|
| Gains | `#166534` | `#052e16` |
| Losses | `#b91c1c` | `#450a0a` |

### Dark theme (bar chart on `#111827`)

| Role | High | Low |
|------|------|-----|
| Gains | `#86efac` | `#22c55e` |
| Losses | `#fca5a5` | `#ef4444` |

Constants live at top of `reporting.py`. `colors_for_metric(values, theme="light"|"dark")` lerps min→max within the appropriate ramp; diverging sets split at zero.

---

## QuickChart gotchas (read before editing)

1. **`outlabeledPie` legend:** Must be `"plugins": { "legend": false }` (boolean). `{ "display": false }` is **ignored** — top ticker row still renders (see user screenshot May 29).
2. **Bar datalabels:** Dark canvas `#121212` + off-white `#f4f4f5` at weight 700. Never white-on-white.
3. **Pie outlabels:** Off-white `#f4f4f5` at weight 700 on dark `#121212` canvas — no CSS filter.
4. **Bar legend:** Same boolean `false` in `plugins.legend` plus top-level `"legend": {"display": false}`.
5. **Datalabel formatter:** QuickChart accepts JS string: `BAR_DATALABEL_FORMATTER` → `function(value){...}+'%'`.
6. **Short URL API:** `get_quickchart_short_url(..., background_color=...)` POSTs to `quickchart.io/chart/create` — prefer over inline URL (line chart URL length).
7. **Pie size:** `PIE_CHART_WIDTH=600`, `PIE_CHART_HEIGHT=420` after legend removal.

---

## Line chart (benchmark)

- **Input:** `portfolio_history.json` keys as `YYYYMMDD`; uses `portfolio_index` when present (not raw balance spikes).
- **Downsample:** `_downsample(..., max_points=LINE_CHART_MAX_POINTS)` where `LINE_CHART_MAX_POINTS = 12`.
- **X labels:** `_format_history_axis_labels()` → `May '25` ( `%b '%y` ).
- **X ticks:** `maxTicksLimit: 6`, no rotation, `autoSkip: true`.
- **Inner title:** `Indexed performance (start = 100)` — HTML already has section title above chart.

---

## Briefing HTML section order

After metric box and charts:

1. Performance + bar charts (side by side)
2. Pie charts (side by side)
3. **The State of the Union** (Round 1 portfolio-level quotes)
4. **The Alpha Pick** (if displayable)
5. **The Debate** (hidden if `boardroom_brawl` incomplete)
6. **Unicorn Protocol** (only if 5/5 Buy or 5/5 Reduce — **UNICORN-1:** unanimous Hold omitted; section hidden when empty)
7. **The Action Plan** — per symbol: Strategic Context → Champion → Dissent (no summary table)
8. Chairman's Closing Thoughts
9. Upcoming Catalysts

**Removed May 30:** Time-Weighted Returns **table** (`04af83d`). Account return JSON still drives CAGR mandate text and pie allocation chart.

---

## Tests

| Test class | Covers |
|------------|--------|
| `BenchmarkChartTests` | TWR index rebase, compact month labels, dark line bg |
| `ChartColorTests` | Palette spread, dark-green-only on light theme, pie legend false, bar datalabels |
| `BriefingHtmlTests` | Section order pies → SoTU → Action Plan; no TWR table; three-layer Action Plan fields |
| `BriefingCopyTests` | Alpha pick / debate / QA jargon sanitization |

Add golden HTML fixtures under `tests/fixtures/visual_qa/` when a run is accepted as baseline.

---

## Still open (P1+)

| Priority | Item | Source |
|----------|------|--------|
| **P0** | Ship staged deploy batch | [`action_tracker.md`](action_tracker.md) — commit blocked this session |
| **P1** | Bar chart Y-axis / legend / contrast | Recurring Graphics CRITICAL |
| **P1** | Logo contrast on dark chip (`GFX-2`) | Partial locally |
| **P1** | Pie categorical palette (`GFX-3`) | Too many similar greens |
| **P2** | Round 2 rebuttal prompts — stop verbatim R1 copy | Prompt Engineer CRITICAL |
| **P2** | Split `reporting.py` | Backlog |
| **P3** | Verdict memory META dedupe | `144833` |

**Done locally (staged, not prod):** GFX-4 section order; AP-1 Strategic Context; GFX-QA `.qa-box` strip; UNICORN-1 empty hide; catalyst fallback; QA review footer in investor email.

**Done (prod):** Post-mortem vote verification (`bf17114`); section order SoTU before Action Plan (`e044bde`); TWR table removed (`04af83d`); three-layer Action Plan (`cfe55fd`).

---

## How to re-render charts only

Skip debate if checkpoint exists:

```http
GET https://<defaultHostName>/api/deliver?run_id=20260529_225159&code=<function-key>
```

Hostname: `engineering_playbook.md` — Flex Consumption regional hostname (not `*.azurewebsites.net` guess).

---

## Related docs

| Doc | Section |
|-----|---------|
| [`action_tracker.md`](action_tracker.md) | Session Handoff + backlog |
| [`technical_solution.md`](technical_solution.md) | `reporting.py` in repo layout |
| [`engineering_playbook.md`](engineering_playbook.md) | QuickChart legend quirk |
| [`agent_architecture.md`](agent_architecture.md) | `audit_chart_health`, Graphics QA pipeline |
| [`post_deliver_checklist.md`](post_deliver_checklist.md) | After each deliver |
