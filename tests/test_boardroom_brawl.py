import unittest

from src.core.board_roster import PANELIST_ROLES, shorten_panelist_references
from src.core.boardroom_brawl import (
    build_clerk_debate_digest,
    build_debate_dialogue_turns,
    build_debate_display_blocks,
    debate_turn_heading,
    fallback_boardroom_brawl,
    is_boardroom_brawl_complete,
    split_debate_paragraphs,
)


def _valid_brawl() -> str:
    return (
        "Benjamin hypatia opened Round 1 by dismissing momentum names as speculation without moats, "
        "while Sun Tzu countered that the tape already priced in those fears. "
        "Charles davinci bridged the gap by arguing growth at a reasonable price still mattered.\n\n"
        "Round 2 turned personal when Nikola Tesla attacked aurelius for treating NVDA as a spreadsheet row, "
        "and aurelius fired back that Tesla ignored correlation risk across the AI cluster. "
        "hypatia and davinci traded barbs over whether concentration in mega-cap tech was courage or complacency.\n\n"
        "The session ended without consensus: value, momentum, and quant camps each retained conviction, "
        "forcing the Chairman to impose structure on a board that agreed on quality but not on timing."
    )


class BoardroomBrawlCompleteTests(unittest.TestCase):
    def test_complete_brawl_passes(self):
        self.assertTrue(is_boardroom_brawl_complete(_valid_brawl()))

    def test_truncated_mid_sentence_fails(self):
        truncated = "hypatia initiated by dismissing the entire portfolio as"
        self.assertFalse(is_boardroom_brawl_complete(truncated))

    def test_short_blob_fails_even_with_punctuation(self):
        self.assertFalse(is_boardroom_brawl_complete("Too short to publish."))


class ClerkDebateDigestTests(unittest.TestCase):
    def test_digest_keeps_summaries_only(self):
        hypatia = PANELIST_ROLES["hypatia"]
        suntzu = PANELIST_ROLES["suntzu"]
        messages = [
            {
                "content": (
                    f"**[ROUND 1] {hypatia}**:\n"
                    "* **Portfolio Overview**: Moats matter.\n"
                    "* **NVDA**: Buy. Analysis: Great business.\n"
                ),
            },
            {
                "content": (
                    f"**[ROUND 2 REBUTTAL] {suntzu}**:\n"
                    "* **Rebuttal Summary**: hypatia ignores the tape.\n"
                    "* **NVDA**: Strong Buy (9/10). Momentum confirms.\n"
                ),
            },
        ]
        digest = build_clerk_debate_digest(messages)
        self.assertIn("Portfolio Overview", digest)
        self.assertIn("Rebuttal Summary", digest)
        self.assertNotIn("Strong Buy (9/10)", digest)


class SplitDebateParagraphTests(unittest.TestCase):
    def test_splits_on_blank_lines(self):
        parts = split_debate_paragraphs(_valid_brawl())
        self.assertEqual(len(parts), 3)

    def test_build_debate_display_blocks(self):
        blocks = build_debate_display_blocks(_valid_brawl())
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["kind"], "body")

    def test_build_debate_dialogue_turns_from_messages(self):
        hypatia = PANELIST_ROLES["hypatia"]
        suntzu = PANELIST_ROLES["suntzu"]
        messages = [
            {
                "content": (
                    f"**[ROUND 1] {hypatia}**:\n"
                    "* **Portfolio Overview**: Moats matter more than momentum.\n"
                    "* **NVDA**: Sell.\n"
                ),
            },
            {
                "content": (
                    f"**[ROUND 2 REBUTTAL] {suntzu}**:\n"
                    "* **Rebuttal Summary**: hypatia ignores the tape.\n"
                    "* **NVDA**: Strong Buy.\n"
                ),
            },
        ]
        turns = build_debate_dialogue_turns(messages)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["speaker"], hypatia)
        self.assertEqual(turns[0]["turn_heading"], "Portfolio Overview")
        self.assertEqual(turns[1]["turn_heading"], "Rebuttal")
        self.assertNotIn("round_label", turns[0])
        self.assertEqual(turns[0]["align"], "left")
        self.assertEqual(turns[1]["align"], "right")
        self.assertIn("Moats matter", turns[0]["text"])

        blocks = build_debate_display_blocks("", raw_board_messages=messages)
        self.assertEqual(blocks[0]["kind"], "turn")
        self.assertEqual(len(blocks), 2)


class DebateTurnHeadingTests(unittest.TestCase):
    def test_maps_round_tags_to_phase_names(self):
        self.assertEqual(debate_turn_heading("ROUND 1"), "Portfolio Overview")
        self.assertEqual(debate_turn_heading("ROUND 2 REBUTTAL"), "Rebuttal")
        self.assertEqual(debate_turn_heading(""), "")


class ShortPeerNameTests(unittest.TestCase):
    def test_shorten_panelist_references(self):
        text = (
            "Leonardo da Vinci describes NVIDIA as a masterwork, yet Marcus Aurelius "
            "and Hypatia of Alexandria disagree."
        )
        shortened = shorten_panelist_references(text)
        self.assertIn("Leonardo describes", shortened)
        self.assertNotIn("da Vinci", shortened)
        self.assertIn("Marcus", shortened)
        self.assertNotIn("Marcus Aurelius", shortened)
        self.assertIn("Hypatia", shortened)
        self.assertNotIn("Hypatia of Alexandria", shortened)

    def test_debate_turns_keep_speaker_header_full_name(self):
        hypatia = PANELIST_ROLES["hypatia"]
        davinci = PANELIST_ROLES["davinci"]
        messages = [
            {
                "content": (
                    f"**[ROUND 2 REBUTTAL] {hypatia}**:\n"
                    f"* **Rebuttal Summary**: {davinci} describes NVIDIA as a masterwork.\n"
                ),
            },
        ]
        turns = build_debate_dialogue_turns(messages)
        self.assertEqual(turns[0]["speaker"], hypatia)
        self.assertIn("Leonardo describes", turns[0]["text"])
        self.assertNotIn("da Vinci", turns[0]["text"])


class FallbackBrawlTests(unittest.TestCase):
    def test_fallback_produces_three_paragraphs(self):
        hypatia = PANELIST_ROLES["hypatia"]
        suntzu = PANELIST_ROLES["suntzu"]
        messages = [
            {
                "content": (
                    f"**[ROUND 1] {hypatia}**:\n"
                    "* **Portfolio Overview**: Quality over hype.\n"
                ),
            },
            {
                "content": (
                    f"**[ROUND 2 REBUTTAL] {suntzu}**:\n"
                    "* **Rebuttal Summary**: The tape disagrees with hypatia.\n"
                ),
            },
        ]
        text = fallback_boardroom_brawl(messages, {})
        self.assertTrue(is_boardroom_brawl_complete(text))
        self.assertEqual(len(split_debate_paragraphs(text)), 3)


if __name__ == "__main__":
    unittest.main()
