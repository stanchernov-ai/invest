"""User-configurable portfolio policy, replacing hardcoded doctrines.

This module maps a user's profile (sliders, primary persona, horizon) into
the specific text blocks and numeric guardrails that control the pipeline.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

class AssetClassGuidance(BaseModel):
    equity_target_pct: int = Field(default=100)
    bond_etf_symbols: list[str] = Field(default_factory=lambda: ["TLT", "BND"])
    hedge_symbols: frozenset[str] = Field(default_factory=lambda: frozenset({"TLT", "VXX"}))


class PortfolioPolicy(BaseModel):
    """The translated rules for a single user's portfolio."""
    
    # 1. Inputs from profile
    date_of_birth: str = "1978-08-06"
    target_retirement_age: int = 65
    monthly_contribution_usd: float = 500.0
    benchmark: str = "NASDAQ"
    benchmark_alpha_target_pct: float = 5.0
    
    # Core tuning dials
    primary_panelist: str = "tesla"  # Which panelist's philosophy leads the overall instruction
    risk_slider: int = 75            # 0 (Preservation) to 100 (Aggressive)
    conviction_slider: int = 80      # 0 (Broad Distribution) to 100 (Extreme Concentration)
    
    # 2. Derived guardrails
    liquidation_cap_pct: float = 0.10
    max_daily_buys: int = 3
    asset_guidance: AssetClassGuidance = Field(default_factory=AssetClassGuidance)

    @property
    def age(self) -> int:
        dob = datetime.strptime(self.date_of_birth, "%Y-%m-%d")
        today = datetime.now()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def years_left(self) -> int:
        return max(0, self.target_retirement_age - self.age)

    def generate_dynamic_mandate(self, current_portfolio_value: float, weighted_cagr: float) -> str:
        """Generates the opening mandate text based on age and benchmark."""
        if current_portfolio_value <= 0:
            return "THE MATHEMATICAL REALITY: Portfolio value is currently registering as zero. Focus on fundamentals."
        
        annual_injection = self.monthly_contribution_usd * 12
        r = weighted_cagr if weighted_cagr > 0 else 0.15
        
        # Cap the projection mathematically so it remains realistic
        if r > 0.15: 
            r = 0.15
            
        years = self.years_left
        future_value = current_portfolio_value * ((1 + r)**years) + annual_injection * (((1 + r)**years - 1) / r) if r > 0 else current_portfolio_value + annual_injection * years
        
        return (
            f"The client is {self.age} years old with {years} years to retirement. "
            f"The objective is to outperform the {self.benchmark} by at least {self.benchmark_alpha_target_pct} percent annually. "
            f"Current portfolio value is ${current_portfolio_value:,.2f} with an estimated weighted historical CAGR of {r*100:.2f} percent. "
            f"If this rate of return is maintained, the projected balance at age {self.target_retirement_age} is ${future_value:,.2f}. "
            f"Demand excellence and alpha to push this projection higher. "
            f"[STRICT {self.liquidation_cap_pct*100:.0f} PERCENT LIQUIDATION CAP = ${current_portfolio_value * self.liquidation_cap_pct:,.2f}]. "
            f"You are mathematically forbidden from selling or trimming more than this total dollar amount today."
        )

    def get_doctrine_blocks(self) -> str:
        """Translates the sliders into specific instructional doctrines."""
        blocks = []
        
        # Conviction vs Distribution
        if self.conviction_slider > 70:
            blocks.append(
                "CONVICTION DOCTRINE: This is an aggressively positioned portfolio built on "
                "extreme concentration in highest-conviction ideas. Maintain a small number "
                "of distinct stocks in the portfolio to maximize alpha. Do not blindly force "
                "diversification for its own sake. You only trim or sell when the business "
                "model is fundamentally broken or the valuation requires extreme assumptions."
            )
        elif self.conviction_slider < 30:
            blocks.append(
                "DISTRIBUTION DOCTRINE: This portfolio requires strict risk management and broad "
                "distribution of capital. Maintain a highly diverse portfolio with many different "
                "distinct stocks across various sectors. Avoid extreme concentration in any single "
                "asset. Prioritize preservation of capital and diversified steady returns over "
                "massive individual bets."
            )
        else:
            blocks.append(
                "BALANCED CONVICTION DOCTRINE: Seek a balance between high-conviction alpha generation "
                "and prudent sector diversification. Do not over-concentrate, but let true winners run."
            )

        # Risk vs Preservation
        if self.risk_slider > 70:
            blocks.append(
                "ASYMMETRIC RISK DOCTRINE: The client is nimble and deeply understands technology. "
                "You are mandated to seek asymmetric upside to outperform the indices. High growth, "
                "high beta, and visionary tech leadership are acceptable. However, you must avoid "
                "fundamentally broken companies, dying businesses, or frauds."
            )
        elif self.risk_slider < 30:
            blocks.append(
                "PRESERVATION DOCTRINE: The client's primary objective is wealth preservation and "
                "defensive positioning. You must heavily bias your recommendations toward wide moats, "
                "strong dividend yields, consistent free cash flow, and low-beta assets. Volatile, "
                "high-multiple growth stocks without current earnings are strictly forbidden."
            )
        else:
            blocks.append(
                "MODERATE GROWTH DOCTRINE: The client seeks sustainable growth at a reasonable price. "
                "Focus on profitable, scaling businesses with proven business models."
            )

        return "\n\n".join(blocks)

def resolve_policy(profile_dict: dict | None = None) -> PortfolioPolicy:
    """Instantiate a policy from a raw database dictionary (profile_json)."""
    if not profile_dict:
        return PortfolioPolicy()  # Default Stan settings
    return PortfolioPolicy(**profile_dict)
