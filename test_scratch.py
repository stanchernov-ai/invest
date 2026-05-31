from src.qa_pipeline import parse_board_matrix
from src.core.board_roster import PANELIST_ROLES

def run():
    agent = PANELIST_ROLES["hypatia"]
    messages = [
        {"content": f"**[ROUND 2 REBUTTAL] {agent}**:\n* **META**: Accumulate Candidate (8/10)."}
    ]
    print(parse_board_matrix(messages, ["META"]))

if __name__ == '__main__':
    run()