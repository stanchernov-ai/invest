import re
import unittest

from src.core.board_roster import PANELIST_AVATAR_URLS, PANELIST_ROLES
from src.output.reporting import build_unicorn_protocol_items, generate_html_briefing
from src.qa.visual_audit import audit_briefing_html

CHAIRMAN = {
    "portfolio_positions": [{
        "symbol": "GOOGL",
        "final_verdict": "Hold",
        "synthesis": "Unanimous hold on quality compounder.",
        "narrative": {
            "champion": PANELIST_ROLES["franklin"],
            "champion_quote": "Moat intact.",
            "dissenter": "None",
            "dissenter_quote": "N/A",
        },
    }, {
        "symbol": "NVDA",
        "final_verdict": "Buy",
        "synthesis": "Add on AI strength.",
        "narrative": {
            "champion": PANELIST_ROLES["tesla"],
            "champion_quote": "Platform moat widening.",
            "dissenter": PANELIST_ROLES["franklin"],
            "dissenter_quote": "Rich multiples.",
        },
    }],
    "watchlist_positions": [],
    "alpha_pick": {
        "symbol": "META",
        "champion_quote": "Cheap vs peers.",
        "image": "https://example.com/meta.png",
    },
    "upcoming_events": [],
}

RED_TEAM = {
    "bear_case_narrative": "Alpha risk from macro.",
    "unicorn_rebuttals": [{"symbol": "GOOGL", "rebuttal": "Antitrust overhang could compress multiples."}],
}

COS = {
    "state_of_the_union_quotes": [{
        "board_member": f"{PANELIST_ROLES['franklin']} (⭐⭐⭐ Bullish)",
        "quote": "Quality compounders remain attractive.",
        "avatar_url": PANELIST_AVATAR_URLS["franklin"],
    }],
    "boardroom_brawl": "The board debated.\n\nRound two heated up.\n\nChairman decided.",
}

_EMAIL_UNSAFE = re.compile(r"(display\s*:\s*flex|flex-direction|display\s*:\s*grid|object-fit)", re.I)


class TestUnicornProtocol(unittest.TestCase):
    def test_enriches_chairman_and_red_team(self):
        items, symbols = build_unicorn_protocol_items(
            [{"symbol": "GOOGL", "verdict": "Hold"}],
            CHAIRMAN,
            {"GOOGL": {"image": "https://example.com/googl.png"}},
            RED_TEAM,
        )
        self.assertEqual(symbols, {"GOOGL"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["synthesis"], "Unanimous hold on quality compounder.")
        self.assertIn("Antitrust", items[0]["red_team_rebuttal"])

    def test_excludes_pass_verdicts(self):
        items, symbols = build_unicorn_protocol_items(
            [{"symbol": "XYZ", "verdict": "Pass"}],
            CHAIRMAN,
        )
        self.assertEqual(items, [])
        self.assertEqual(symbols, set())

    def test_briefing_html_is_email_safe(self):
        html = generate_html_briefing(
            100000, 5.0, 3.0,
            "CAGR of 15.00 percent projected balance at age 65 is $2,000,000",
            CHAIRMAN, COS, "",
            [{"symbol": "GOOGL", "verdict": "Hold"}],
            [("GOOGL", {"Total": 50000})],
            red_team_data=RED_TEAM,
            advanced_data={
                "GOOGL": {"image": "https://example.com/googl.png"},
                "NVDA": {"image": "https://example.com/nvda.png"},
                "META": {"image": "https://example.com/meta.png"},
            },
        )
        self.assertIsNone(_EMAIL_UNSAFE.search(html))
        html_findings = audit_briefing_html(html)
        critical = [f for f in html_findings if f.get("severity") == "CRITICAL"]
        self.assertEqual(critical, [], msg=str(critical))


if __name__ == "__main__":
    unittest.main()
