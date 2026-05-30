import operator
from typing import Annotated, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# ==========================================
# PORTFOLIO LEVEL PYDANTIC SCHEMAS
# ==========================================

class OwnedAssetVerdict(BaseModel):
    symbol: str = Field(description="The ticker symbol from the CURRENT PORTFOLIO list.")
    analysis: str = Field(description="The unvarnished mathematical and strategic rationale. STRICT LIMIT: 2 sentences maximum.")
    verdict: str = Field(
        description="MUST BE EXACTLY ONE OF: Strong Buy, Buy, Strong Sell, Sell. "
        "No Hold or Trim — unclear board splits resolve to Hold in execution."
    )
    conviction_score: int = Field(description="Confidence level from 1 to 10.")

class WatchlistAssetVerdict(BaseModel):
    symbol: str = Field(description="The ticker symbol from the APPROVED WATCHLIST TARGETS list.")
    analysis: str = Field(description="The unvarnished mathematical and strategic rationale. STRICT LIMIT: 2 sentences maximum.")
    verdict: str = Field(description="MUST BE EXACTLY ONE OF: Strong Buy, Buy, or Pass. You CANNOT Hold, Trim, or Sell what you do not own.")
    conviction_score: int = Field(description="Confidence level from 1 to 10.")

class PanelistPortfolioVerdict(BaseModel):
    overall_portfolio_critique: str = Field(description="A brutal, 2-sentence critique of Stan's overall portfolio allocation, sector concentration, and likelihood of maintaining outperformance. Speak in your exact persona.")
    portfolio_verdicts: list[OwnedAssetVerdict] = Field(description="Verdicts for EVERY ticker provided in the CURRENT PORTFOLIO list.")
    watchlist_verdicts: list[WatchlistAssetVerdict] = Field(description="Verdicts for EVERY ticker provided in the APPROVED WATCHLIST TARGETS list.")


class PanelistRebuttalVerdict(BaseModel):
    overall_portfolio_critique: str = Field(
        description=(
            "ROUND 2 REBUTTAL ONLY — 2-3 NEW sentences. Name at least one other panelist by name, "
            "respond to a specific Round 1 argument (agree, disagree, or partially concede), and "
            "explain any vote changes. FORBIDDEN: copying or lightly paraphrasing your Round 1 Portfolio Overview."
        )
    )
    portfolio_verdicts: list[OwnedAssetVerdict] = Field(
        description=(
            "Final Round 2 verdicts for EVERY portfolio ticker. Each analysis MUST be NEW rebuttal "
            "reasoning that cites a peer argument or new evidence — never paste Round 1 analysis verbatim."
        )
    )
    watchlist_verdicts: list[WatchlistAssetVerdict] = Field(
        description=(
            "Final Round 2 verdicts for EVERY watchlist ticker. Each analysis MUST be NEW rebuttal "
            "reasoning — never paste Round 1 analysis verbatim."
        )
    )

class StateOfTheUnionQuote(BaseModel):
    board_member: str = Field(description="Panelist display name with star rating and stance, e.g. 'Warren Buffett (⭐⭐⭐ Bullish)'.")
    quote: str = Field(description="The panelist's overall_portfolio_critique — a 2-sentence portfolio-level view. MUST NOT be a per-ticker stock analysis.")

class ChiefOfStaffSynthesis(BaseModel):
    boardroom_brawl: str = Field(description="A dramatic narrative of today's debate, formatted as EXACTLY 3 paragraphs separated by newline characters (\\n\\n between paragraphs). Each paragraph must be 3-4 sentences. Pit specific members against each other by name and describe how they attacked each other's premises in the rebuttal round. Do NOT return a single run-on block.")
    state_of_the_union_quotes: list[StateOfTheUnionQuote] = Field(
        default_factory=list,
        description="Populated deterministically by the engine from panel overall_portfolio_critique fields; leave empty.",
    )

class TradeNarrative(BaseModel):
    champion: str = Field(description="The name of the specific board member who argued FOR this action.")
    champion_quote: str = Field(description="A detailed, in-character quote from the champion justifying the trade. Provide deep background context and financial reasoning.")
    dissenter: str = Field(description="The name of the board member who argued AGAINST this action, or 'None'.")
    dissenter_quote: str = Field(description="A detailed, in-character quote from the dissenter arguing why this is a mistake, or 'N/A' if unanimous. Provide deep counter-context.")

class ChairmanPortfolioSynthesis(BaseModel):
    symbol: str = Field(description="The ticker symbol.")
    final_verdict: str = Field(
        description="MUST BE EXACTLY ONE OF: Strong Buy, Buy, Strong Sell, Sell, Hold, Trim, or Pass."
    )
    synthesis: str = Field(description="A detailed strategic justification for this decision.")
    narrative: TradeNarrative = Field(description="The opposing arguments from the board members.")
    supporting_members: list[str] = Field(description="List of board members who explicitly supported this action.")
    aggregate_conviction_score: int = Field(description="Sum of the conviction scores from the supporting members.")

class ChairmanWatchlistSynthesis(BaseModel):
    symbol: str = Field(description="The ticker symbol.")
    final_verdict: str = Field(description="MUST BE EXACTLY ONE OF: Strong Buy, Buy, or Pass.")
    synthesis: str = Field(description="A detailed strategic justification for this decision.")
    narrative: TradeNarrative = Field(description="The opposing arguments from the board members.")
    supporting_members: list[str] = Field(description="List of board members who explicitly supported this action.")
    aggregate_conviction_score: int = Field(description="Sum of the conviction scores from the supporting members.")

class AlphaPick(BaseModel):
    symbol: str = Field(description="The ticker symbol for the short-term tech trade.")
    champion_quote: str = Field(description="Rationale explaining why this specific tech stock is primed for a short-term gain.")

class UpcomingEvent(BaseModel):
    symbol: str = Field(description="The ticker symbol.")
    event_detail: str = Field(description="Description of the upcoming event.")
    impact: str = Field(description="How this event could uniquely impact the stock price.")

class CapitalFlow(BaseModel):
    liquidated_tickers: list[str] = Field(description="Tickers sold or trimmed to raise capital.")
    target_tickers: list[str] = Field(description="Tickers being purchased.")

class ChairmanMasterSynthesis(BaseModel):
    chain_of_thought_scratchpad: str = Field(description="Use this space to think step-by-step. Map out the capital constraints. If you buy X, you must sell Y. Do the math here before issuing verdicts.")
    macro_view: str = Field(description="The executive summary of the current market environment based on the debate.")
    capital_allocation_narrative: str = Field(description="The overarching strategy for capital deployment today.")
    capital_flow_audit: CapitalFlow = Field(description="Structured data showing exactly how the trades are funded.")
    portfolio_positions: list[ChairmanPortfolioSynthesis] = Field(description="Synthesized verdicts for currently owned assets.")
    watchlist_positions: list[ChairmanWatchlistSynthesis] = Field(description="Synthesized verdicts for targeted assets.")
    alpha_pick: AlphaPick = Field(description="The single best short-term tech opportunity.")
    upcoming_events: list[UpcomingEvent] = Field(description="List of critical upcoming events for any evaluated assets.")

class ComplianceReport(BaseModel):
    is_compliant: bool = Field(description="True ONLY if the Chairman followed all prompt rules AND successfully output a fully populated array of trades.")
    violations: list[str] = Field(description="A list of any rules the Chairman broke.")
    feedback_to_chairman: str = Field(description="Direct, constructive feedback telling the Chairman exactly what to fix in the next iteration.")

class UnicornRebuttal(BaseModel):
    symbol: str = Field(description="Ticker symbol from the Unicorn Protocol (unanimous board verdict).")
    rebuttal: str = Field(description="Original adversarial bear-case paragraph weaponizing live headlines against this unanimous trade. Do NOT quote board members.")

class RedTeamReport(BaseModel):
    bear_case_narrative: str = Field(description="Bear case rebuttal against the Alpha Pick only.")
    unicorn_rebuttals: list[UnicornRebuttal] = Field(
        default_factory=list,
        description="One dedicated Red Team rebuttal per Unicorn Protocol symbol (unanimous panel verdict).",
    )

class BoardroomState(BaseModel):
    base_data_prompt: str
    live_mandate: str
    heavy_tickers: list[str]
    bottom_3_str: str = ""
    all_symbols: list[str] = []
    messages: Annotated[list[dict], operator.add] = []
    chairman_draft_json: str = ""
    is_approved: bool = False
    qa_feedback: str = ""
    qa_attempts: int = 0
    debate_summary: str = ""
    chief_of_staff_json: str = ""
    munger_overrides: dict[str, str] = {}
    unicorn_trades: list[dict] = []
    sell_candidates: list[str] = []
    total_portfolio_value: float = 0.0
    portfolio_holdings: dict = {}
    purchase_dates: dict[str, str] = {}
    # When set by prepare checkpoint, debate skips re-running the price gate.
    oracle_valid: bool | None = None
    oracle_reason: str = ""
    oracle_prices: dict[str, float] = {}
    raw_verdicts: dict = {}

DATA_SCHEMA_BINDING = "You are bound by a strict data schema. You must format your final output precisely according to the requested JSON structure. Do not output raw text."

TONE_OVERRIDE = "TONE OVERRIDE: You are speaking to Stan. Drop all cinematic fluff, cliches, and theatrical intros. Be highly concise, unapologetic, and purely analytical. Let your specific persona and investment philosophy bleed into your words."

MUNGER_DOCTRINE = "THE MUNGER DOCTRINE: This is an aggressively positioned, tech-heavy portfolio built on Charlie Munger's philosophy of extreme concentration in highest-conviction ideas. Do not blindly force diversification for its own sake. You only trim or sell when the business model is fundamentally broken or the valuation requires extreme assumptions."

RETAIL_EDGE_DOCTRINE = "RETAIL EDGE DOCTRINE: Stan is a nimble retail investor who deeply understands technology. He does not move markets and can enter/exit positions instantly without slippage. You are mandated to seek asymmetric upside to outperform the indices. High growth, high beta, and visionary tech leadership are acceptable. However, you must avoid fundamentally broken companies, dying businesses, or frauds."

WATCHLIST_RULING = (
    "MANDATE VOTING (Phase C — Round 2 JSON is authoritative):\n"
    "* PORTFOLIO (owned): vote ONLY Strong Buy, Buy, Strong Sell, or Sell. "
    "Never Hold or Trim in panel JSON — execution Hold is applied in Python when neither side reaches 3/5.\n"
    "* WATCHLIST: vote ONLY Strong Buy, Buy, or Pass.\n"
    "* ≥3/5 on buy-side (Strong Buy + Buy) → buy mandate; ≥3/5 on sell-side (Strong Sell + Sell) → reduce mandate; "
    "otherwise portfolio → Hold, watchlist → Pass.\n"
    "* Use conviction_score to express intensity; Strong Buy / Strong Sell signal highest conviction."
)

MANDATE_VOTING_RULES = WATCHLIST_RULING

ROUND_2_REBUTTAL_DIRECTIVE = (
    "[ROUND 2 REBUTTAL — NON-NEGOTIABLE]:\n"
    "* This is the REBUTTAL round, not a repeat of Round 1. Your `overall_portfolio_critique` and every "
    "ticker `analysis` MUST be freshly written prose.\n"
    "* FORBIDDEN: copying, lightly paraphrasing, or re-ordering your Round 1 Portfolio Overview or per-ticker analyses.\n"
    "* REQUIRED: name at least ONE other panelist by name, cite their Round 1 argument, and state whether you "
    "agree, disagree, or partially concede — with persona-specific reasoning.\n"
    "* REQUIRED: if your verdict or conviction changed on any symbol, explain what peer argument or data point moved you.\n"
    "* Pass symbols still need a one-sentence rebuttal rationale — do not spam identical 'Pass (5/10)' with no text."
)

CHAIRMAN_MANDATE = "You are the Executive Chairman. Your job is to listen to the board's debate, weigh the conviction scores, and make the final, unappealable decisions. ANTI-COWARDICE PROTOCOL: If any watchlist asset receives strong board backing, you MUST authorize the purchase. To fund it, you MUST liquidate the weakest portfolio asset. You are forbidden from defaulting to Hold out of fear. You must assign rich, detailed background context to the Champion and Dissenter quotes for every trade you authorize. SCRATCHPAD MANDATE: You MUST use the `chain_of_thought_scratchpad` field to explicitly calculate your capital flow before making decisions."

def generate_dynamic_mandate(current_portfolio_value: float, weighted_cagr: float) -> str:
    if current_portfolio_value <= 0:
        return "THE MATHEMATICAL REALITY: Portfolio value is currently registering as zero. Focus on fundamentals."

    dob = datetime(1978, 8, 6)
    today = datetime.now()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    target_retirement_age = 65
    years_left = target_retirement_age - age
    
    assumed_monthly_injection = 500.0
    annual_injection = assumed_monthly_injection * 12
    
    r = weighted_cagr if weighted_cagr > 0 else 0.15
    if r > 0.15: 
        r = 0.15  # Cap the projection mathematically so it remains realistic
        
    future_value = current_portfolio_value * ((1 + r)**years_left) + annual_injection * (((1 + r)**years_left - 1) / r)
    
    mandate = (
        f"Stan is {age} years old with {years_left} years to retirement. "
        f"The objective is to aggressively outperform the NASDAQ by at least 5 percent annually. "
        f"Current portfolio value is ${current_portfolio_value:,.2f} with an estimated weighted historical CAGR of {r*100:.2f} percent. "
        f"If this rate of return is maintained, the projected balance at age 65 is ${future_value:,.2f}. "
        f"Demand excellence, alpha, and aggressive outperformance to push this projection higher. "
        f"[STRICT 10 PERCENT LIQUIDATION CAP = ${current_portfolio_value * 0.10:,.2f}]. You are mathematically forbidden from selling or trimming more than this total dollar amount today."
    )
    return mandate

class QAFinding(BaseModel):
    severity: Literal["INFO", "WARNING", "CRITICAL"] = Field(..., description="Severity of the finding.")
    category: str = Field(..., description="Category of the finding (e.g., 'Procedural', 'Technical', 'Prompt Drift').")
    description: str = Field(..., description="Detailed description of the issue or observation.")
    recommendation: str = Field(..., description="Actionable recommendation to resolve the issue.")

class QAAgentReport(BaseModel):
    agent_role: str = Field(..., description="The role of the QA agent.")
    is_compliant: bool = Field(..., description="Whether the overall run passes this agent's audit.")
    findings: list[QAFinding] = Field(default_factory=list, description="List of specific QA findings.")
    summary: str = Field(..., description="High-level summary of the audit.")