"""Invest AI executive briefing — Stealth Wealth dark premium palette (SSOT).

Code constants, CSS blocks, and agent digests for briefing HTML, QA dashboard,
Graphics Designer QA, and deterministic visual audit. Charts render natively on
#121212 via QuickChart (Chart.js) — never CSS-filtered static images.
"""

from __future__ import annotations

import html
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

# The Crucible — adversarial rebuttal block (cold iron vault; not bear-red semantics).
CRUCIBLE_BG = "#09090b"          # void charcoal — darker/colder than BG_SURFACE
CRUCIBLE_BORDER = "#a8b0ba"      # forged steel — ties to portrait iron ring
CRUCIBLE_TEXT = "#e4e4e7"        # icy zinc — cold prose, no warm emotion
CRUCIBLE_HEADER = "#c0c8d0"      # stark metallic silver

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

NEUTRAL_BLUE = "#93c5fd"

# Chart charge semantics — hardcoded sign colors (aligned with SoTU / verdict pills).
CHART_GAIN = BULL_TEXT           # #6ee7b7
CHART_LOSS = BEAR_TEXT           # #fca5a5
CHART_NEUTRAL = NEUTRAL_BLUE
CHART_NEUTRAL_EPS = 0.05         # |return| ≤ this → neutral blue (%)
CHART_GAIN_VARIANTS = (CHART_GAIN, "#34d399", "#22c55e", "#4ade80")
CHART_LOSS_VARIANTS = (CHART_LOSS, "#f87171", "#ef4444", "#fb7185")
CHART_LINE_PORTFOLIO = CHART_GAIN
CHART_LINE_BENCHMARK = "#71717a"
CHART_LINE_NASDAQ = CHART_NEUTRAL

# Side-by-side row (Performance + Returns) — identical PNG geometry for visual balance.
# QuickChart renders at width×height CSS px, then scales bitmap by devicePixelRatio.
# 3× matches premium phone retina (iPhone Pro class); HTML max-width stays 388px.
QUICKCHART_DEVICE_PIXEL_RATIO = 3

BRIEFING_PAIR_CHART_WIDTH = 388
BRIEFING_PAIR_CHART_HEIGHT = 300
BAR_CHART_WIDTH = BRIEFING_PAIR_CHART_WIDTH
BAR_CHART_HEIGHT = BRIEFING_PAIR_CHART_HEIGHT
LINE_CHART_WIDTH = BRIEFING_PAIR_CHART_WIDTH
LINE_CHART_HEIGHT = BRIEFING_PAIR_CHART_HEIGHT

BAR_DATALABEL_SIZE = 12
BAR_DATALABEL_COLOR = "#18181b"
BAR_DATALABEL_ANCHOR = "end"
BAR_DATALABEL_ALIGN = "start"
BAR_DATALABEL_OFFSET = -14
BAR_MIN_BAR_LENGTH = 28
BAR_CHART_LAYOUT_PADDING = {"top": 32, "bottom": 14, "left": 8, "right": 12}
BAR_Y_SCALE_GRACE = "12%"
# QuickChart tickFormat plugin — JS formatters in datalabels are ignored on POST renders.
BAR_TICK_FORMAT = {
    "suffix": "%",
    "minimumFractionDigits": 0,
    "maximumFractionDigits": 0,
    "applyToDataLabels": True,
}

PIE_CHART_WIDTH = BRIEFING_PAIR_CHART_WIDTH
PIE_CHART_HEIGHT = 360
PIE_OUTLABEL_COLOR = "#18181b"
PIE_OUTLABEL_MIN_SIZE = 14
PIE_OUTLABEL_MAX_SIZE = 18
PIE_OUTLABEL_STRETCH = 24

# Magnitude ramps on dark canvas: lighter tint = smaller |return|, deeper = larger |return|.
CHART_GAIN_LIGHT = "#86efac"
CHART_GAIN_DARK = "#166534"
CHART_LOSS_LIGHT = "#fca5a5"
CHART_LOSS_DARK = "#991b1b"


def _clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))


def _lerp_hex(color_low: str, color_high: str, t: float) -> str:
    """Blend two #RRGGBB colors; t=0 → low, t=1 → high."""
    t = _clamp01(t)

    def _rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    r1, g1, b1 = _rgb(color_low)
    r2, g2, b2 = _rgb(color_high)
    return "#%02x%02x%02x" % (
        int(round(r1 + (r2 - r1) * t)),
        int(round(g1 + (g2 - g1) * t)),
        int(round(b1 + (b2 - b1) * t)),
    )


def chart_magnitude_colors(values: list[float]) -> list[str]:
    """Map return % to green/red intensity — darker = larger |gain| within each sign."""
    if not values:
        return []
    floats = [float(v) for v in values]
    pos = [v for v in floats if v > CHART_NEUTRAL_EPS]
    neg = [v for v in floats if v < -CHART_NEUTRAL_EPS]
    pos_min, pos_max = (min(pos), max(pos)) if pos else (0.0, 0.0)
    neg_min, neg_max = (min(neg), max(neg)) if neg else (0.0, 0.0)

    colors: list[str] = []
    for v in floats:
        if v > CHART_NEUTRAL_EPS:
            if len(pos) <= 1 or pos_max == pos_min:
                t = 0.65
            else:
                t = (v - pos_min) / (pos_max - pos_min)
            colors.append(_lerp_hex(CHART_GAIN_LIGHT, CHART_GAIN_DARK, t))
        elif v < -CHART_NEUTRAL_EPS:
            if len(neg) <= 1 or neg_min == neg_max:
                t = 0.65
            else:
                t = (neg_max - v) / (neg_max - neg_min)
            colors.append(_lerp_hex(CHART_LOSS_LIGHT, CHART_LOSS_DARK, t))
        else:
            colors.append(CHART_NEUTRAL)
    return colors


def chart_charge_colors(values: list[float]) -> list[str]:
    """Map metric values to green (gain) / blue (flat) / red (loss) — no lerp ambiguity."""
    if not values:
        return []
    pos_i = neg_i = 0
    colors: list[str] = []
    for raw in values:
        v = float(raw)
        if v > CHART_NEUTRAL_EPS:
            colors.append(CHART_GAIN_VARIANTS[pos_i % len(CHART_GAIN_VARIANTS)])
            pos_i += 1
        elif v < -CHART_NEUTRAL_EPS:
            colors.append(CHART_LOSS_VARIANTS[neg_i % len(CHART_LOSS_VARIANTS)])
            neg_i += 1
        else:
            colors.append(CHART_NEUTRAL)
    return colors


SOTU_GLOW_ALPHA = 0.18
SOTU_BULL_BG = "#052e24"       # dark emerald — between canvas and BULL_BG pill
SOTU_BULL_EDGE = "#0d4a3d"     # muted green rim
SOTU_BULL_GLOW_RGB = "110,231,183"  # BULL_TEXT accent
SOTU_BEAR_BG = "#3b0a0a"       # dark crimson — aligned with BEAR_BG
SOTU_BEAR_EDGE = "#6b1515"
SOTU_BEAR_GLOW_RGB = "252,165,165"  # BEAR_TEXT accent
SOTU_NEUTRAL_BG = "#0f1a2e"    # dark navy — between bear and bull on #121212
SOTU_NEUTRAL_EDGE = "#1e3a5f"
SOTU_NEUTRAL_GLOW_RGB = "147,197,253"
SOTU_NEUTRAL_TEXT = NEUTRAL_BLUE
SOTU_AVATAR_SIZE = 128
SOTU_AVATAR_COLUMN_WIDTH = 152
DEBATE_AVATAR_SIZE = 48
ACTION_PLAN_AVATAR_SIZE = 40


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


def _rgba_rgb(rgb: str, alpha: float) -> str:
    return f"rgba({rgb},{alpha})"


def _sotu_stance(board_member_label: str) -> str:
    """Hardcoded stance from Round 2 label text — never infer from star count."""
    label = (board_member_label or "").lower()
    if "bearish" in label:
        return "bearish"
    if "bullish" in label:
        return "bullish"
    if "neutral" in label:
        return "neutral"
    return "neutral"


def sotu_quote_style(board_member_label: str) -> tuple[str, str, str]:
    """Return (background, border-left, row_glow_style) for State of the Union quote rows."""
    stance = _sotu_stance(board_member_label)
    if stance == "bullish":
        bg, edge, glow_rgb, border = SOTU_BULL_BG, SOTU_BULL_EDGE, SOTU_BULL_GLOW_RGB, BULL_TEXT
    elif stance == "bearish":
        bg, edge, glow_rgb, border = SOTU_BEAR_BG, SOTU_BEAR_EDGE, SOTU_BEAR_GLOW_RGB, BEAR_TEXT
    else:
        bg, edge, glow_rgb, border = (
            SOTU_NEUTRAL_BG,
            SOTU_NEUTRAL_EDGE,
            SOTU_NEUTRAL_GLOW_RGB,
            SOTU_NEUTRAL_TEXT,
        )
    glow = (
        f"box-shadow: inset 0 0 28px {_rgba_rgb(glow_rgb, SOTU_GLOW_ALPHA)}, "
        f"0 0 14px {_rgba_rgb(glow_rgb, SOTU_GLOW_ALPHA * 0.45)}; "
        f"border-top: 1px solid {edge}; "
        f"border-right: 1px solid {edge}; "
        f"border-bottom: 1px solid {edge};"
    )
    return bg, border, glow


def sotu_quote_colors(board_member_label: str) -> tuple[str, str]:
    """Return (background, border-left) — backward-compatible wrapper."""
    bg, border, _ = sotu_quote_style(board_member_label)
    return bg, border


def ticker_logo_inline_style(*, size: int = 28) -> str:
    """Light chip behind FMP logos so dark PNGs read on ``#27272a`` cards."""
    chip = "#f4f4f5"
    return (
        f"width:{size}px;height:{size}px;border-radius:6px;display:block;"
        f"max-width:{size}px;background-color:{chip};padding:4px;"
        f"border:1px solid #71717a;"
    )


def portrait_clip_styles(
    panelist_key: str | None = None,
    *,
    size: int = SOTU_AVATAR_SIZE,
    ring_background: str = BG_CONTAINER,
) -> dict[str, str | int]:
    """Circular portrait — ``border-radius`` on ``<img>`` (email-safe)."""
    _ = panelist_key
    _ = ring_background
    return {
        "img": (
            f"width:{size}px;height:{size}px;border-radius:50%;display:block;"
            f"border:0;margin:0 auto;padding:0;"
        ),
        "img_size": size,
    }


def sotu_avatar_img_style(panelist_key: str | None = None) -> str:
    """Email-safe face crop — zoom bust art without object-fit."""
    return portrait_clip_styles(panelist_key, size=SOTU_AVATAR_SIZE)["img"]


def format_investor_qa_summary(qa_reports: list[dict]) -> str:
    """Stealth Wealth QA strip — no emoji pass/fail marks in the investor email."""
    if not qa_reports:
        return ""
    rows: list[str] = []
    for report in qa_reports:
        role = (report.get("agent_role") or "QA Agent").strip()
        compliant = bool(report.get("is_compliant"))
        if compliant:
            badge = f'<span style="color:{BULL_TEXT};font-size:0.8em;letter-spacing:0.04em;">PASS</span>'
        else:
            badge = (
                f'<span style="color:{TEXT_PRIMARY};font-size:0.8em;letter-spacing:0.04em;">'
                f"ADVISORY</span>"
            )
        rows.append(
            f'<span style="color:{BRAND_SAGE};font-size:0.65em;vertical-align:middle;">&#9679;</span> '
            f'<strong style="color:{TEXT_HIGHLIGHT};">{role}</strong> {badge}'
        )
    return "<br>".join(rows)


def executive_briefing_inline_styles() -> dict[str, str]:
    """Inline style map for Gmail/Outlook-safe Stealth Wealth rendering.

    Email clients strip ``<head>`` rules and CSS variables; duplicate critical
    colors as inline ``style`` + ``bgcolor`` on wrapper tables.
    """
    font = "font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;"
    return {
        "body": f"margin:0;padding:0;{font}background-color:{BG_CANVAS};color:{TEXT_PRIMARY};",
        "canvas_cell": f"padding:20px;background-color:{BG_CANVAS};",
        "container_table": (
            f"max-width:800px;width:100%;background-color:{BG_CONTAINER};"
            f"border:1px solid {BORDER_SUBTLE};border-collapse:collapse;"
        ),
        "container_td": f"padding:30px;background-color:{BG_CONTAINER};color:{TEXT_PRIMARY};{font}",
        "h1": (
            f"color:{BRAND_SAGE};border-bottom:2px solid {BORDER_SUBTLE};padding-bottom:10px;"
            f"margin:0 0 20px 0;font-size:1.6em;{font}"
        ),
        "h2": (
            f"color:{BRAND_SAGE};border-bottom:1px solid {BORDER_SUBTLE};padding-bottom:5px;"
            f"margin:30px 0 15px 0;font-size:1.25em;{font}"
        ),
        "h3": f"color:{TEXT_HIGHLIGHT};margin:25px 0 10px 0;font-size:1.05em;{font}",
        "strong": f"color:{TEXT_HIGHLIGHT};",
        "p": f"color:{TEXT_PRIMARY};margin:0 0 12px 0;line-height:1.5;{font}",
        "muted_p": f"color:{TEXT_PRIMARY};font-size:0.95em;margin-top:-5px;{font}",
        "metric_box": (
            f"background-color:{BG_SURFACE};padding:15px;border-left:4px solid {BRAND_SAGE};"
            f"margin-bottom:20px;{font}color:{TEXT_PRIMARY};"
        ),
        "hedge_box": (
            f"background-color:{WARN_BG};padding:15px;border-left:4px solid {WARN_TEXT};"
            f"margin-bottom:20px;color:{WARN_TEXT};{font}"
        ),
        "crucible_box": (
            f"background-color:{CRUCIBLE_BG};padding:12px;border-left:4px solid {CRUCIBLE_BORDER};"
            f"color:{CRUCIBLE_TEXT};line-height:1.55;{font}"
        ),
        "crucible_heading": (
            f"color:{CRUCIBLE_HEADER};font-weight:700;font-size:0.95em;"
            f"letter-spacing:0.06em;text-transform:uppercase;margin:0 0 8px 0;{font}"
        ),
        "chairman_box": (
            f"background-color:{BG_SURFACE};padding:15px;border-left:4px solid {BRAND_SAGE};"
            f"font-style:italic;color:{TEXT_PRIMARY};{font}"
        ),
        "chart_title": (
            f"color:{TEXT_PRIMARY};font-size:0.68em;font-weight:600;"
            f"letter-spacing:0.12em;text-transform:uppercase;margin:0 0 6px 0;"
            f"line-height:1.35;{font}"
        ),
        "chart_container": (
            f"text-align:center;border:1px solid {BORDER_SUBTLE};padding:6px;"
            f"background-color:{BG_CANVAS};margin:0;"
        ),
        "chart_img": "max-width:100%;height:auto;display:block;margin:0 auto;border:0;",
        "chart_img_pair": (
            f"width:100%;max-width:{BRIEFING_PAIR_CHART_WIDTH}px;height:auto;"
            f"display:block;margin:0 auto;border:0;"
        ),
        "champion": f"color:{BULL_TEXT};font-weight:bold;",
        "dissenter": f"color:{BEAR_TEXT};font-weight:bold;",
        "bear_heading": f"color:{BEAR_TEXT};",
        "section_divider": f"border-bottom:1px solid {BORDER_SUBTLE};margin-bottom:20px;padding-bottom:20px;",
        "footer": (
            f"margin-top:40px;font-size:0.8em;color:{TEXT_PRIMARY};text-align:center;"
            f"border-top:1px solid {BORDER_SUBTLE};padding-top:20px;{font}"
        ),
        "li": f"color:{TEXT_PRIMARY};margin-bottom:6px;{font}",
        "ticker_logo_sm": ticker_logo_inline_style(size=28),
        "ticker_logo_md": ticker_logo_inline_style(size=48),
        "sotu_avatar_cell": (
            f"padding:12px;text-align:center;vertical-align:middle;"
            f"width:{SOTU_AVATAR_COLUMN_WIDTH}px;"
        ),
        "sotu_quote": (
            f"padding:14px 16px 14px 6px;font-style:italic;color:{TEXT_PRIMARY};line-height:1.55;{font}"
        ),
        "debate_bubble": (
            f"background-color:{BG_SURFACE};padding:14px 16px;border-radius:10px;"
            f"border:1px solid {BORDER_SUBTLE};color:{TEXT_PRIMARY};line-height:1.55;{font}"
        ),
        "debate_speaker": (
            f"color:{BRAND_SAGE};font-size:0.82em;font-weight:600;margin:0 0 6px 0;{font}"
        ),
        "debate_text": f"margin:0;color:{TEXT_PRIMARY};line-height:1.55;white-space:pre-line;{font}",
        "debate_round_label": (
            f"color:{BRAND_SAGE};font-size:0.75em;font-weight:600;letter-spacing:0.08em;"
            f"text-transform:uppercase;margin:0 0 8px 0;{font}"
        ),
        "qa_box": (
            f"margin-top:40px;font-size:0.82em;line-height:1.8;color:{TEXT_PRIMARY};"
            f"border-top:1px solid {BORDER_SUBTLE};padding-top:18px;{font}"
        ),
        "qa_box_title": (
            f"color:{BRAND_SAGE};font-size:0.72em;font-weight:600;letter-spacing:0.1em;"
            f"text-transform:uppercase;margin:0 0 10px 0;{font}"
        ),
        "actions_summary_box": (
            f"background-color:{BG_SURFACE};padding:16px 18px;border-radius:8px;"
            f"border:1px solid {BORDER_SUBTLE};margin:24px 0 8px 0;{font}color:{TEXT_PRIMARY};"
        ),
        "actions_row_cell": (
            f"padding:10px 0;border-bottom:1px solid {BORDER_SUBTLE};vertical-align:middle;{font}"
        ),
        "actions_pill": (
            "display:inline-block;padding:4px 10px;border-radius:6px;font-weight:bold;"
            "font-size:12px;white-space:nowrap;"
        ),
        "actions_symbol": f"color:{TEXT_HIGHLIGHT};font-weight:600;font-size:0.95em;{font}",
        "actions_context": f"color:{TEXT_PRIMARY};font-size:0.88em;line-height:1.45;{font}",
        "actions_unanimous_badge": (
            f"color:{BRAND_SAGE};font-size:0.68em;font-weight:600;letter-spacing:0.06em;"
            f"text-transform:uppercase;margin-left:6px;{font}"
        ),
        "actions_overflow_note": (
            f"color:{TEXT_PRIMARY};font-size:0.85em;margin:10px 0 0 0;font-style:italic;{font}"
        ),
    }


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
                padding: 8px;
                border-radius: 5px;
                background-color: var(--bg-canvas);
            }}
            .chart-title {{
                color: var(--text-primary);
                font-size: 0.68em;
                font-weight: 600;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                margin: 0 0 6px 0;
                line-height: 1.35;
            }}
            .chart-img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
            }}
            .sotu-row {{ border-radius: 8px; }}
            .debate-bubble {{ margin: 12px 0; }}
            @media only screen and (max-width: 620px) {{
                body {{ padding: 12px !important; }}
                .container {{ padding: 18px !important; }}
                .sotu-avatar-col {{
                    display: block !important;
                    width: 100% !important;
                    text-align: center;
                    padding: 14px 0 8px 0 !important;
                }}
                .sotu-quote-col {{
                    display: block !important;
                    width: 100% !important;
                    padding: 0 14px 14px 14px !important;
                }}
                .chart-img {{
                    width: 100% !important;
                    max-width: 100% !important;
                }}
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
            .candidate-preview {{
                margin-top: 50px;
                padding-top: 24px;
                border-top: 2px solid var(--border-subtle);
            }}
            .candidate-intro {{
                color: var(--text-primary);
                font-size: 0.9em;
                margin-bottom: 16px;
            }}
            .candidate-table td {{
                font-size: 13px;
            }}
            .pending-badge {{
                display: inline-block;
                padding: 3px 8px;
                border-radius: 4px;
                background: var(--bg-surface);
                color: var(--text-highlight);
                font-size: 12px;
                font-weight: bold;
            }}
            """


def qa_summary_box_html(qa_summary_text: str) -> str:
    """HTML fragment for post-render QA summary injection."""
    return (
        f'<div class="qa-box" style="margin-top:40px;font-size:0.82em;line-height:1.8;color:{TEXT_PRIMARY};'
        f'border-top:1px solid {BORDER_SUBTLE};padding-top:18px;">\n'
        f'                <div style="color:{BRAND_SAGE};font-size:0.72em;font-weight:600;'
        f'letter-spacing:0.1em;text-transform:uppercase;margin:0 0 10px 0;">'
        f"Internal QA Ledger</div>\n"
        f"                {qa_summary_text}\n"
        "            </div>"
    )


def qa_review_link_html(review_url: str) -> str:
    """Email-safe footer CTA — human QA review form (same link as QA dashboard email)."""
    safe_url = html.escape(review_url, quote=True)
    return (
        f'<p style="margin:18px 0 8px 0;">'
        f'<a href="{safe_url}" style="display:inline-block;background:{BRAND_SAGE};'
        f"color:{BG_CANVAS};padding:12px 20px;border-radius:6px;text-decoration:none;"
        f'font-weight:600;">Review QA &amp; provide feedback</a></p>'
        f'<p style="margin:0;font-size:0.85em;color:{TEXT_PRIMARY};">'
        f"Confirm or reject each QA agent&apos;s verdict for this run (2–5 min).</p>"
    )


GRAPHICS_QA_STYLE_MANDATE = f"""
[BRIEFING VISUAL SSOT — Invest AI dark premium palette]
Ground truth for rubric C (color discipline) and F (brand/tone). Do NOT flag these as wrong.

Backgrounds: canvas {BG_CANVAS}, container {BG_CONTAINER}, elevated surfaces (metric box, chart cards) {BG_SURFACE}.
Typography: primary body {TEXT_PRIMARY}; critical numbers and strong labels {TEXT_HIGHLIGHT}.
Brand accent (h1, h2, chart titles): matte sage {BRAND_SAGE}. Borders/dividers: {BORDER_SUBTLE}.

Financial semantics:
- Bullish (Buy / Strong Buy pills, champion quotes): {BULL_TEXT} on {BULL_BG}.
- Bearish (Sell / Strong Sell pills, SoTU 1–2 star): {BEAR_TEXT} on {BEAR_BG}.
- The Crucible rebuttal (Alpha Pick / Unicorn): {CRUCIBLE_TEXT} on {CRUCIBLE_BG}, {CRUCIBLE_BORDER} left accent, header {CRUCIBLE_HEADER}. NOT bear-red.
- Warning / hedge mandate: {WARN_TEXT} on {WARN_BG}.

Charts: All chart types (line, bar, pie) render natively on {CHART_CANVAS_DARK} via QuickChart (Chart.js). Do NOT apply CSS filters to chart images — filters ruin categorical color fidelity.

Chart typography (QuickChart): data labels weight {CHART_DATALABEL_WEIGHT}, off-white {CHART_DATALABEL_ON_DARK} on dark canvas; pie outlabels weight {CHART_OUTLABEL_WEIGHT} on dark canvas. Legend base size {CHART_LEGEND_FONT_SIZE}px on line chart. Flag CRITICAL if labels or legends are faint or unreadable.

Also flag CRITICAL if charts are broken, if bright white Bootstrap/SaaS blocks return, or if more than three unrelated accent hues appear outside this palette.
""".strip()


def agent_palette_digest() -> str:
    """Alias for agent prompts."""
    return GRAPHICS_QA_STYLE_MANDATE
