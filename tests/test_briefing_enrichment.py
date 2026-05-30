import json
import os
import unittest

from src.output import briefing_enrichment, reporting


FIXTURE_DEBATE = os.path.join(".cache", "state", "debate.json")
FIXTURE_PREPARE = os.path.join(".cache", "state", "prepare.json")


class BriefingEnrichmentTests(unittest.TestCase):
    def test_enrich_nvda_uses_round2_analysis(self):
        if not os.path.exists(FIXTURE_DEBATE):
            self.skipTest("cached debate.json not available")
        debate = json.load(open(FIXTURE_DEBATE, encoding="utf-8"))
        chairman = debate["chairman_data"]
        raw_verdicts = debate["raw_verdicts"]
        nvda = next(p for p in chairman["portfolio_positions"] if p["symbol"] == "NVDA")
        enriched = briefing_enrichment.enrich_position_from_round2(
            nvda,
            raw_verdicts,
            sanitized_synthesis=reporting._sanitize_briefing_text(nvda["synthesis"]),
        )
        self.assertNotIn("consensus mandate", enriched["synthesis"].lower())
        self.assertGreater(len(enriched["synthesis"]), 40)
        self.assertIn("Peter Lynch", enriched["narrative"]["champion"])

    def test_enrich_asml_keeps_override_and_sell_champion(self):
        if not os.path.exists(FIXTURE_DEBATE):
            self.skipTest("cached debate.json not available")
        debate = json.load(open(FIXTURE_DEBATE, encoding="utf-8"))
        chairman = debate["chairman_data"]
        raw_verdicts = debate["raw_verdicts"]
        asml = next(p for p in chairman["portfolio_positions"] if p["symbol"] == "ASML")
        sanitized = reporting._sanitize_briefing_text(asml["synthesis"])
        enriched = briefing_enrichment.enrich_position_from_round2(
            asml, raw_verdicts, sanitized_synthesis=sanitized,
        )
        self.assertIn("liquidation limit", enriched["synthesis"].lower())
        self.assertGreater(len(enriched["synthesis"]), 60)
        champion = enriched["narrative"]["champion"]
        self.assertIn(
            champion,
            asml.get("supporting_members") or [],
            msg=f"champion {champion} should be a mandate supporter",
        )

    def test_briefing_html_includes_round2_prose(self):
        if not os.path.exists(FIXTURE_DEBATE):
            self.skipTest("cached debate.json not available")
        debate = json.load(open(FIXTURE_DEBATE, encoding="utf-8"))
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data=debate["chairman_data"],
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": "x" * 100},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            raw_verdicts=debate["raw_verdicts"],
        )
        self.assertNotIn("supported the committee's recommendation", html.lower())
        self.assertNotIn("consensus mandate from today's panel vote", html)
        self.assertIn("Strategic Context:", html)


if __name__ == "__main__":
    unittest.main()
