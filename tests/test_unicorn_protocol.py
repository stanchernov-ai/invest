import re
import unittest

from src.core.board_roster import CRUCIBLE_AVATAR_URL, CRUCIBLE_DISPLAY_NAME, PANELIST_AVATAR_URLS, PANELIST_ROLES
from src.output import briefing_style
from src.output.reporting import (
    build_unicorn_protocol_items,
    generate_html_briefing,
    show_unicorn_protocol_section,
)
from src.qa.visual_audit import audit_briefing_html

CHAIRMAN = {
    "portfolio_positions": [{
        "symbol": "GOOGL",
        "final_verdict": "Hold",
        "synthesis": "Unanimous hold on quality compounder.",
        "narrative": {
            "champion": PANELIST_ROLES["hypatia"],
            "champion_quote": "Moat intact.",
            "dissenter": "None",
            "dissenter_quote": "N/A",
        },
    }, {
        "symbol": "NVDA",
        "final_verdict": "Accumulate Candidate",
        "synthesis": "Add on AI strength.",
        "narrative": {
            "champion": PANELIST_ROLES["tesla"],
            "champion_quote": "Platform moat widening.",
            "dissenter": PANELIST_ROLES["hypatia"],
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
    "unicorn_rebuttals": [{"symbol": "NVDA", "rebuttal": "Valuation leaves little margin of safety."}],
}

COS = {
    "state_of_the_union_quotes": [{
        "board_member": f"{PANELIST_ROLES['hypatia']} (⭐⭐⭐ Bullish)",
        "quote": "Quality compounders remain attractive.",
        "avatar_url": PANELIST_AVATAR_URLS["hypatia"],
    }],
    "boardroom_brawl": "The board debated.\n\nRound two heated up.\n\nChairman decided.",
}

_EMAIL_UNSAFE = re.compile(r"(display\s*:\s*flex|flex-direction|display\s*:\s*grid|object-fit)", re.I)


class TestUnicornProtocol(unittest.TestCase):
    def test_enriches_chairman_and_red_team(self):
        items, symbols = build_unicorn_protocol_items(
            [{"symbol": "NVDA", "verdict": "Accumulate Candidate"}],
            CHAIRMAN,
            {"NVDA": {"image": "https://example.com/nvda.png"}},
            RED_TEAM,
        )
        self.assertEqual(symbols, {"NVDA"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["board_synthesis"], "Add on AI strength.")
        self.assertIn("margin of safety", items[0]["crucible_text"])
        self.assertEqual(items[0]["champion_quote"], "Platform moat widening.")

    def test_excludes_unanimous_hold(self):
        items, symbols = build_unicorn_protocol_items(
            [{"symbol": "GOOGL", "verdict": "Hold"}],
            CHAIRMAN,
            {"GOOGL": {"image": "https://example.com/googl.png"}},
            RED_TEAM,
        )
        self.assertEqual(items, [])
        self.assertEqual(symbols, set())
        self.assertFalse(show_unicorn_protocol_section(items))

    def test_excludes_pass_verdicts(self):
        items, symbols = build_unicorn_protocol_items(
            [{"symbol": "XYZ", "verdict": "Pass"}],
            CHAIRMAN,
        )
        self.assertEqual(items, [])
        self.assertEqual(symbols, set())

    def test_briefing_hides_unicorn_section_when_empty(self):
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
        self.assertNotIn("Unicorn Protocol", html)

    def test_briefing_html_is_email_safe(self):
        html = generate_html_briefing(
            100000, 5.0, 3.0,
            "CAGR of 15.00 percent projected balance at age 65 is $2,000,000",
            CHAIRMAN, COS, "",
            [{"symbol": "NVDA", "verdict": "Accumulate Candidate"}],
            [("GOOGL", {"Total": 50000})],
            red_team_data=RED_TEAM,
            advanced_data={
                "GOOGL": {"image": "https://example.com/googl.png"},
                "NVDA": {"image": "https://example.com/nvda.png"},
                "META": {"image": "https://example.com/meta.png"},
            },
        )
        self.assertIn("Unicorn Protocol", html)
        self.assertIn("The Board", html)
        self.assertIn(CRUCIBLE_DISPLAY_NAME, html)
        self.assertIn(CRUCIBLE_AVATAR_URL, html)
        self.assertIn(briefing_style.CRUCIBLE_BG, html)
        self.assertIn(briefing_style.CRUCIBLE_BORDER, html)
        self.assertNotIn("Bear Case Rebuttal", html)
        self.assertIsNone(_EMAIL_UNSAFE.search(html))
        html_findings = audit_briefing_html(html)
        critical = [f for f in html_findings if f.get("severity") == "CRITICAL"]
        self.assertEqual(critical, [], msg=str(critical))


if __name__ == "__main__":
    unittest.main()
