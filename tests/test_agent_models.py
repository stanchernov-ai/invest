import unittest

from src.core.agents import FAST_MODEL, HEAVY_MODEL, agent_config
from src.core.board_roster import PANELIST_KEYS


class AgentModelTierTests(unittest.TestCase):
    def test_red_teamer_uses_flash(self):
        self.assertEqual(agent_config["board_members"]["red_teamer"]["model"], FAST_MODEL)
        self.assertNotEqual(agent_config["board_members"]["red_teamer"]["model"], HEAVY_MODEL)

    def test_panelists_and_chairman_still_use_pro(self):
        for key in (*PANELIST_KEYS, "chairman"):
            self.assertEqual(agent_config["board_members"][key]["model"], HEAVY_MODEL)


if __name__ == "__main__":
    unittest.main()
