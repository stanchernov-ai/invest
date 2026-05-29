import os
import urllib.parse
import requests
import json
import re
from jinja2 import Template
import logging

logger = logging.getLogger(__name__)

def get_quickchart_short_url(chart_config, width=600, height=300):
    # Prefer the short-URL endpoint: the inline GET fallback encodes the entire
    # config into the querystring, which silently breaks for large charts (e.g.
    # the benchmark line chart with a full year of points blows past URL limits).
    payload = {
        "chart": chart_config,
        "width": width,
        "height": height,
        "backgroundColor": "white",
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
    return f"https://quickchart.io/chart?w={width}&h={height}&bkg=white&c={encoded_config}"


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
        "line_chart_url": "Performance vs. Benchmark (line)",
        "bar_chart_url": "Personal Return by Asset (bar)",
        "pie_chart_url": "Unrealized Gains (pie)",
        "account_pie_url": "12M Return by Account (pie)",
    }
    health = []
    for key, name in labels.items():
        url = (chart_urls or {}).get(key, "")
        ok, detail = _probe_image_url(url)
        health.append({"name": name, "ok": ok, "detail": detail, "url": url})
    return health


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

def get_color_for_return(ret):
    if ret >= 20: return "#166534"
    elif ret >= 10: return "#22c55e"
    elif ret >= 0: return "#86efac"
    elif ret <= -20: return "#991b1b"
    elif ret <= -10: return "#ef4444"
    else: return "#fca5a5"

def build_portfolio_pie_chart(sorted_ledger):
    labels = []
    data = []
    colors = []
    for sym, entry in sorted_ledger:
        if sym != "BRK_LINK" and entry.get('Total', 0) > 1000:
            labels.append(sym)
            data.append(int(entry['Total']))
            colors.append(get_color_for_return(entry.get('Personal_Return_Pct', 0.0)))
            
    if not data:
        return ""
        
    chart_config = {
        "type": "outlabeledPie",
        "data": {
            "labels": labels,
            "datasets": [{"backgroundColor": colors, "data": data}]
        },
        "options": {
            "plugins": {
                "legend": {"display": False},
                "outlabels": {"text": "%l %p", "color": "white", "stretch": 35, "font": {"resizable": True, "minSize": 12, "maxSize": 18}}
            }
        }
    }
    return get_quickchart_short_url(chart_config)

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
    labels, data, colors = [], [], []
    for account in ["eTrade Taxable", "eTrade Roth IRA", "Fidelity 401K", "Fidelity Roth 401K"]:
        syms = account_holdings.get(account, {})
        val = sum(info.get("value", 0) for info in syms.values())
        if val <= 1000:
            continue
        labels.append(_ACCOUNT_PIE_LABELS.get(account, account))
        data.append(int(val))
        twelve = rets.get(account, {}).get("12m", 0.0) or 0.0
        colors.append(get_color_for_return(twelve))

    if not data:
        return ""

    chart_config = {
        "type": "outlabeledPie",
        "data": {
            "labels": labels,
            "datasets": [{"backgroundColor": colors, "data": data}]
        },
        "options": {
            "plugins": {
                "legend": {"display": False},
                "outlabels": {
                    "text": "%l %p",
                    "color": "white",
                    "stretch": 35,
                    "font": {"resizable": True, "minSize": 12, "maxSize": 18}
                }
            }
        }
    }
    return get_quickchart_short_url(chart_config)

def build_returns_rows(account_returns):
    """Flatten the history-engine output into display rows (Total first)."""
    if not account_returns or not account_returns.get("returns"):
        return []
    order = ["Total", "eTrade Taxable", "eTrade Roth IRA", "Fidelity 401K", "Fidelity Roth 401K"]
    rets = account_returns["returns"]
    rows = []
    for name in order:
        if name not in rets:
            continue
        ytd = rets[name].get("ytd", 0.0) or 0.0
        twelve = rets[name].get("12m", 0.0) or 0.0
        rows.append({
            "name": name,
            "ytd": ytd, "ytd_color": "#166534" if ytd >= 0 else "#991b1b",
            "twelve": twelve, "twelve_color": "#166534" if twelve >= 0 else "#991b1b",
        })
    return rows

def build_returns_bar_chart(sorted_ledger):
    labels = []
    data = []
    colors = []
    for sym, entry in sorted_ledger:
        if sym != "BRK_LINK" and not sym.startswith("922"):
            ret = entry.get('Personal_Return_Pct', 0.0)
            labels.append(sym)
            data.append(round(ret, 2))
            colors.append('rgba(22, 101, 52, 0.8)' if ret >= 0 else 'rgba(153, 27, 27, 0.8)')
            
    if not data:
        return ""

    chart_config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"label": "Unrealized Return Percentage", "data": data, "backgroundColor": colors}]
        },
        "options": {
            "plugins": {
                "datalabels": {"display": True, "align": "end", "anchor": "end", "color": "#374151"}
            },
            "scales": {
                "y": {"beginAtZero": True}
            }
        }
    }
    return get_quickchart_short_url(chart_config)

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


def build_benchmark_line_chart(history_data):
    if not history_data:
        return ""

    # Merge static benchmarks for historical context (one-time scrub data)
    import os, json
    static_path = os.path.join(os.path.dirname(__file__), "..", "data", "static_benchmarks.json")
    if os.path.exists(static_path):
        try:
            with open(static_path, "r") as f:
                static_data = json.load(f)
            for d, vals in static_data.items():
                if d not in history_data:
                    history_data[d] = vals
                else:
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

    # Anchor the chart on the first date with a meaningful portfolio value.
    base_port = 0
    base_spy = 0
    base_qqq = 0
    for d in dates:
        row = history_data[d]
        if row.get("portfolio", 0) > 1000 and row.get("spy", 0) > 0:
            base_port = row.get("portfolio")
            base_spy = row.get("spy")
            base_qqq = row.get("qqq", 0)
            break

    if base_port <= 0 or base_spy <= 0:
        return ""
    has_qqq = base_qqq > 0

    port_data = []
    spy_data = []
    qqq_data = []

    for d in dates:
        p_val = history_data[d].get("portfolio", 0)
        s_val = history_data[d].get("spy", 0)
        
        if p_val > 1000 and base_port > 0:
            port_data.append(round(((p_val - base_port) / base_port) * 100, 2))
        else:
            port_data.append(None)
            
        if s_val > 0 and base_spy > 0:
            spy_data.append(round(((s_val - base_spy) / base_spy) * 100, 2))
        else:
            spy_data.append(None)
            
        if has_qqq:
            q_val = history_data[d].get("qqq", 0)
            if q_val > 0 and base_qqq > 0:
                qqq_data.append(round(((q_val - base_qqq) / base_qqq) * 100, 2))
            else:
                qqq_data.append(None)

    # Downsample to keep the QuickChart config compact. A full trailing-12-month
    # daily series (~250 pts) bloats the URL/payload; ~90 evenly-spaced points
    # render an identical-looking line at a fraction of the size.
    dates, (port_data, spy_data, qqq_data) = _downsample(dates, [port_data, spy_data, qqq_data])

    datasets = [
        {"label": "Portfolio", "data": port_data, "borderColor": "#2563eb", "fill": False, "tension": 0.1, "spanGaps": True},
        {"label": "S&P 500", "data": spy_data, "borderColor": "#9ca3af", "fill": False, "tension": 0.1, "spanGaps": True},
    ]
    if has_qqq:
        datasets.append({"label": "NASDAQ", "data": qqq_data, "borderColor": "#10b981", "fill": False, "tension": 0.1, "spanGaps": True})

    chart_config = {
        "type": "line",
        "data": {
            "labels": dates,
            "datasets": datasets
        },
        "options": {
            "plugins": {
                "datalabels": {"display": False}
            },
            "scales": {
                "y": {"beginAtZero": False}
            }
        }
    }
    return get_quickchart_short_url(chart_config)

def build_briefing_charts(sorted_ledger, account_holdings, account_returns, history_data):
    """Build every briefing chart URL once so callers can both render and health-check
    the exact same images (avoids regenerating differing short URLs)."""
    return {
        "pie_chart_url": build_portfolio_pie_chart(sorted_ledger),
        "account_pie_url": build_account_allocation_pie(account_holdings, account_returns),
        "bar_chart_url": build_returns_bar_chart(sorted_ledger),
        "line_chart_url": build_benchmark_line_chart(history_data),
    }


def generate_html_briefing(total_val, qqq_trend, portfolio_3m_trend, mandate, chairman_data, cos_data, matrix_md, unicorn_trades, sorted_ledger, red_team_data=None, history_data=None, qa_summary_text="", account_holdings=None, account_returns=None, advanced_data=None, chart_urls=None):

    if chart_urls is None:
        chart_urls = build_briefing_charts(sorted_ledger, account_holdings, account_returns, history_data)
    pie_chart_url = chart_urls.get("pie_chart_url", "")
    account_pie_url = chart_urls.get("account_pie_url", "")
    bar_chart_url = chart_urls.get("bar_chart_url", "")
    line_chart_url = chart_urls.get("line_chart_url", "")
    returns_rows = build_returns_rows(account_returns)
    returns_updated = (account_returns or {}).get("updated", "")
    
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
            <h1>Invest AI: Executive Briefing</h1>
            
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
                        <div class="chart-title">Performance vs. Benchmark</div>
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
                        <div class="chart-title">1 Yr Return</div>
                        <div class="chart-container">
                            <img class="chart-img" src="{{ account_pie_url }}" alt="1 Yr Return Pie Chart">
                        </div>
                    </td>
                    {% endif %}
                </tr>
            </table>
            {% endif %}

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
                            <img src="{{ quote.avatar_url }}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover; display: block;" alt="Avatar">
                        </td>
                        <td valign="middle" style="padding: 15px; font-style: italic;">
                            <strong>{{ quote.board_member }}:</strong> "{{ quote.quote }}"
                        </td>
                    </tr>
                </table>
            {% endfor %}

            {% if alpha_pick %}
            <h2>🎯 The Alpha Pick</h2>
            <div class="metric-box" style="border-left-color: #f59e0b;">
                <div style="display: flex; align-items: flex-start; margin-bottom: 10px;">
                    {% if alpha_pick.image %}
                    <img src="{{ alpha_pick.image }}" alt="{{ alpha_pick.symbol }} logo" style="width: 48px; height: 48px; border-radius: 6px; margin-right: 15px; object-fit: contain; background-color: #ffffff; flex-shrink: 0;">
                    {% endif %}
                    <p style="margin-top: 0; font-size: 1.1em;"><strong>{{ alpha_pick.symbol }}</strong>: "{{ alpha_pick.champion_quote }}"</p>
                </div>
                
                {% if red_team_case %}
                <h3 style="margin-top: 20px; margin-bottom: 10px; font-size: 1.05em; color: #991b1b; border-bottom: none;">⚠️ The Bear Case Rebuttal</h3>
                <div class="red-team-box">
                    {{ red_team_case }}
                </div>
                {% endif %}
            </div>
            {% endif %}

            <h2>The Debate</h2>
            {% for paragraph in brawl_text.split('\\n') %}
                {% if paragraph.strip() %}
                    <p>{{ paragraph.strip() }}</p>
                {% endif %}
            {% endfor %}
            
            {% if unicorn_trades_grouped %}
            <h2>🦄 Unicorn Protocol</h2>
            <div style="margin-left: 20px;">
            {% for verdict, symbols in unicorn_trades_grouped.items() %}
                <div style="display: flex; margin-bottom: 8px;">
                    <div style="font-weight: bold; width: 120px;">{{ verdict }}:</div>
                    <div>
                        {% for sym in symbols %}
                            <div>{{ sym }}</div>
                        {% endfor %}
                    </div>
                </div>
            {% endfor %}
            </div>
            {% endif %}

            <h2>The Action Plan</h2>
            
            {% if hedge_action %}
            <div class="hedge-box">
                <strong>🛡️ Risk Management Mandate:</strong> {{ hedge_action }}
            </div>
            {% endif %}

            {% set action_categories = ['STRONG BUY', 'BUY', 'HOLD', 'TRIM', 'SELL', 'STRONG SELL'] %}
            {% set pill_styles = {
                'STRONG BUY':  'background-color:#dcfce7; color:#166534;',
                'BUY':         'background-color:#dcfce7; color:#166534;',
                'HOLD':        'background-color:#f3f4f6; color:#374151;',
                'TRIM':        'background-color:#fef3c7; color:#92400e;',
                'SELL':        'background-color:#fee2e2; color:#991b1b;',
                'STRONG SELL': 'background-color:#fee2e2; color:#991b1b;'
            } %}
            {% for category in action_categories %}
                {% if grouped_actions[category] %}
                    {% for pos in grouped_actions[category] %}
                        <div style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #e5e7eb;">
                            <div style="display: flex; align-items: center; margin-bottom: 12px;">
                                {% if pos.image %}
                                <img src="{{ pos.image }}" alt="{{ pos.symbol }} logo" style="width: 28px; height: 28px; border-radius: 4px; margin-right: 12px; object-fit: contain; background-color: #ffffff;">
                                {% endif %}
                                <span class="verdict-pill" style="{{ pill_styles[category] }} margin-bottom: 0;">{{ category }} : {{ pos.symbol }}</span>
                            </div>
                            <p><strong>Strategic Context:</strong> {{ pos.synthesis }}</p>
                            {% if pos.narrative %}
                                <p><span class="champion">The Champion ({{ pos.narrative.champion }}):</span> "{{ pos.narrative.champion_quote }}"</p>
                                <p><span class="dissenter">The Dissent ({{ pos.narrative.dissenter }}):</span> "{{ pos.narrative.dissenter_quote }}"</p>
                            {% endif %}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endfor %}
            
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

            {% if returns_rows %}
            <h2>Time-Weighted Returns</h2>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: separate; border-spacing: 0;">
                <tr>
                    <td width="55%" valign="top">
                        <table width="100%" style="border-collapse:collapse; background-color:#f8fafc; border:1px solid #e5e7eb; border-radius:6px;">
                            <tr style="text-align:left; color:#6b7280; font-size:13px;">
                                <th style="padding:8px 10px; border-bottom:2px solid #e5e7eb;">Account</th>
                                <th style="padding:8px 10px; border-bottom:2px solid #e5e7eb; text-align:right;">YTD</th>
                                <th style="padding:8px 10px; border-bottom:2px solid #e5e7eb; text-align:right;">12 Mo</th>
                            </tr>
                            {% for r in returns_rows %}
                            <tr>
                                <td style="padding:8px 10px; border-bottom:1px solid #eef2f6;{% if r.name == 'Total' %} font-weight:bold;{% endif %}">{{ r.name }}</td>
                                <td style="padding:8px 10px; border-bottom:1px solid #eef2f6; text-align:right; font-weight:bold; color:{{ r.ytd_color }};">{{ '%+.2f'|format(r.ytd) }}%</td>
                                <td style="padding:8px 10px; border-bottom:1px solid #eef2f6; text-align:right; font-weight:bold; color:{{ r.twelve_color }};">{{ '%+.2f'|format(r.twelve) }}%</td>
                            </tr>
                            {% endfor %}
                        </table>
                        <p style="font-size:11px; color:#9ca3af; margin:8px 0 0 0;">Time-weighted return (securities only); neutralizes deposits, withdrawals, and trades. Updated {{ returns_updated }}.</p>
                    </td>
                    <td width="45%"></td>
                </tr>
            </table>
            {% endif %}

            <div class="footer">
                Generated autonomously by the AI Board of Directors.<br>
                Data provided by Financial Modeling Prep and ETrade Fidelity Logs.
            </div>
            
            {% if qa_summary_text %}
            <div class="qa-box">
                <strong style="color:#4b5563;">Automated QA Audit</strong>
                <span style="color:#9ca3af;">&mdash; see the QA Audit Dashboard for details on any &#10060;.</span><br><br>
                {{ qa_summary_text }}
            </div>
            {% endif %}
        </div>
    </body>
    </html>
    """

    unicorn_trades = [u for u in unicorn_trades if u['verdict'].upper() != 'PASS']
    unicorn_trades_grouped = {}
    for u in unicorn_trades:
        v = u['verdict'].upper()
        if v not in unicorn_trades_grouped:
            unicorn_trades_grouped[v] = []
        unicorn_trades_grouped[v].append(u['symbol'])

    all_positions = chairman_data.get('portfolio_positions', []) + chairman_data.get('watchlist_positions', [])
    
    if advanced_data is None: advanced_data = {}
    grouped_actions = {cat: [] for cat in ['STRONG BUY', 'BUY', 'HOLD', 'TRIM', 'SELL', 'STRONG SELL']}
    for pos in all_positions:
        verdict = pos.get('final_verdict', 'Pass').upper()
        if verdict in grouped_actions:
            pos['image'] = advanced_data.get(pos['symbol'], {}).get('image', '')
            grouped_actions[verdict].append(pos)
            
    for cat in grouped_actions:
        grouped_actions[cat].sort(key=lambda x: x.get('aggregate_conviction_score', 0), reverse=True)

    alpha_pick = chairman_data.get('alpha_pick', {})
    if alpha_pick and 'symbol' in alpha_pick:
        alpha_pick['image'] = advanced_data.get(alpha_pick['symbol'], {}).get('image', '')
        
    events = chairman_data.get('upcoming_events', [])
    red_team_case = red_team_data.get('bear_case_narrative', '')
    chairman_remarks = chairman_data.get('chairman_closing_remarks', '')
    
    hedge_action = chairman_data.get('capital_allocation_narrative', '') if 'hedge' in chairman_data.get('capital_allocation_narrative', '').lower() else ''

    cagr_match = re.search(r"CAGR of ([\d\.]+ percent)", mandate)
    proj_match = re.search(r"projected balance at age 65 is (\$[\d\.,]+)", mandate)
    cagr_text = cagr_match.group(1) if cagr_match else "N/A"
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
        unicorn_trades_grouped=unicorn_trades_grouped,
        grouped_actions=grouped_actions,
        alpha_pick=alpha_pick,
        events=events,
        pie_chart_url=pie_chart_url,
        account_pie_url=account_pie_url,
        returns_rows=returns_rows,
        returns_updated=returns_updated,
        bar_chart_url=bar_chart_url,
        line_chart_url=line_chart_url,
        red_team_case=red_team_case,
        hedge_action=hedge_action,
        chairman_remarks=chairman_remarks,
        qa_summary_text=qa_summary_text
    )

    return rendered_html

def generate_qa_dashboard_html(reports, timestamp):
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
                Invest AI Boardroom
            </div>
        </div>
    </body>
    </html>
    """
    
    template = Template(html_template)
    return template.render(reports=reports, timestamp=timestamp)