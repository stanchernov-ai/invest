import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from src.core.board_roster import resolve_panelist_key
from src.output import briefing_enrichment, reporting


FIXTURE_DEBATE = os.path.join(".cache", "state", "debate.json")


class BriefingEnrichmentTests(unittest.TestCase):
    def test_narratives_separate_from_strategic_context(self):
        if not os.path.exists(FIXTURE_DEBATE):
            self.skipTest("cached debate.json not available")
        with open(FIXTURE_DEBATE, encoding="utf-8") as f:
            debate = json.load(f)
        nvda = next(p for p in debate["chairman_data"]["portfolio_positions"] if p["symbol"] == "NVDA")
        enriched = briefing_enrichment.enrich_position_narratives(
            nvda,
            debate["raw_verdicts"],
            sanitized_synthesis=reporting._sanitize_briefing_text(nvda["synthesis"]),
        )
        champion_quote = enriched["narrative"]["champion_quote"]
        self.assertGreater(len(champion_quote), 40)
        self.assertNotEqual(champion_quote, enriched.get("strategic_context", ""))

    def test_enrich_asml_keeps_override_on_position(self):
        if not os.path.exists(FIXTURE_DEBATE):
            self.skipTest("cached debate.json not available")
        with open(FIXTURE_DEBATE, encoding="utf-8") as f:
            debate = json.load(f)
        asml = next(p for p in debate["chairman_data"]["portfolio_positions"] if p["symbol"] == "ASML")
        sanitized = reporting._sanitize_briefing_text(asml["synthesis"])
        enriched = briefing_enrichment.enrich_position_narratives(
            asml, debate["raw_verdicts"], sanitized_synthesis=sanitized,
        )
        if "[SYSTEM OVERRIDE" in asml["synthesis"]:
            self.assertIn("liquidation limit", (enriched.get("override_context") or "").lower())
        champion = enriched["narrative"]["champion"]
        champion_key = resolve_panelist_key(champion) or champion
        supporter_keys = {
            resolve_panelist_key(name) or name
            for name in (asml.get("supporting_members") or [])
        }
        self.assertIn(champion_key, supporter_keys)

    def test_action_plan_html_shows_three_layers(self):
        if not os.path.exists(FIXTURE_DEBATE):
            self.skipTest("cached debate.json not available")
        with open(FIXTURE_DEBATE, encoding="utf-8") as f:
            debate = json.load(f)
        portfolio_symbols = {
            p["symbol"] for p in debate["chairman_data"].get("portfolio_positions") or []
        }
        chairman = briefing_enrichment.enrich_chairman_for_briefing_sync(
            debate["chairman_data"],
            debate["raw_verdicts"],
            portfolio_symbols=portfolio_symbols,
            sanitize_fn=reporting._sanitize_briefing_text,
        )
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data=chairman,
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": "x" * 100},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            raw_verdicts=None,
        )
        action = html[html.find("The Action Plan"):]
        self.assertIn("Strategic Context:", action)
        self.assertIn("The Champion (", action)
        self.assertIn("The Dissent (None):", action)
        self.assertNotIn("supported the committee's recommendation", html.lower())

    def test_flash_strategic_context_applied(self):
        if not os.path.exists(FIXTURE_DEBATE):
            self.skipTest("cached debate.json not available")
        with open(FIXTURE_DEBATE, encoding="utf-8") as f:
            debate = json.load(f)
        portfolio_symbols = {
            p["symbol"] for p in debate["chairman_data"].get("portfolio_positions") or []
        }
        mock_response = AsyncMock()
        mock_response.text = json.dumps({
            "items": [
                {
                    "symbol": "NVDA",
                    "strategic_context": (
                        "Unanimous conviction on NVDA: the growth camp won the room despite tape concerns."
                    ),
                }
            ]
        })

        async def _run():
            with patch("src.output.briefing_enrichment.client", True), patch(
                "src.output.briefing_enrichment.call_gemini_async",
                new_callable=AsyncMock,
                return_value=mock_response,
            ):
                return await briefing_enrichment.enrich_chairman_for_briefing(
                    debate["chairman_data"],
                    debate["raw_verdicts"],
                    portfolio_symbols=portfolio_symbols,
                    sanitize_fn=reporting._sanitize_briefing_text,
                )

        import asyncio
        chairman = asyncio.run(_run())
        nvda = next(p for p in chairman["portfolio_positions"] if p["symbol"] == "NVDA")
        self.assertIn("growth camp won the room", nvda["strategic_context"])
        self.assertNotEqual(nvda["strategic_context"], nvda["narrative"]["champion_quote"])


if __name__ == "__main__":
    unittest.main()
