import os
import urllib.parse
import json
import re
from jinja2 import Template
import logging

logger = logging.getLogger(__name__)

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
    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    return f"https://quickchart.io/chart?w=600&h=300&c={encoded_config}"

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
    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    return f"https://quickchart.io/chart?w=600&h=300&c={encoded_config}"

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
    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    return f"https://quickchart.io/chart?w=600&h=300&c={encoded_config}"

def build_benchmark_line_chart(history_data):
    if not history_data or len(history_data) < 2:
        return ""

    dates = sorted(history_data.keys())
    # Backfilled history may start with $0 portfolio before holdings existed.
    # Anchor the chart on the first date with a meaningful portfolio value.
    baseline_idx = 0
    for i, d in enumerate(dates):
        row = history_data[d]
        if row.get("portfolio", 0) > 1000 and row.get("spy", 0) > 0:
            baseline_idx = i
            break
    dates = dates[baseline_idx:]
    if len(dates) < 2:
        return ""

    base_port = history_data[dates[0]].get("portfolio", 0)
    base_spy = history_data[dates[0]].get("spy", 0)
    base_qqq = history_data[dates[0]].get("qqq", 0)
    if base_port <= 0 or base_spy <= 0:
        return ""
    has_qqq = base_qqq > 0

    port_data = []
    spy_data = []
    qqq_data = []

    for d in dates:
        p_val = history_data[d].get("portfolio", base_port)
        s_val = history_data[d].get("spy", base_spy)
        port_data.append(round(((p_val - base_port) / base_port) * 100, 2))
        spy_data.append(round(((s_val - base_spy) / base_spy) * 100, 2))
        if has_qqq:
            q_val = history_data[d].get("qqq", base_qqq)
            qqq_data.append(round(((q_val - base_qqq) / base_qqq) * 100, 2))

    datasets = [
        {"label": "Portfolio", "data": port_data, "borderColor": "#2563eb", "fill": False, "tension": 0.1},
        {"label": "S&P 500", "data": spy_data, "borderColor": "#9ca3af", "fill": False, "tension": 0.1},
    ]
    if has_qqq:
        datasets.append({"label": "NASDAQ", "data": qqq_data, "borderColor": "#10b981", "fill": False, "tension": 0.1})

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
    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    return f"https://quickchart.io/chart?w=600&h=300&c={encoded_config}"

def generate_html_briefing(total_val, qqq_trend, portfolio_3m_trend, mandate, chairman_data, cos_data, matrix_md, unicorn_trades, sorted_ledger, red_team_data=None, history_data=None, qa_summary_text="", account_holdings=None, account_returns=None):

    pie_chart_url = build_portfolio_pie_chart(sorted_ledger)
    account_pie_url = build_account_allocation_pie(account_holdings, account_returns)
    returns_rows = build_returns_rows(account_returns)
    returns_updated = (account_returns or {}).get("updated", "")
    bar_chart_url = build_returns_bar_chart(sorted_ledger)
    line_chart_url = build_benchmark_line_chart(history_data)
    
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
            .chart-container { margin: 20px 0; text-align: center; border: 1px solid #e5e7eb; padding: 10px; border-radius: 5px;}
            .chart-img { max-width: 100%; height: auto; }
            .footer { margin-top: 40px; font-size: 0.8em; color: #6b7280; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; }
            .qa-box { margin-top: 40px; font-size: 0.75em; color: #6b7280; border-top: 1px dashed #e5e7eb; padding-top: 15px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SC Invest: Executive Briefing</h1>
            
            <div class="metric-box">
                <strong>Portfolio Value:</strong> {{ total_val }}<br>
                <strong>3M Trend — Portfolio:</strong> {{ portfolio_3m_trend }} &nbsp;|&nbsp; <strong>QQQ:</strong> {{ qqq_trend }}<br>
                <strong>Current CAGR:</strong> {{ cagr_text }} &nbsp;|&nbsp; <strong>Projected Balance (Age 65):</strong> {{ proj_text }}
            </div>

            {% if returns_rows %}
            <h2>Time-Weighted Returns</h2>
            <table style="width:100%; border-collapse:collapse; margin:10px 0;">
                <tr style="text-align:left; color:#6b7280; font-size:13px;">
                    <th style="padding:6px 8px; border-bottom:2px solid #e5e7eb;">Account</th>
                    <th style="padding:6px 8px; border-bottom:2px solid #e5e7eb; text-align:right;">YTD</th>
                    <th style="padding:6px 8px; border-bottom:2px solid #e5e7eb; text-align:right;">12 Mo</th>
                </tr>
                {% for r in returns_rows %}
                <tr>
                    <td style="padding:6px 8px; border-bottom:1px solid #f3f4f6;{% if r.name == 'Total' %} font-weight:bold;{% endif %}">{{ r.name }}</td>
                    <td style="padding:6px 8px; border-bottom:1px solid #f3f4f6; text-align:right; font-weight:bold; color:{{ r.ytd_color }};">{{ '%+.2f'|format(r.ytd) }}%</td>
                    <td style="padding:6px 8px; border-bottom:1px solid #f3f4f6; text-align:right; font-weight:bold; color:{{ r.twelve_color }};">{{ '%+.2f'|format(r.twelve) }}%</td>
                </tr>
                {% endfor %}
            </table>
            <p style="font-size:11px; color:#9ca3af; margin-top:4px;">Time-weighted return (securities only); neutralizes deposits, withdrawals, and trades. Updated {{ returns_updated }}.</p>
            {% endif %}

            {% if line_chart_url %}
            <h2>Performance vs. S&P 500 & NASDAQ</h2>
            <div class="chart-container">
                <img class="chart-img" src="{{ line_chart_url }}" alt="Benchmark Performance Line Chart">
            </div>
            {% endif %}

            {% if pie_chart_url or account_pie_url %}
            <div style="display: flex; flex-wrap: wrap; gap: 20px; margin-top: 30px; align-items: stretch;">
                {% if pie_chart_url %}
                <div style="flex: 1; min-width: 300px;">
                    <h2 style="margin-top: 0; border-bottom: 1px solid #e5e7eb; padding-bottom: 5px;">Unrealized Gains</h2>
                    <div class="chart-container" style="margin-top: 10px;">
                        <img class="chart-img" src="{{ pie_chart_url }}" alt="Unrealized Gains Pie Chart">
                    </div>
                </div>
                {% endif %}

                {% if account_pie_url %}
                <div style="flex: 1; min-width: 300px;">
                    <h2 style="margin-top: 0; border-bottom: 1px solid #e5e7eb; padding-bottom: 5px;">12 M Return</h2>
                    <p style="font-size:12px; color:#6b7280; margin-top:-10px;">Slice size = account weight. Color = 12M return.</p>
                    <div class="chart-container" style="margin-top: 10px;">
                        <img class="chart-img" src="{{ account_pie_url }}" alt="12 M Return Pie Chart">
                    </div>
                </div>
                {% endif %}
            </div>
            {% endif %}

            {% if bar_chart_url %}
            <h2>Personal Return by Asset</h2>
            <div class="chart-container">
                <img class="chart-img" src="{{ bar_chart_url }}" alt="Portfolio Returns Bar Chart">
            </div>
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
                <p style="margin-top: 0;"><strong>{{ alpha_pick.symbol }}</strong>: "{{ alpha_pick.champion_quote }}"</p>
                
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
                            <span class="verdict-pill" style="{{ pill_styles[category] }}">{{ category }} : {{ pos.symbol }}</span>
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

            <div class="footer">
                Generated autonomously by the AI Board of Directors.<br>
                Data provided by Financial Modeling Prep and ETrade Fidelity Logs.
            </div>
            
            {% if qa_summary_text %}
            <div class="qa-box">
                <strong>P.S. Automated QA Auditor Summary:</strong><br>
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
    
    grouped_actions = {cat: [] for cat in ['STRONG BUY', 'BUY', 'HOLD', 'TRIM', 'SELL', 'STRONG SELL']}
    for pos in all_positions:
        verdict = pos.get('final_verdict', 'Pass').upper()
        if verdict in grouped_actions:
            grouped_actions[verdict].append(pos)
            
    for cat in grouped_actions:
        grouped_actions[cat].sort(key=lambda x: x.get('aggregate_conviction_score', 0), reverse=True)

    alpha_pick = chairman_data.get('alpha_pick', {})
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
            <h1>SC Invest: QA Audit Dashboard</h1>
            <p style="color: #6b7280; margin-top: -10px; margin-bottom: 30px;">Generated: {{ timestamp }}</p>
            
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
                SC Invest Boardroom AI
            </div>
        </div>
    </body>
    </html>
    """
    
    template = Template(html_template)
    return template.render(reports=reports, timestamp=timestamp)