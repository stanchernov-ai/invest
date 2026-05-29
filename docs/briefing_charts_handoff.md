# Briefing Charts & Layout — Session Handoff

**Status:** Active  
**Last updated:** May 29, 2026 (EOD — chart palette + layout sprint)  
**SSOT for:** QuickChart configuration, briefing section order, gain/loss color rules, and validation runs for executive briefing visuals.

**Code:** `src/output/reporting.py`  
**Tests:** `tests/test_reporting_briefing.py` (14 tests)

---

## Start here

1. Read this doc for chart behavior and design rules.
2. Run tests: `python -m pytest tests/test_reporting_briefing.py -v`
3. After deploy, validate with deliver-only re-run or full pipeline — Graphics QA is the acceptance gate.
4. Pull artifacts: `.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id <run_id>`

---

## What shipped (May 29, 2026)

| Commit | Summary |
|--------|---------|
| `ce577bf` | Dark green/red gain-loss palette on white (pies + TWR table); bar Y-axis `Return (%)`; hide bar legend |
| `a91b05a` | Move **State of the Union** before Action Plan; CAGR `12.00%` not `12.00 percent` |
| `41cc31d` | Remove pie chart top legends (`plugins.legend: false` boolean); taller pie canvas 600×420 |
| *(pending push)* | Dark canvas line + bar charts; compact date labels; visible bar `%` datalabels |

### Validation runs

| Run ID | Pipeline | Charts / QA notes |
|--------|----------|-------------------|
| `20260529_144833` | **success** — canonical pre-chart-fix | Graphics **FAIL** — light green pies, unreadable labels |
| `20260529_152151` | **success** — post `ce577bf` deploy | Graphics **FAIL** — similar dark greens on pies; bar labels invisible (white-on-white); raw `YYYYMMDD` x-axis |
| *(next)* | Re-run after full chart sprint deploy | Expect Graphics PASS on chart-health + contrast |

**Note:** `wait_for_run.py --timeout 660` can false-timeout when debate queue delay (~10 min post-deploy) eats the budget. Poll from debate start or use `--timeout 900`.

---

## Chart inventory

| Chart | Builder | Canvas | Color rule |
|-------|---------|--------|------------|
| Performance vs. Benchmark | `build_benchmark_line_chart()` | **Dark** `#111827` | Lines: blue / gray / mint (not gain-loss semantic) |
| Personal Return by Asset | `build_returns_bar_chart()` | **Dark** `#111827` | Green/red ramp via `colors_for_metric(..., theme="dark")` |
| Unrealized Gains (pie) | `build_portfolio_pie_chart()` | **White** | Green/red ramp via `colors_for_metric(..., theme="light")` |
| 12M Return by Account (pie) | `build_account_allocation_pie()` | **White** | Same light-theme ramp on 12M TWR |

**Design intent:** Top row = dashboard terminal (dark). Pies = allocation detail inside white email containers — keep white background so outlabels breathe.

---

## Color palettes (gain / loss only)

No third hue for gain/loss charts. Semantic: **green = gains, red = losses**.

### Light theme (pies, TWR table text)

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
2. **Bar datalabels:** Were configured white on white canvas — invisible. Fixed with dark canvas + `CHART_LABEL_ON_DARK` (`#ecfdf5`).
3. **Bar legend:** Same boolean `false` in `plugins.legend` plus top-level `"legend": {"display": false}`.
4. **Datalabel formatter:** QuickChart accepts JS string: `BAR_DATALABEL_FORMATTER` → `function(value){...}+'%'`.
5. **Short URL API:** `get_quickchart_short_url(..., background_color=...)` POSTs to `quickchart.io/chart/create` — prefer over inline URL (line chart URL length).
6. **Pie size:** `PIE_CHART_WIDTH=600`, `PIE_CHART_HEIGHT=420` after legend removal.

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
3. Time-Weighted Returns table
4. **The State of the Union** (analyst quotes)
5. The Alpha Pick (if displayable)
6. The Action Plan
7. The Debate
8. Unicorn Protocol (if any)
9. Chairman's Closing Thoughts
10. Upcoming Catalysts

**Open tension:** Graphics QA on `152151` suggested Action Plan *above* SoTU. Stan approved SoTU earlier (after TWR). Reconcile with Stan before reordering again.

---

## Tests

| Test class | Covers |
|------------|--------|
| `BenchmarkChartTests` | TWR index rebase, compact month labels, dark line bg |
| `ChartColorTests` | Palette spread, dark-green-only on light theme, pie legend false, bar datalabels |
| `BriefingHtmlTests` | Section order TWR → SoTU → Action Plan; CAGR `%` |
| `BriefingCopyTests` | Alpha pick / debate / QA jargon sanitization |

Add golden HTML fixtures under `tests/fixtures/visual_qa/` when a run is accepted as baseline.

---

## Still open (P1+)

| Priority | Item | Source |
|----------|------|--------|
| **P1** | Validate full chart sprint on production deliver | This session |
| **P1** | Round 2 rebuttal prompts — stop verbatim R1 copy | Prompt Engineer CRITICAL `152151` |
| **P1** | Post Mortem QA — verify vote counts vs log (AMZN 2/5 false majority) | Integrity CRITICAL `152151` |
| **P1** | Section order — SoTU vs Action Plan priority | Graphics WARNING `152151` vs Stan preference |
| **P2** | R2 debate log bloat (Pass spam) | Systems Architect CRITICAL `152151` |
| **P2** | Split `reporting.py` | Backlog |
| **P3** | Verdict memory META dedupe | `144833` |

---

## How to re-render charts only

Skip debate if checkpoint exists:

```http
GET https://<defaultHostName>/api/deliver?run_id=20260529_152151&code=<function-key>
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
