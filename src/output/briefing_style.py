"""Invest AI executive briefing — Stealth Wealth dark premium palette (SSOT).

Code constants, CSS blocks, and agent digests for briefing HTML, QA dashboard,
Graphics Designer QA, and deterministic visual audit. Charts render natively on
#121212 via QuickChart (Chart.js) — never CSS-filtered static images.
"""

from __future__ import annotations

# --- Core backgrounds ---
BG_CANVAS = "#121212"
BG_CONTAINER = "#1e1e1e"
BG_SURFACE = "#27272a"

# --- Typography ---
TEXT_PRIMARY = "#a1a1aa"
TEXT_HIGHLIGHT = "#f4f4f5"

# --- Branding ---
BRAND_SAGE = "#95b8a2"
BORDER_SUBTLE = "#3f3f46"

# --- Financial indicators ---
BULL_TEXT = "#6ee7b7"
BULL_BG = "#064e3b"
BEAR_TEXT = "#fca5a5"
BEAR_BG = "#450a0a"
WARN_TEXT = "#fcd34d"
WARN_BG = "#3f2c12"

# QuickChart (Chart.js) renders all chart types on CHART_CANVAS_DARK natively.
# --- QuickChart typography (credibility gate: labels/legends must not require squinting) ---
CHART_CANVAS_DARK = BG_CANVAS  # #121212 — all charts (line, bar, pie)
CHART_CANVAS_LIGHT = "#ffffff"  # legacy alias — do not use for new charts

CHART_DATALABEL_ON_DARK = TEXT_HIGHLIGHT  # #f4f4f5 off-white on dark canvas
CHART_DATALABEL_ON_LIGHT = "#18181b"  # near-black on white pie canvas
CHART_DATALABEL_WEIGHT = 700
CHART_DATALABEL_SIZE = 13

CHART_LEGEND_COLOR_ON_DARK = TEXT_HIGHLIGHT
CHART_LEGEND_FONT_SIZE = 14
CHART_LEGEND_WEIGHT = 600

CHART_AXIS_ON_DARK = TEXT_PRIMARY
CHART_AXIS_TITLE_ON_DARK = TEXT_HIGHLIGHT
CHART_AXIS_TICK_SIZE = 11
CHART_AXIS_TITLE_SIZE = 12
CHART_GRID_ON_DARK = "rgba(255,255,255,0.08)"

CHART_INNER_TITLE_ON_DARK = TEXT_HIGHLIGHT
CHART_INNER_TITLE_SIZE = 13
CHART_INNER_TITLE_WEIGHT = 600

CHART_OUTLABEL_WEIGHT = 700
CHART_OUTLABEL_MIN_SIZE = 13
CHART_OUTLABEL_MAX_SIZE = 18

# State of the Union quote rows — backgrounds at least 50% transparent (borders stay solid).
SOTU_BG_ALPHA = 0.5


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

CSS_ROOT_BLOCK = f""":root {{
    --bg-canvas: {BG_CANVAS};
    --bg-container: {BG_CONTAINER};
    --bg-surface: {BG_SURFACE};
    --text-primary: {TEXT_PRIMARY};
    --text-highlight: {TEXT_HIGHLIGHT};
    --brand-sage: {BRAND_SAGE};
    --border-subtle: {BORDER_SUBTLE};
    --bull-text: {BULL_TEXT};
    --bull-bg: {BULL_BG};
    --bear-text: {BEAR_TEXT};
    --bear-bg: {BEAR_BG};
    --warn-text: {WARN_TEXT};
    --warn-bg: {WARN_BG};
}}"""


def verdict_pill_styles() -> dict[str, str]:
    """Inline styles for action-plan verdict pills (email-client safe)."""
    return {
        "STRONG BUY": f"background-color:{BULL_BG}; color:{BULL_TEXT};",
        "BUY": f"background-color:{BULL_BG}; color:{BULL_TEXT};",
        "HOLD": f"background-color:{BG_SURFACE}; color:{TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE};",
        "TRIM": f"background-color:{WARN_BG}; color:{WARN_TEXT};",
        "SELL": f"background-color:{BEAR_BG}; color:{BEAR_TEXT};",
        "STRONG SELL": f"background-color:{BEAR_BG}; color:{BEAR_TEXT};",
    }


def sotu_quote_colors(board_member_label: str) -> tuple[str, str]:
    """Return (background, border-left) for State of the Union quote rows."""
    label = board_member_label or ""
    if "⭐⭐⭐⭐" in label:
        return _hex_to_rgba(BULL_BG, SOTU_BG_ALPHA), BULL_TEXT
    if "⭐⭐⭐" in label:
        return _hex_to_rgba(BG_SURFACE, SOTU_BG_ALPHA), BRAND_SAGE
    if "⭐⭐" in label or "⭐" in label:
        return _hex_to_rgba(BEAR_BG, SOTU_BG_ALPHA), BEAR_TEXT
    return _hex_to_rgba(BG_SURFACE, SOTU_BG_ALPHA), BORDER_SUBTLE


def executive_briefing_css() -> str:
    """Full `<style>` body for the investor executive briefing email."""
    return f"""
            {CSS_ROOT_BLOCK}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-canvas);
                color: var(--text-primary);
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background-color: var(--bg-container);
                padding: 30px;
                border-radius: 8px;
                border: 1px solid var(--border-subtle);
            }}
            h1 {{
                color: var(--brand-sage);
                border-bottom: 2px solid var(--border-subtle);
                padding-bottom: 10px;
            }}
            h2 {{
                color: var(--brand-sage);
                margin-top: 30px;
                border-bottom: 1px solid var(--border-subtle);
                padding-bottom: 5px;
            }}
            h3 {{
                color: var(--text-highlight);
                margin-top: 25px;
                border-bottom: 1px solid var(--border-subtle);
                padding-bottom: 5px;
            }}
            h4 {{ color: var(--text-highlight); margin-bottom: 5px; }}
            strong {{ color: var(--text-highlight); }}
            .metric-box {{
                background-color: var(--bg-surface);
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
                border-left: 4px solid var(--brand-sage);
            }}
            .hedge-box {{
                background-color: var(--warn-bg);
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
                border-left: 4px solid var(--warn-text);
                color: var(--warn-text);
            }}
            .red-team-box {{
                background-color: var(--bear-bg);
                padding: 12px;
                border-radius: 4px;
                border-left: 4px solid var(--bear-text);
                color: var(--bear-text);
            }}
            .champion {{ color: var(--bull-text); font-weight: bold; }}
            .dissenter {{ color: var(--bear-text); font-weight: bold; }}
            .verdict-pill {{
                display: inline-block;
                padding: 6px 14px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                letter-spacing: 0.5px;
                margin-bottom: 12px;
            }}
            .chart-container {{
                margin: 0;
                text-align: center;
                border: 1px solid var(--border-subtle);
                padding: 10px;
                border-radius: 5px;
                background-color: var(--bg-surface);
            }}
            .chart-title {{
                color: var(--brand-sage);
                font-size: 1.3em;
                font-weight: 600;
                margin: 0 0 10px 0;
                padding-bottom: 5px;
                border-bottom: 1px solid var(--border-subtle);
            }}
            .chart-img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
            }}
            .section-divider {{ border-bottom: 1px solid var(--border-subtle); }}
            .muted {{ color: var(--text-primary); }}
            .bear-heading {{ color: var(--bear-text); }}
            .alpha-accent {{ border-left-color: var(--brand-sage) !important; }}
            .chairman-box {{
                background-color: var(--bg-surface);
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid var(--brand-sage);
                font-style: italic;
            }}
            .footer {{
                margin-top: 40px;
                font-size: 0.8em;
                color: var(--text-primary);
                text-align: center;
                border-top: 1px solid var(--border-subtle);
                padding-top: 20px;
            }}
            .qa-box {{
                margin-top: 40px;
                font-size: 0.85em;
                line-height: 1.7;
                color: var(--text-primary);
                border-top: 1px dashed var(--border-subtle);
                padding-top: 15px;
            }}
            .qa-box strong {{ color: var(--text-highlight); }}
            """


def qa_dashboard_css() -> str:
    """Dark palette for the internal QA audit dashboard (matches briefing brand)."""
    return f"""
            {CSS_ROOT_BLOCK}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-canvas);
                color: var(--text-primary);
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                background-color: var(--bg-container);
                padding: 30px;
                border-radius: 8px;
                border: 1px solid var(--border-subtle);
            }}
            h1 {{ color: var(--brand-sage); border-bottom: 2px solid var(--border-subtle); padding-bottom: 10px; }}
            h2 {{ color: var(--brand-sage); margin-top: 30px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 5px; }}
            h3 {{ color: var(--text-highlight); margin-top: 25px; margin-bottom: 10px; }}
            .status-badge {{ display: inline-block; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 14px; margin-bottom: 15px; }}
            .status-pass {{ background-color: var(--bull-bg); color: var(--bull-text); border: 1px solid var(--bull-text); }}
            .status-fail {{ background-color: var(--bear-bg); color: var(--bear-text); border: 1px solid var(--bear-text); }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }}
            th {{ text-align: left; padding: 10px; background-color: var(--bg-surface); border-bottom: 2px solid var(--border-subtle); color: var(--text-highlight); }}
            td {{ padding: 12px 10px; border-bottom: 1px solid var(--border-subtle); vertical-align: top; }}
            .sev-CRITICAL {{ color: var(--bear-text); font-weight: bold; }}
            .sev-WARNING {{ color: var(--warn-text); font-weight: bold; }}
            .sev-INFO {{ color: var(--brand-sage); font-weight: bold; }}
            .summary-box {{
                background-color: var(--bg-surface);
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid var(--border-subtle);
                font-style: italic;
                margin-bottom: 20px;
            }}
            .footer {{
                margin-top: 40px;
                font-size: 0.8em;
                color: var(--text-primary);
                text-align: center;
                border-top: 1px solid var(--border-subtle);
                padding-top: 20px;
            }}
            .pass-text {{ color: var(--bull-text); font-weight: bold; }}
            .fail-text {{ color: var(--bear-text); font-weight: bold; }}
            .timestamp {{ color: var(--text-primary); margin-top: -10px; margin-bottom: 30px; }}
            .review-btn {{
                display: inline-block;
                background: var(--brand-sage);
                color: var(--bg-canvas);
                padding: 12px 20px;
                border-radius: 6px;
                text-decoration: none;
                font-weight: bold;
            }}
            """


def qa_summary_box_html(qa_summary_text: str) -> str:
    """HTML fragment for post-render QA summary injection."""
    return (
        '<div class="qa-box">\n'
        "                <strong>Automated QA Audit</strong>\n"
        "                <span class=\"muted\">&mdash; see the QA Audit Dashboard for details on any &#10060;.</span><br><br>\n"
        f"                {qa_summary_text}\n"
        "            </div>"
    )


GRAPHICS_QA_STYLE_MANDATE = f"""
[BRIEFING VISUAL SSOT — Invest AI dark premium palette]
Ground truth for rubric C (color discipline) and F (brand/tone). Do NOT flag these as wrong.

Backgrounds: canvas {BG_CANVAS}, container {BG_CONTAINER}, elevated surfaces (metric box, chart cards) {BG_SURFACE}.
Typography: primary body {TEXT_PRIMARY}; critical numbers and strong labels {TEXT_HIGHLIGHT}.
Brand accent (h1, h2, chart titles): matte sage {BRAND_SAGE}. Borders/dividers: {BORDER_SUBTLE}.

Financial semantics:
- Bullish (Buy / Strong Buy pills, champion quotes): {BULL_TEXT} on {BULL_BG}.
- Bearish (Sell / Strong Sell, dissent, red team): {BEAR_TEXT} on {BEAR_BG}.
- Warning / hedge mandate: {WARN_TEXT} on {WARN_BG}.

Charts: All chart types (line, bar, pie) render natively on {CHART_CANVAS_DARK} via QuickChart (Chart.js). Do NOT apply CSS filters to chart images — filters ruin categorical color fidelity.

Chart typography (QuickChart): data labels weight {CHART_DATALABEL_WEIGHT}, off-white {CHART_DATALABEL_ON_DARK} on dark canvas; pie outlabels weight {CHART_OUTLABEL_WEIGHT} on dark canvas. Legend base size {CHART_LEGEND_FONT_SIZE}px on line chart. Flag CRITICAL if labels or legends are faint or unreadable.

Also flag CRITICAL if charts are broken, if bright white Bootstrap/SaaS blocks return, or if more than three unrelated accent hues appear outside this palette.
""".strip()


def agent_palette_digest() -> str:
    """Alias for agent prompts."""
    return GRAPHICS_QA_STYLE_MANDATE
