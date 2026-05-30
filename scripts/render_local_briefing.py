"""Render executive briefing HTML from cached prepare/debate checkpoints (no QA agents)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.output import reporting

CACHE = ROOT / ".cache" / "state"
DEFAULT_OUT = ROOT / ".cache" / "reports" / "briefing_preview_local.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    prep = json.loads((CACHE / "prepare.json").read_text(encoding="utf-8"))
    debate = json.loads((CACHE / "debate.json").read_text(encoding="utf-8"))

    chart_urls = reporting.build_briefing_charts(
        prep["sorted_ledger"],
        prep["account_holdings"],
        prep["account_returns"],
        prep["history_data"],
    )
    html = reporting.generate_html_briefing(
        total_val=prep["total_portfolio_value"],
        qqq_trend=prep["live_qqq_trend"],
        portfolio_3m_trend=prep["portfolio_3m_trend"],
        mandate=prep["live_mandate"],
        chairman_data=debate["chairman_data"],
        cos_data=debate["cos_data"],
        matrix_md="",
        unicorn_trades=debate["unicorn_trades"],
        sorted_ledger=prep["sorted_ledger"],
        red_team_data=debate["red_team_data"],
        history_data=prep["history_data"],
        qa_summary_text="",
        account_holdings=prep["account_holdings"],
        account_returns=prep["account_returns"],
        advanced_data=prep["advanced_data"],
        chart_urls=chart_urls,
        raw_verdicts=debate.get("raw_verdicts"),
        portfolio_symbols=set(prep.get("portfolio_holdings") or {}),
        raw_board_messages=debate.get("raw_board_messages"),
    )
    investor_html = reporting.inject_qa_summary_into_briefing(html, "")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(investor_html, encoding="utf-8")
    print(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
