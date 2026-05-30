import os
import urllib.parse
import requests
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from jinja2 import Template
import logging

from src.output.briefing_enrichment import enrich_chairman_for_briefing_sync, _is_generic_synthesis

logger = logging.getLogger(__name__)

# Insertion point for post-render QA summary (deliver injects after integrity audit).
QA_SUMMARY_ANCHOR = "<!-- QA_SUMMARY_ANCHOR -->"
_CHART_PARALLEL_WORKERS = 4

def get_quickchart_short_url(chart_config, width=600, height=300, background_color="white"):
    # Prefer the short-URL endpoint: the inline GET fallback encodes the entire
    # config into the querystring, which silently breaks for large charts (e.g.
    # the benchmark line chart with a full year of points blows past URL limits).
    payload = {
        "chart": chart_config,
        "width": width,
        "height": height,
        "backgroundColor": background_color,
        "devicePixelRatio": 2,
    }
    last_err = None
    for attempt in range(2):
        try:
            response = requests.post(
                'https://quickchart.io/chart/create',
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
            url = response.json().get('url')
            if url:
                return url
            last_err = "QuickChart returned no url field."
        except Exception as e:
            last_err = e
    logger.error(f"Failed to create short URL for chart after retries: {last_err}")
    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    bkg = urllib.parse.quote(background_color)
    return f"https://quickchart.io/chart?w={width}&h={height}&bkg={bkg}&c={encoded_config}"


def _probe_image_url(url):
    """Best-effort HTTP check that a chart URL actually serves an image."""
    if not url:
        return False, "No chart generated (empty URL)."
    try:
        resp = requests.get(url, timeout=12, stream=True)
        status = resp.status_code
        ctype = resp.headers.get("content-type", "")
        resp.close()
        if status != 200:
            return False, f"HTTP {status} when fetching chart."
        if "image" not in ctype and "svg" not in ctype:
            return False, f"Non-image content-type returned: {ctype or 'unknown'}."
        return True, f"OK (HTTP 200, {ctype})."
    except Exception as e:
        return False, f"Request failed: {e}"


def audit_chart_health(chart_urls):
    """Deterministically verify each briefing chart renders. Ground truth for the
    Graphics Designer QA agent, which cannot 'see' rendered images itself."""
    labels = {
        "line_chart_url": "Performance vs. Benchmark — indexed (line)",
        "bar_chart_url": "Personal Return by Asset (bar)",
        "pie_chart_url": "Unrealized Gains (pie)",
        "account_pie_url": "12M Return by Account (pie)",
    }
    urls = chart_urls or {}

    def _probe_one(item):
        key, name = item
        url = urls.get(key, "")
        ok, detail = _probe_image_url(url)
        return {"name": name, "ok": ok, "detail": detail, "url": url}

    with ThreadPoolExecutor(max_workers=_CHART_PARALLEL_WORKERS) as pool:
        return list(pool.map(_probe_one, labels.items()))


def format_chart_health(health):
    if not health:
        return "No charts to validate."
    lines = []
    for h in health:
        status = "OK" if h["ok"] else "BROKEN"
        lines.append(f"- [{status}] {h['name']}: {h['detail']}")
    return "\n".join(lines)


def fetch_briefing_visual_assets(html: str, max_images: int = 10) -> list[dict]:
    """Download chart/avatar images embedded in the final briefing HTML.

    These bytes are what the Graphics Designer agent reviews — the same images
    a recipient's email client loads from the saved Azure artifact."""
    from bs4 import BeautifulSoup

    if not html:
        return []

    assets = []
    soup = BeautifulSoup(html, "html.parser")
    for idx, img in enumerate(soup.find_all("img")):
        if len(assets) >= max_images:
            break
        src = (img.get("src") or "").strip()
        alt = (img.get("alt") or f"briefing_image_{idx + 1}").strip()
        if not src or src.startswith("data:"):
            continue
        try:
            resp = requests.get(src, timeout=15, stream=True)
            status = resp.status_code
            ctype = (resp.headers.get("content-type") or "image/png").split(";")[0].strip().lower()
            body = resp.content
            resp.close()
            if status != 200:
                logger.warning(f"Briefing image fetch HTTP {status}: {src[:120]}")
                continue
            if not ctype.startswith("image/"):
                logger.warning(f"Briefing image non-image content-type {ctype}: {src[:120]}")
                continue
            assets.append({
                "name": alt,
                "url": src,
                "bytes": body,
                "mime_type": ctype,
            })
        except Exception as e:
            logger.warning(f"Could not fetch briefing image {src[:120]}: {e}")
    return assets

def build_unicorn_protocol_items(unicorn_trades, chairman_data, advanced_data=None, red_team_data=None):
    """Enrich unanimous panel trades with chairman narrative + Red Team rebuttals."""
    advanced_data = advanced_data or {}
    red_team_data = red_team_data or {}
    rebuttal_map = {
        r.get("symbol"): r.get("rebuttal", "")
        for r in red_team_data.get("unicorn_rebuttals", []) or []
        if r.get("symbol")
    }

    pos_by_symbol = {}
    for pos in (chairman_data or {}).get("portfolio_positions", []) + (chairman_data or {}).get("watchlist_positions", []):
        sym = pos.get("symbol")
        if sym:
            pos_by_symbol[sym] = pos

    verdict_rank = {"STRONG BUY": 0, "BUY": 1, "HOLD": 2, "TRIM": 3, "SELL": 4, "STRONG SELL": 5, "PASS": 6}
    items = []
    unicorn_symbols = set()

    for u in unicorn_trades or []:
        sym = u.get("symbol")
        panel_verdict = (u.get("verdict") or "").upper()
        if not sym or panel_verdict == "PASS":
            continue
        unicorn_symbols.add(sym)
        pos = pos_by_symbol.get(sym, {})
        narrative = pos.get("narrative") or {}
        sanitized = _sanitize_position_for_briefing(pos)
        sanitized_narrative = sanitized.get("narrative") or {}
        items.append({
            "symbol": sym,
            "verdict": panel_verdict,
            "synthesis": sanitized.get("synthesis", ""),
            "champion": sanitized_narrative.get("champion", narrative.get("champion", "")),
            "champion_quote": sanitized_narrative.get("champion_quote", ""),
            "red_team_rebuttal": _sanitize_briefing_text(rebuttal_map.get(sym, "")),
            "image": advanced_data.get(sym, {}).get("image", ""),
        })

    items.sort(key=lambda x: (verdict_rank.get(x["verdict"], 99), x["symbol"]))
    return items, unicorn_symbols


def fmt_dol(val):
    try:
        return f"${float(val):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

def fmt(val):
    try:
        return f"{float(val):.2f}%"
    except (ValueError, TypeError):
        return "0.00%"

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


# Gain/loss chart palette — light canvas (all briefing charts); brand-aligned greens/reds.
GAIN_GREEN_HIGH = "#16a34a"
GAIN_GREEN_LOW = "#bbf7d0"
LOSS_RED_HIGH = "#dc2626"
LOSS_RED_LOW = "#fecaca"
CHART_BG = "#ffffff"
CHART_LABEL_COLOR = "#111827"
CHART_AXIS_COLOR = "#374151"
CHART_GRID_COLOR = "rgba(0,0,0,0.08)"
CHART_LABEL_ON_SLICE = "#1f2937"
PIE_CHART_WIDTH = 600
PIE_CHART_HEIGHT = 420
LINE_CHART_MAX_POINTS = 12
BAR_DATALABEL_FORMATTER = (
    "function(value){return value==null?'':(Math.round(value*10)/10)+'%';}"
)


def _format_history_axis_labels(date_keys: list[str]) -> list[str]:
    """YYYYMMDD keys → compact 'May '25' labels for chart x-axes."""
    labels = []
    for key in date_keys:
        try:
            dt = datetime.strptime(str(key), "%Y%m%d")
        except ValueError:
            labels.append(str(key))
            continue
        labels.append(dt.strftime("%b '%y"))
    return labels


def _light_chart_scales(*, y_title: str, y_begin_at_zero: bool = False) -> dict:
    tick = {"color": CHART_AXIS_COLOR, "font": {"size": 10}}
    grid = {"color": CHART_GRID_COLOR}
    return {
        "y": {
            "beginAtZero": y_begin_at_zero,
            "title": {"display": True, "text": y_title, "color": CHART_AXIS_COLOR, "font": {"size": 11}},
            "ticks": tick,
            "grid": grid,
        },
        "x": {
            "ticks": {
                **tick,
                "maxTicksLimit": 6,
                "maxRotation": 0,
                "minRotation": 0,
                "autoSkip": True,
            },
            "grid": {"display": False},
        },
    }


def _outlabeled_pie_options() -> dict:
    """QuickChart outlabeledPie — legend must be boolean false, not {display: false}."""
    return {
        "plugins": {
            "legend": False,
            "datalabels": {"display": False},
            "outlabels": {
                "text": "%l %p",
                "color": CHART_LABEL_ON_SLICE,
                "stretch": 35,
                "font": {"resizable": True, "minSize": 11, "maxSize": 16, "weight": "bold"},
            },
        },
        "legend": {"display": False},
        "layout": {"padding": {"top": 8, "bottom": 8, "left": 8, "right": 8}},
    }


def _render_outlabeled_pie_chart(labels, data, colors):
    chart_config = {
        "type": "outlabeledPie",
        "data": {
            "labels": labels,
            "datasets": [{"backgroundColor": colors, "data": data}],
        },
        "options": _outlabeled_pie_options(),
    }
    return get_quickchart_short_url(chart_config, width=PIE_CHART_WIDTH, height=PIE_CHART_HEIGHT)


def colors_for_metric(values: list[float]) -> list[str]:
    """Gradual colors across the slice set — min→max spread shows disparity.

    Green ramp for gains, red ramp for losses; lighter tints at the low end
    so pie slices stay distinguishable on a white canvas.
    """
    if not values:
        return []
    gain_high, gain_low = GAIN_GREEN_HIGH, GAIN_GREEN_LOW
    loss_high, loss_low = LOSS_RED_HIGH, LOSS_RED_LOW
    vals = [float(v) for v in values]
    vmin, vmax = min(vals), max(vals)
    if vmin == vmax:
        if vmin == 0:
            mid = "#6b7280"
        elif vmin > 0:
            mid = _lerp_hex(gain_high, gain_low, 0.5)
        else:
            mid = _lerp_hex(loss_high, loss_low, 0.5)
        return [mid for _ in vals]

    if vmin < 0 < vmax:
        colors = []
        for v in vals:
            if v >= 0:
                t = v / vmax if vmax else 0.0
                colors.append(_lerp_hex(gain_high, gain_low, t))
            else:
                t = v / vmin if vmin else 0.0
                colors.append(_lerp_hex(loss_high, loss_low, t))
        return colors

    if vmin >= 0:
        low, high = gain_high, gain_low
    else:
        low, high = loss_high, loss_low
    span = vmax - vmin
    return [_lerp_hex(low, high, (v - vmin) / span) for v in vals]


def get_color_for_return(ret: float, *, vmin: float | None = None, vmax: float | None = None) -> str:
    """Single return → color. With vmin/vmax, uses the same gradual scale as charts."""
    try:
        val = float(ret)
    except (TypeError, ValueError):
        val = 0.0
    if vmin is not None and vmax is not None:
        return colors_for_metric([vmin, vmax, val])[2]
    return colors_for_metric([val])[0]


def build_portfolio_pie_chart(sorted_ledger):
    labels = []
    data = []
    returns = []
    for sym, entry in sorted_ledger:
        if sym != "BRK_LINK" and entry.get('Total', 0) > 1000:
            labels.append(sym)
            data.append(int(entry['Total']))
            returns.append(entry.get('Personal_Return_Pct', 0.0) or 0.0)

    if not data:
        return ""

    colors = colors_for_metric(returns)

    return _render_outlabeled_pie_chart(labels, data, colors)

_ACCOUNT_PIE_LABELS = {
    "eTrade Taxable": "eTrade",
    "eTrade Roth IRA": "eTrade Roth",
    "Fidelity 401K": "Fidelity 401K",
    "Fidelity Roth 401K": "Fidelity Roth 401K",
}


def build_account_allocation_pie(account_holdings, account_returns):
    """Single pie: one slice per account (% of total), colored by 12M TWR."""
    if not account_holdings:
        return ""

    rets = (account_returns or {}).get("returns", {})
    labels, data, twelves = [], [], []
    for account in ["eTrade Taxable", "eTrade Roth IRA", "Fidelity 401K", "Fidelity Roth 401K"]:
        syms = account_holdings.get(account, {})
        val = sum(info.get("value", 0) for info in syms.values())
        if val <= 1000:
            continue
        labels.append(_ACCOUNT_PIE_LABELS.get(account, account))
        data.append(int(val))
        twelves.append(rets.get(account, {}).get("12m", 0.0) or 0.0)

    if not data:
        return ""

    colors = colors_for_metric(twelves)

    return _render_outlabeled_pie_chart(labels, data, colors)

def build_returns_bar_chart(sorted_ledger):
    labels = []
    data = []
    returns = []
    for sym, entry in sorted_ledger:
        if sym != "BRK_LINK" and not sym.startswith("922"):
            ret = entry.get('Personal_Return_Pct', 0.0) or 0.0
            labels.append(sym)
            data.append(round(ret, 2))
            returns.append(ret)

    if not data:
        return ""

    colors = colors_for_metric(returns)

    chart_config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"label": "", "data": data, "backgroundColor": colors}]
        },
        "options": {
            "plugins": {
                "legend": False,
                "datalabels": {
                    "display": True,
                    "align": "end",
                    "anchor": "end",
                    "color": CHART_LABEL_COLOR,
                    "font": {"weight": "bold", "size": 12},
                    "formatter": BAR_DATALABEL_FORMATTER,
                },
            },
            "scales": _light_chart_scales(y_title="Return (%)", y_begin_at_zero=True),
            "legend": {"display": False},
        },
    }
    return get_quickchart_short_url(chart_config, background_color=CHART_BG)

def _downsample(labels, series_list, max_points=90):
    """Evenly subsample parallel label + series lists, always keeping the last point."""
    n = len(labels)
    if n <= max_points:
        return labels, series_list
    step = n / float(max_points)
    idxs = sorted(set([int(i * step) for i in range(max_points)] + [n - 1]))
    new_labels = [labels[i] for i in idxs]
    new_series = [[s[i] for i in idxs] for s in series_list]
    return new_labels, new_series


def _rebase_index_series(values):
    """Rebase a numeric series so the first valid point equals 100."""
    first = next((v for v in values if v is not None), None)
    if first in (None, 0):
        return values
    return [round(v / first * 100, 2) if v is not None else None for v in values]


_BRIEFING_JARGON_RULES: list[tuple[str, str]] = [
    (
        r"\[SYSTEM OVERRIDE:\s*10%\s*Liquidation Cap Reached\.\s*Hold enforced\.\]",
        "Position held to respect the portfolio's daily liquidation limit.",
    ),
    (
        r"\[SYSTEM OVERRIDE:\s*10%\s*Liquidation Cap Reached\.\s*Action canceled\.\]",
        "Action canceled after reaching the daily liquidation limit.",
    ),
    (
        r"\[SYSTEM OVERRIDE:\s*Sell mathematically capped at[^\]]+\]",
        "Sell size was capped by the daily liquidation limit; the verdict was adjusted accordingly.",
    ),
    (
        r"\[SYSTEM OVERRIDE:\s*Trim mathematically capped at[^\]]+\]",
        "Trim size was capped by the daily liquidation limit; the verdict was adjusted accordingly.",
    ),
    (
        r"\[SYSTEM OVERRIDE:\s*Maximum\s+\d+\s+Buys limit[^\]]+\]",
        "Held to stay within the three-buy daily limit after ranking board conviction.",
    ),
    (
        r"\[SYSTEM OVERRIDE:\s*Wash-Sale Rule[^\]]+\]",
        "Sell deferred due to wash-sale rules on a recent purchase.",
    ),
    (
        r"\[SYSTEM OVERRIDE:\s*Board majority Buy[^\]]+\]",
        "",
    ),
    (
        r"\[VOTE ENGINE\]\s*Surplus majority buy demoted[^.]+\.\s*Assigned\s+\w+\.",
        "Held to respect the three-buy daily limit after ranking board conviction.",
    ),
    (
        r"\[VOTE ENGINE\]\s*Deterministic mandate from Round 2 panel votes\s*"
        r"\(buy_side=\d/5,\s*sell_side=\d/5\)\.?",
        "The board reached a consensus mandate from today's panel vote.",
    ),
    (r"\[VOTE ENGINE\][^\n\.]*\.?", ""),
    (r"\[SYSTEM OVERRIDE:[^\]]+\]", ""),
    (
        r"(?i)\bVote-engine mandate from unanimous\s*/\s*deterministic Round 2 panel votes\.?",
        "",
    ),
    (r"(?i)\bbuy_side=\d/5,\s*sell_side=\d/5\b", ""),
    (r"(?i)\bas per the qa amendment protocol\b[,:\s]*", ""),
    (r"(?i)\bqa amendment protocol\b[,:\s]*", ""),
    (r"(?i)\btarget_tickers\b", "target allocations"),
    (r"(?i)\bmax-3 cap\b", "three-buy daily limit"),
    (r"(?i)\bdeterministically from Round 2 structured votes\b", "from today's board vote"),
]

_DEFAULT_SYNTHESIS = (
    "The investment committee finalized this position after today's board deliberation."
)

_BOILERPLATE_CHAMPION_RE = re.compile(
    r"(?i)^(vote[- ]engine mandate|deterministic mandate|pending max-3|no executed majority).*$"
)


def _sanitize_briefing_text(text: str) -> str:
    """Strip internal protocol jargon before rendering investor-facing copy."""
    if not text:
        return text
    cleaned = text
    for _ in range(3):
        prev = cleaned
        for pattern, repl in _BRIEFING_JARGON_RULES:
            cleaned = re.sub(pattern, repl, cleaned)
        if cleaned == prev:
            break
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"(?:\.\s*){2,}", ". ", cleaned)
    return cleaned.strip()


def _is_boilerplate_champion_quote(text: str) -> bool:
    if not text:
        return True
    return bool(_BOILERPLATE_CHAMPION_RE.match(text.strip()))


def _sanitize_position_for_briefing(pos: dict) -> dict:
    """Return a shallow copy with investor-facing strategic context and narrative."""
    sym = (pos.get("symbol") or "").strip()
    out = dict(pos)
    context = _sanitize_briefing_text(
        pos.get("strategic_context") or pos.get("synthesis", "")
    )
    if len(context) < 12 or _is_generic_synthesis(context):
        context = _DEFAULT_SYNTHESIS
    out["strategic_context"] = context
    out["synthesis"] = context

    narrative = dict(pos.get("narrative") or {})
    champion = (narrative.get("champion") or "Board").strip()
    champion_quote = _sanitize_briefing_text(narrative.get("champion_quote", ""))
    if _is_boilerplate_champion_quote(champion_quote):
        champion_quote = ""
    narrative["champion"] = champion
    narrative["champion_quote"] = champion_quote

    dissenter = (narrative.get("dissenter") or "None").strip() or "None"
    dissenter_quote = _sanitize_briefing_text(narrative.get("dissenter_quote", ""))
    if dissenter.upper() in {"NONE", "N/A"} or dissenter_quote.upper() in {"N/A", "NONE", ""}:
        dissenter = "None"
        dissenter_quote = "N/A"
    narrative["dissenter"] = dissenter
    narrative["dissenter_quote"] = dissenter_quote
    out["narrative"] = narrative
    return out


def _alpha_pick_displayable(alpha_pick: dict) -> bool:
    if not alpha_pick:
        return False
    sym = (alpha_pick.get("symbol") or "").strip().upper()
    if not sym or sym in {"NONE", "N/A", "NULL"}:
        return False
    quote = _sanitize_briefing_text(alpha_pick.get("champion_quote", ""))
    return bool(quote) and quote.upper() not in {"N/A", "NONE"}


from src.core.boardroom_brawl import is_boardroom_brawl_complete, split_debate_paragraphs


def _debate_has_content(brawl_text: str) -> bool:
    return is_boardroom_brawl_complete(brawl_text)


def build_benchmark_line_chart(history_data):
    if not history_data:
        return ""

    history_data = {d: dict(row) for d, row in history_data.items()}
    # Merge static benchmarks for historical context (one-time scrub data)
    import os, json
    static_path = os.path.join(os.path.dirname(__file__), "..", "data", "static_benchmarks.json")
    if os.path.exists(static_path):
        try:
            with open(static_path, "r") as f:
                static_data = json.load(f)
            for d, vals in static_data.items():
                if d not in history_data:
                    continue
                # Don't overwrite portfolio data, just backfill missing benchmarks
                if "spy" not in history_data[d] and "spy" in vals:
                    history_data[d]["spy"] = vals["spy"]
                if "qqq" not in history_data[d] and "qqq" in vals:
                    history_data[d]["qqq"] = vals["qqq"]
        except Exception:
            pass

    dates = sorted(history_data.keys())
    if len(dates) < 2:
        return ""

    # Anchor on the first date with benchmark prices; portfolio uses TWR index when available.
    anchor_idx = None
    for i, d in enumerate(dates):
        row = history_data[d]
        if row.get("spy", 0) > 0 and (
            row.get("portfolio_index") is not None or row.get("portfolio", 0) > 1000
        ):
            anchor_idx = i
            break

    if anchor_idx is None:
        return ""

    base_spy = history_data[dates[anchor_idx]].get("spy", 0)
    base_qqq = history_data[dates[anchor_idx]].get("qqq", 0)
    has_qqq = base_qqq > 0
    if base_spy <= 0:
        return ""

    port_data = []
    spy_data = []
    qqq_data = []

    for d in dates:
        row = history_data[d]
        if row.get("portfolio_index") is not None:
            port_data.append(round(float(row["portfolio_index"]), 2))
        else:
            p_val = row.get("portfolio", 0)
            base_port = history_data[dates[anchor_idx]].get("portfolio", 0)
            if p_val > 1000 and base_port > 0:
                port_data.append(round((p_val / base_port) * 100, 2))
            else:
                port_data.append(None)

        s_val = row.get("spy", 0)
        if s_val > 0 and base_spy > 0:
            spy_data.append(round((s_val / base_spy) * 100, 2))
        else:
            spy_data.append(None)

        if has_qqq:
            q_val = row.get("qqq", 0)
            if q_val > 0 and base_qqq > 0:
                qqq_data.append(round((q_val / base_qqq) * 100, 2))
            else:
                qqq_data.append(None)

    port_data, spy_data, qqq_data = (
        _rebase_index_series(port_data),
        _rebase_index_series(spy_data),
        _rebase_index_series(qqq_data),
    )

    dates, (port_data, spy_data, qqq_data) = _downsample(
        dates, [port_data, spy_data, qqq_data], max_points=LINE_CHART_MAX_POINTS,
    )
    axis_labels = _format_history_axis_labels(dates)

    datasets = [
        {
            "label": "Portfolio (TWR)",
            "data": port_data,
            "borderColor": "#60a5fa",
            "fill": False,
            "tension": 0.1,
            "spanGaps": True,
        },
        {
            "label": "S&P 500",
            "data": spy_data,
            "borderColor": "#d1d5db",
            "fill": False,
            "tension": 0.1,
            "spanGaps": True,
        },
    ]
    if has_qqq:
        datasets.append({
            "label": "NASDAQ",
            "data": qqq_data,
            "borderColor": "#34d399",
            "fill": False,
            "tension": 0.1,
            "spanGaps": True,
        })

    chart_config = {
        "type": "line",
        "data": {
            "labels": axis_labels,
            "datasets": datasets,
        },
        "options": {
            "plugins": {
                "datalabels": {"display": False},
                "title": {
                    "display": True,
                    "text": "Indexed performance (start = 100)",
                    "font": {"size": 12},
                    "color": CHART_LABEL_COLOR,
                },
                "legend": {
                    "position": "bottom",
                    "labels": {"color": CHART_AXIS_COLOR, "font": {"size": 11}},
                },
            },
            "scales": _light_chart_scales(y_title="Index"),
        },
    }
    return get_quickchart_short_url(chart_config, width=640, height=340, background_color=CHART_BG)

def build_briefing_charts(sorted_ledger, account_holdings, account_returns, history_data):
    """Build every briefing chart URL once so callers can both render and health-check
    the exact same images (avoids regenerating differing short URLs)."""
    builders = {
        "pie_chart_url": lambda: build_portfolio_pie_chart(sorted_ledger),
        "account_pie_url": lambda: build_account_allocation_pie(account_holdings, account_returns),
        "bar_chart_url": lambda: build_returns_bar_chart(sorted_ledger),
        "line_chart_url": lambda: build_benchmark_line_chart(history_data),
    }
    results = {}

    def _build_one(item):
        key, builder = item
        return key, builder()

    with ThreadPoolExecutor(max_workers=_CHART_PARALLEL_WORKERS) as pool:
        for key, url in pool.map(_build_one, builders.items()):
            results[key] = url
    return results


def _qa_summary_box_html(qa_summary_text: str) -> str:
    return (
        '<div class="qa-box">\n'
        '                <strong style="color:#4b5563;">Automated QA Audit</strong>\n'
        '                <span style="color:#9ca3af;">&mdash; see the QA Audit Dashboard for details on any &#10060;.</span><br><br>\n'
        f"                {qa_summary_text}\n"
        "            </div>"
    )


def inject_qa_summary_into_briefing(html: str, qa_summary_text: str) -> str:
    """Append the QA audit strip to a briefing rendered without qa_summary_text."""
    if not qa_summary_text:
        return html.replace(QA_SUMMARY_ANCHOR, "")
    box = _qa_summary_box_html(qa_summary_text)
    if QA_SUMMARY_ANCHOR in html:
        return html.replace(QA_SUMMARY_ANCHOR, box)
    return html.replace("</body>", f"{box}\n    </body>", 1)


def generate_html_briefing(total_val, qqq_trend, portfolio_3m_trend, mandate, chairman_data, cos_data, matrix_md, unicorn_trades, sorted_ledger, red_team_data=None, history_data=None, qa_summary_text="", account_holdings=None, account_returns=None, advanced_data=None, chart_urls=None, raw_verdicts=None, portfolio_symbols=None):

    if raw_verdicts:
        chairman_data = enrich_chairman_for_briefing_sync(
            chairman_data,
            raw_verdicts,
            portfolio_symbols=portfolio_symbols or set(),
            sanitize_fn=_sanitize_briefing_text,
        )

    if chart_urls is None:
        chart_urls = build_briefing_charts(sorted_ledger, account_holdings, account_returns, history_data)
    pie_chart_url = chart_urls.get("pie_chart_url", "")
    account_pie_url = chart_urls.get("account_pie_url", "")
    bar_chart_url = chart_urls.get("bar_chart_url", "")
    line_chart_url = chart_urls.get("line_chart_url", "")
    
    if red_team_data is None:
        red_team_data = {}

    avatar_map = {
        "Warren Buffett": "https://stboardroomprod.blob.core.windows.net/assets/buffett.jpg",
        "Peter Lynch": "https://stboardroomprod.blob.core.windows.net/assets/lynch.jpg",
        "Jesse Livermore": "https://stboardroomprod.blob.core.windows.net/assets/livermore.jpg",
        "Jensen Huang": "https://stboardroomprod.blob.core.windows.net/assets/huang.jpg",
        "Jim Simons": "https://stboardroomprod.blob.core.windows.net/assets/simons.jpg"
    }

    sotu_quotes = cos_data.get('state_of_the_union_quotes', [])
    for quote in sotu_quotes:
        base_name = quote.get('board_member', '').split(' (')[0].strip()
        quote['avatar_url'] = avatar_map.get(base_name, "https://ui-avatars.com/api/?name=AI&background=333&color=fff&rounded=true&size=128")

    brawl_text = cos_data.get('boardroom_brawl', 'The board evaluated the portfolio without major conflict.')
    known_tickers = [sym for sym, _ in sorted_ledger] + ["SPY", "QQQ"]
    for ticker in set(known_tickers):
        brawl_text = re.sub(rf'\b({ticker})\b', rf'<strong>\1</strong>', brawl_text)

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            h1 { color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }
            h2 { color: #2563eb; margin-top: 30px; border-bottom: 1px solid #e5e7eb; padding-bottom: 5px;}
            h3 { color: #374151; margin-top: 25px; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; }
            h4 { color: #111827; margin-bottom: 5px; }
            .metric-box { background-color: #f8fafc; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #2563eb; }
            .hedge-box { background-color: #fffbeb; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #d97706; color: #92400e; }
            .red-team-box { background-color: #fef2f2; padding: 12px; border-radius: 4px; border-left: 4px solid #dc2626; color: #991b1b; }
            .champion { color: #166534; font-weight: bold; }
            .dissenter { color: #991b1b; font-weight: bold; }
            .verdict-pill { display: inline-block; padding: 6px 14px; border-radius: 6px; font-weight: bold; font-size: 13px; letter-spacing: 0.5px; margin-bottom: 12px; border: 1px solid rgba(0,0,0,0.06); }
            .chart-container { margin: 0; text-align: center; border: 1px solid #e5e7eb; padding: 10px; border-radius: 5px; background-color: #ffffff; }
            .chart-title { color: #2563eb; font-size: 1.3em; font-weight: 600; margin: 0 0 10px 0; padding-bottom: 5px; border-bottom: 1px solid #e5e7eb; }
            .chart-img { max-width: 100%; height: auto; display: block; margin: 0 auto; }
            .footer { margin-top: 40px; font-size: 0.8em; color: #6b7280; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; }
            .qa-box { margin-top: 40px; font-size: 0.85em; line-height: 1.7; color: #6b7280; border-top: 1px dashed #e5e7eb; padding-top: 15px; }
        </style>
    </head>
    <body>
        <div class="container">
            {% set pill_styles = {
                'STRONG BUY': 'background-color:#dcfce7; color:#166534;',
                'BUY': 'background-color:#dcfce7; color:#166534;',
                'HOLD': 'background-color:#f3f4f6; color:#374151;',
                'TRIM': 'background-color:#fef3c7; color:#92400e;',
                'SELL': 'background-color:#fee2e2; color:#991b1b;',
                'STRONG SELL': 'background-color:#fee2e2; color:#991b1b;'
            } %}
            <h1>Invest AI: Executive Briefing{% if briefing_date %} &mdash; {{ briefing_date }}{% endif %}</h1>
            
            <div class="metric-box">
                <strong>Portfolio Value:</strong> {{ total_val }}<br>
                <strong>3M Trend — Portfolio:</strong> {{ portfolio_3m_trend }} &nbsp;|&nbsp; <strong>QQQ:</strong> {{ qqq_trend }}<br>
                <strong>Current CAGR:</strong> {{ cagr_text }} &nbsp;|&nbsp; <strong>Projected Balance (Age 65):</strong> {{ proj_text }}
            </div>

            {% if line_chart_url or bar_chart_url %}
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top: 30px; border-collapse: separate; border-spacing: 0;">
                <tr>
                    {% if line_chart_url %}
                    <td valign="top" width="{{ '50%' if bar_chart_url else '100%' }}" style="padding: 0 {{ '10px' if bar_chart_url else '0' }} 0 0;">
                        <div class="chart-title">Performance vs. Benchmark (indexed)</div>
                        <div class="chart-container">
                            <img class="chart-img" src="{{ line_chart_url }}" alt="Benchmark Performance Line Chart">
                        </div>
                    </td>
                    {% endif %}
                    {% if bar_chart_url %}
                    <td valign="top" width="{{ '50%' if line_chart_url else '100%' }}" style="padding: 0 0 0 {{ '10px' if line_chart_url else '0' }};">
                        <div class="chart-title">Personal Return by Asset</div>
                        <div class="chart-container">
                            <img class="chart-img" src="{{ bar_chart_url }}" alt="Portfolio Returns Bar Chart">
                        </div>
                    </td>
                    {% endif %}
                </tr>
            </table>
            {% endif %}

            {% if pie_chart_url or account_pie_url %}
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top: 30px; border-collapse: separate; border-spacing: 0;">
                <tr>
                    {% if pie_chart_url %}
                    <td valign="top" width="{{ '50%' if account_pie_url else '100%' }}" style="padding: 0 {{ '10px' if account_pie_url else '0' }} 0 0;">
                        <div class="chart-title">Unrealized Gains</div>
                        <div class="chart-container">
                            <img class="chart-img" src="{{ pie_chart_url }}" alt="Unrealized Gains Pie Chart">
                        </div>
                    </td>
                    {% endif %}
                    {% if account_pie_url %}
                    <td valign="top" width="{{ '50%' if pie_chart_url else '100%' }}" style="padding: 0 0 0 {{ '10px' if pie_chart_url else '0' }};">
                        <div class="chart-title">12M Return by Account</div>
                        <div class="chart-container">
                            <img class="chart-img" src="{{ account_pie_url }}" alt="1 Yr Return Pie Chart">
                        </div>
                    </td>
                    {% endif %}
                </tr>
            </table>
            {% endif %}

            {% if sotu_quotes %}
            <h2>The State of the Union</h2>
            {% for quote in sotu_quotes %}
                {% set box_color = '#f9fafb' %}
                {% set border_color = '#9ca3af' %}
                
                {% if '⭐⭐⭐⭐' in quote.board_member %}
                    {% set box_color = '#dcfce7' %}
                    {% set border_color = '#22c55e' %}
                {% elif '⭐⭐⭐' in quote.board_member %}
                    {% set box_color = '#dbeafe' %}
                    {% set border_color = '#3b82f6' %}
                {% elif '⭐⭐' in quote.board_member or '⭐' in quote.board_member %}
                    {% set box_color = '#fee2e2' %}
                    {% set border_color = '#ef4444' %}
                {% endif %}
                
                <table width="100%" cellpadding="0" cellspacing="0" style="margin: 10px 0; border-left: 4px solid {{ border_color }}; background-color: {{ box_color }}; border-radius: 4px;">
                    <tr>
                        <td width="65" valign="top" style="padding: 15px 0 15px 15px;">
                            <img src="{{ quote.avatar_url }}" style="width: 50px; height: 50px; border-radius: 50%; display: block; max-width: 50px;" alt="{{ quote.board_member }} avatar">
                        </td>
                        <td valign="middle" style="padding: 15px; font-style: italic;">
                            <strong>{{ quote.board_member }}:</strong> "{{ quote.quote }}"
                        </td>
                    </tr>
                </table>
            {% endfor %}
            {% endif %}

            {% if show_alpha_pick %}
            <h2>🎯 The Alpha Pick</h2>
            <div class="metric-box" style="border-left-color: #f59e0b;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 10px;">
                    <tr>
                        {% if alpha_pick.image %}
                        <td valign="top" width="63" style="padding-right: 15px;">
                            <img src="{{ alpha_pick.image }}" alt="{{ alpha_pick.symbol }} logo" style="width: 48px; height: 48px; border-radius: 6px; display: block; max-width: 48px; background-color: #ffffff;">
                        </td>
                        {% endif %}
                        <td valign="top">
                            <p style="margin-top: 0; font-size: 1.1em;"><strong>{{ alpha_pick.symbol }}</strong>: "{{ alpha_pick.champion_quote }}"</p>
                        </td>
                    </tr>
                </table>
                
                {% if red_team_case %}
                <h3 style="margin-top: 20px; margin-bottom: 10px; font-size: 1.05em; color: #991b1b; border-bottom: none;">⚠️ The Bear Case Rebuttal</h3>
                <div class="red-team-box">
                    {{ red_team_case }}
                </div>
                {% endif %}
            </div>
            {% endif %}

            <h2>The Action Plan</h2>

            {% if hedge_action %}
            <div class="hedge-box">
                <strong>🛡️ Risk Management Mandate:</strong> {{ hedge_action }}
            </div>
            {% endif %}

            {% set action_categories = ['STRONG BUY', 'BUY', 'HOLD', 'TRIM', 'SELL', 'STRONG SELL'] %}
            {% for category in action_categories %}
                {% if grouped_actions[category] %}
                    {% for pos in grouped_actions[category] %}
                        <div style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #e5e7eb;">
                            <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom: 12px;">
                                <tr>
                                    {% if pos.image %}
                                    <td valign="middle" style="padding-right: 12px;">
                                        <img src="{{ pos.image }}" alt="{{ pos.symbol }} logo" style="width: 28px; height: 28px; border-radius: 4px; display: block; max-width: 28px; background-color: #ffffff;">
                                    </td>
                                    {% endif %}
                                    <td valign="middle">
                                        <span class="verdict-pill" style="{{ pill_styles[category] }} margin-bottom: 0;">{{ category }} : {{ pos.symbol }}</span>
                                    </td>
                                </tr>
                            </table>
                            <p><strong>Strategic Context:</strong> {{ pos.strategic_context or pos.synthesis }}</p>
                            {% if pos.narrative and pos.narrative.champion_quote %}
                                <p><span class="champion">The Champion ({{ pos.narrative.champion }}):</span> "{{ pos.narrative.champion_quote }}"</p>
                                <p><span class="dissenter">The Dissent ({{ pos.narrative.dissenter or 'None' }}):</span> "{{ pos.narrative.dissenter_quote or 'N/A' }}"</p>
                            {% endif %}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endfor %}

            {% if show_debate %}
            <h2>The Debate</h2>
            {% for paragraph in debate_paragraphs %}
                <p>{{ paragraph }}</p>
            {% endfor %}
            {% endif %}
            
            {% if unicorn_protocol_items %}
            <h2>🦄 Unicorn Protocol</h2>
            <p style="color:#6b7280; font-size:0.95em; margin-top:-5px;">Unanimous board verdict — full context with Red Team rebuttal.</p>
            {% for item in unicorn_protocol_items %}
                <div style="margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid #e5e7eb;">
                    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom: 12px;">
                        <tr>
                            {% if item.image %}
                            <td valign="middle" style="padding-right: 12px;">
                                <img src="{{ item.image }}" alt="{{ item.symbol }} logo" style="width: 28px; height: 28px; border-radius: 4px; display: block; max-width: 28px; background-color: #ffffff;">
                            </td>
                            {% endif %}
                            <td valign="middle">
                                <span class="verdict-pill" style="{{ pill_styles[item.verdict] if item.verdict in pill_styles else pill_styles['HOLD'] }} margin-bottom: 0;">{{ item.verdict }} : {{ item.symbol }}</span>
                            </td>
                        </tr>
                    </table>
                    {% if item.synthesis %}
                    <p><strong>Strategic Context:</strong> {{ item.synthesis }}</p>
                    {% endif %}
                    {% if item.champion_quote %}
                    <p><span class="champion">The Champion ({{ item.champion }}):</span> "{{ item.champion_quote }}"</p>
                    {% endif %}
                    {% if item.red_team_rebuttal %}
                    <p style="margin-top: 12px; margin-bottom: 6px; font-weight: bold; color: #991b1b;">⚠️ Red Team Rebuttal</p>
                    <div class="red-team-box">{{ item.red_team_rebuttal }}</div>
                    {% endif %}
                </div>
            {% endfor %}
            {% endif %}
            
            {% if chairman_remarks %}
            <h2>Chairman's Closing Thoughts</h2>
            <div style="background-color: #f8fafc; padding: 15px; border-radius: 5px; border-left: 4px solid #4f46e5; font-style: italic;">
                <p style="margin: 0;">"{{ chairman_remarks }}"</p>
            </div>
            {% endif %}

            <h2>Upcoming Catalysts</h2>
            <ul>
            {% for event in events %}
                <li><strong>{{ event.symbol }}</strong>: {{ event.event_detail }} <em>{{ event.impact }}</em></li>
            {% else %}
                <li>No major immediate catalysts flagged.</li>
            {% endfor %}
            </ul>

            <div class="footer">
                Invest AI Daily Briefing<br>
                Data provided by Financial Modeling Prep and brokerage activity logs.
            </div>
            
            {% if qa_summary_text %}
            <div class="qa-box">
                <strong style="color:#4b5563;">Automated QA Audit</strong>
                <span style="color:#9ca3af;">&mdash; see the QA Audit Dashboard for details on any &#10060;.</span><br><br>
                {{ qa_summary_text }}
            </div>
            {% else %}
            <!-- QA_SUMMARY_ANCHOR -->
            {% endif %}
        </div>
    </body>
    </html>
    """

    unicorn_trades = [u for u in unicorn_trades if u['verdict'].upper() != 'PASS']
    unicorn_protocol_items, unicorn_symbols = build_unicorn_protocol_items(
        unicorn_trades, chairman_data, advanced_data, red_team_data
    )

    all_positions = chairman_data.get('portfolio_positions', []) + chairman_data.get('watchlist_positions', [])
    
    if advanced_data is None: advanced_data = {}
    grouped_actions = {cat: [] for cat in ['STRONG BUY', 'BUY', 'HOLD', 'TRIM', 'SELL', 'STRONG SELL']}
    for pos in all_positions:
        sym = pos.get('symbol')
        if sym in unicorn_symbols:
            continue
        verdict = pos.get('final_verdict', 'Pass').upper()
        if verdict in grouped_actions:
            sanitized = _sanitize_position_for_briefing(pos)
            sanitized['image'] = advanced_data.get(sym, {}).get('image', '')
            grouped_actions[verdict].append(sanitized)
            
    for cat in grouped_actions:
        grouped_actions[cat].sort(key=lambda x: x.get('aggregate_conviction_score', 0), reverse=True)

    alpha_pick = chairman_data.get('alpha_pick', {})
    if alpha_pick and 'symbol' in alpha_pick:
        alpha_pick['image'] = advanced_data.get(alpha_pick['symbol'], {}).get('image', '')
        alpha_pick['champion_quote'] = _sanitize_briefing_text(alpha_pick.get('champion_quote', ''))
    show_alpha_pick = _alpha_pick_displayable(alpha_pick)
        
    events = chairman_data.get('upcoming_events', [])
    red_team_case = _sanitize_briefing_text(red_team_data.get('bear_case_narrative', ''))
    chairman_remarks = _sanitize_briefing_text(chairman_data.get('chairman_closing_remarks', ''))
    show_debate = _debate_has_content(brawl_text)
    debate_paragraphs = split_debate_paragraphs(brawl_text)
    
    hedge_action = chairman_data.get('capital_allocation_narrative', '') if 'hedge' in chairman_data.get('capital_allocation_narrative', '').lower() else ''
    hedge_action = _sanitize_briefing_text(hedge_action)

    from src.config.settings import now_local
    briefing_date = now_local().strftime("%B %d, %Y")

    cagr_match = re.search(r"CAGR of ([\d\.]+)\s*percent", mandate, re.I)
    proj_match = re.search(r"projected balance at age 65 is (\$[\d\.,]+)", mandate)
    cagr_text = f"{cagr_match.group(1)}%" if cagr_match else "N/A"
    proj_text = proj_match.group(1) if proj_match else "N/A"

    template = Template(html_template)
    rendered_html = template.render(
        total_val=fmt_dol(total_val),
        qqq_trend=fmt(qqq_trend),
        portfolio_3m_trend=fmt(portfolio_3m_trend),
        cagr_text=cagr_text,
        proj_text=proj_text,
        sotu_quotes=sotu_quotes,
        brawl_text=brawl_text,
        debate_paragraphs=debate_paragraphs,
        unicorn_protocol_items=unicorn_protocol_items,
        grouped_actions=grouped_actions,
        alpha_pick=alpha_pick,
        show_alpha_pick=show_alpha_pick,
        show_debate=show_debate,
        briefing_date=briefing_date,
        events=events,
        pie_chart_url=pie_chart_url,
        account_pie_url=account_pie_url,
        bar_chart_url=bar_chart_url,
        line_chart_url=line_chart_url,
        red_team_case=red_team_case,
        hedge_action=hedge_action,
        chairman_remarks=chairman_remarks,
        qa_summary_text=qa_summary_text
    )

    return rendered_html

def generate_qa_dashboard_html(reports, timestamp, review_url: str = None):
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 20px; }
            .container { max-width: 1000px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            h1 { color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }
            h2 { color: #2563eb; margin-top: 30px; border-bottom: 1px solid #e5e7eb; padding-bottom: 5px;}
            h3 { color: #374151; margin-top: 25px; margin-bottom: 10px; }
            .status-badge { display: inline-block; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 14px; margin-bottom: 15px; }
            .status-pass { background-color: #dcfce7; color: #166534; border: 1px solid #22c55e; }
            .status-fail { background-color: #fee2e2; color: #991b1b; border: 1px solid #ef4444; }
            
            table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
            th { text-align: left; padding: 10px; background-color: #f8fafc; border-bottom: 2px solid #e5e7eb; color: #4b5563; }
            td { padding: 12px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
            
            .sev-CRITICAL { color: #dc2626; font-weight: bold; }
            .sev-WARNING { color: #d97706; font-weight: bold; }
            .sev-INFO { color: #2563eb; font-weight: bold; }
            
            .summary-box { background-color: #f8fafc; padding: 15px; border-radius: 5px; border-left: 4px solid #64748b; font-style: italic; margin-bottom: 20px; }
            .footer { margin-top: 40px; font-size: 0.8em; color: #6b7280; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Invest AI: QA Audit Dashboard</h1>
            <p style="color: #6b7280; margin-top: -10px; margin-bottom: 30px;">Generated: {{ timestamp }}</p>
            
            <h2>QA Agents Summary</h2>
            <table style="margin-bottom: 40px;">
                <tr>
                    <th width="70%">Agent Role</th>
                    <th width="30%">Status</th>
                </tr>
                {% for report in reports %}
                <tr>
                    <td><strong>{{ report.agent_role }}</strong></td>
                    <td>
                        {% if report.is_compliant %}
                            <span style="color: #166534; font-weight: bold;">✅ PASS</span>
                        {% else %}
                            <span style="color: #dc2626; font-weight: bold;">❌ FAIL</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>
            
            {% for report in reports %}
            <div style="margin-bottom: 50px;">
                <h2>{{ report.agent_role }} Audit</h2>
                
                {% if report.is_compliant %}
                    <span class="status-badge status-pass">✅ AUDIT PASSED</span>
                {% else %}
                    <span class="status-badge status-fail">❌ AUDIT FAILED</span>
                {% endif %}
                
                <div class="summary-box">
                    {{ report.summary }}
                </div>
                
                {% if report.findings %}
                <h3>Detailed Findings</h3>
                <table>
                    <tr>
                        <th width="10%">Severity</th>
                        <th width="15%">Category</th>
                        <th width="40%">Description</th>
                        <th width="35%">Recommendation</th>
                    </tr>
                    {% for finding in report.findings %}
                    <tr>
                        <td class="sev-{{ finding.severity }}">{{ finding.severity }}</td>
                        <td>{{ finding.category }}</td>
                        <td>{{ finding.description }}</td>
                        <td>{{ finding.recommendation }}</td>
                    </tr>
                    {% endfor %}
                </table>
                {% else %}
                <p style="color: #6b7280; font-style: italic;">No specific findings reported.</p>
                {% endif %}
            </div>
            {% endfor %}
            
            <div class="footer">
                Automated Post-Flight Quality Assurance Report.<br>
                {% if review_url %}
                <p style="margin: 16px 0;"><a href="{{ review_url }}" style="display:inline-block;background:#2563eb;color:#ffffff;padding:12px 20px;border-radius:6px;text-decoration:none;font-weight:bold;">Review QA accuracy for this run</a></p>
                <p style="font-size: 0.85em;">Confirm or reject each QA agent's verdict (2–5 min). Link requires your review token.</p>
                {% endif %}
                Invest AI Boardroom
            </div>
        </div>
    </body>
    </html>
    """
    
    template = Template(html_template)
    return template.render(reports=reports, timestamp=timestamp, review_url=review_url)