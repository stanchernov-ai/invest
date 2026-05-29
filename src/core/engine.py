import json
import logging
import asyncio
from pydantic import BaseModel
from google.genai import types

from src.core.schemas import (
    BoardroomState, PanelistPortfolioVerdict, ChiefOfStaffSynthesis, 
    ChairmanMasterSynthesis, ComplianceReport, RedTeamReport, DATA_SCHEMA_BINDING, 
    TONE_OVERRIDE, MUNGER_DOCTRINE, CHAIRMAN_MANDATE, RETAIL_EDGE_DOCTRINE, 
    WATCHLIST_RULING
)
from src.core.data_oracle import validate_price_feed
from src.core.guardrails import apply_chairman_guardrails
from src.core.state_of_union import build_state_of_union_quotes
from src.core.agents import call_gemini_async, agent_config, FAST_MODEL, FLASH_TOKEN_LIMIT

logger = logging.getLogger(__name__)

CONCENTRATION_EXEMPTION = (
    "[CRITICAL CONCENTRATION EXEMPTION]: This portfolio is intentionally tech heavy. "
    "You are strictly FORBIDDEN from voting to Sell or Trim purely to achieve sector diversification. "
    "Evaluate assets on individual mathematical metrics and edge."
)

class StateMachineOrchestrator:
    def __init__(self, state: BoardroomState):
        self.state = state
        self.raw_verdicts = {}
        self.max_qa_retries = 3
        self.oracle_valid = False
        self.oracle_reason = "Default security stance. Awaiting Oracle clearance."
        self.red_team_json = "{}"

    async def _ensure_oracle_cleared(self) -> None:
        """Use prepare-phase oracle when present; otherwise run the LLM gate (legacy)."""
        if self.state.oracle_valid is True:
            self.oracle_valid = True
            self.oracle_reason = self.state.oracle_reason or "Validated in prepare phase."
            logger.info("Skipping debate Data Oracle — prepare checkpoint already validated.")
            return
        if self.state.oracle_valid is False:
            self.oracle_valid = False
            self.oracle_reason = self.state.oracle_reason or "Oracle rejected in prepare phase."
            return
        await self.execute_data_oracle()

    async def execute_pipeline(self) -> BoardroomState:
        logger.info("Starting orchestrated execution matrix pipeline.")

        await self._ensure_oracle_cleared()
        if not self.oracle_valid:
            self.state.is_approved = False
            self.state.qa_feedback = f"CRITICAL DATA ORACLE VIOLATION: {self.oracle_reason}"
            return self.state

        await self.execute_parallel_board()
        await self.execute_rebuttal_round()
        await self.execute_synthesis()
        
        if self.state.heavy_tickers:
            await self.execute_munger_audit()
             
        attempt = 0
        while attempt < self.max_qa_retries and not self.state.is_approved:
            await self.execute_chairman_arbitration()
            await self.execute_compliance_audit()
            attempt += 1

        if self.state.is_approved:
            await self.execute_red_team()
                 
        return self.state

    async def _run_agent(self, agent_key: str, context_msg: str, schema: type[BaseModel] = None) -> dict:
        member_info = agent_config["board_members"][agent_key]
        
        instructions = [
            member_info['system_instruction'],
            CONCENTRATION_EXEMPTION,
            DATA_SCHEMA_BINDING,
            self.state.live_mandate,
            MUNGER_DOCTRINE,
            RETAIL_EDGE_DOCTRINE,
            WATCHLIST_RULING,
            TONE_OVERRIDE
        ]
        system_prompt = "\n\n".join(instructions)
        prompt_text = f"{self.state.base_data_prompt}\n\n{context_msg}"
        
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])]
        config_params = {"system_instruction": system_prompt, "temperature": 0.15}
        
        if member_info["model"] == FAST_MODEL: 
            config_params["max_output_tokens"] = FLASH_TOKEN_LIMIT

        # Elevated native reasoning for decision-critical agents (internal thinking
        # tokens only; does not enter the response text / downstream context).
        thinking_budget = member_info.get("thinking_budget")
        if thinking_budget is not None:
            config_params["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

        if schema:
            config_params["response_mime_type"] = "application/json"
            config_params["response_schema"] = schema
            
        response = await call_gemini_async(
            member_info["model"], 
            contents, 
            types.GenerateContentConfig(**config_params), 
            agent_name=agent_key, 
            schema=schema
        )
        
        if schema:
            text = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        return {"raw_text": response.text.strip()}

    async def execute_data_oracle(self) -> None:
        """Legacy path: deterministic check when prepare checkpoint is unavailable."""
        result = validate_price_feed(self.state.oracle_prices or {})
        self.oracle_valid = result["is_valid"]
        self.oracle_reason = result["reason"]

    async def execute_parallel_board(self) -> None:
        agents = ["buffett", "lynch", "livermore", "huang", "simons"]
        tasks = [self._run_agent(a, "Provide initial asset analysis.", schema=PanelistPortfolioVerdict) for a in agents]
        results = await asyncio.gather(*tasks)
        
        for agent_key, res in zip(agents, results):
            role_name = agent_config["board_members"][agent_key]["role"]
            msg = f"**[ROUND 1] {role_name}**:\n"
            if res and res.get("overall_portfolio_critique"):
                msg += f"* **Portfolio Overview**: {res['overall_portfolio_critique']}\n"
            if res and res.get('portfolio_verdicts'):
                for v in res['portfolio_verdicts']:
                    v_sym = v.get("symbol", "Unknown")
                    v_erd = v.get("verdict", "Hold")
                    v_ans = v.get("analysis", "")
                    msg += f"* **{v_sym}**: {v_erd}. Analysis: {v_ans}\n"
            self.state.messages.append({"role": "assistant", "content": msg})

    async def execute_rebuttal_round(self) -> None:
        agents = ["buffett", "lynch", "livermore", "huang", "simons"]
        history = "\n\n".join([m["content"] for m in self.state.messages])
        tasks = [self._run_agent(a, f"Review opinions and issue final structured verdicts:\n\n{history}", schema=PanelistPortfolioVerdict) for a in agents]
        results = await asyncio.gather(*tasks)
        
        for agent_key, res in zip(agents, results):
            self.raw_verdicts[agent_key] = res
            role_name = agent_config["board_members"][agent_key]["role"]
            msg = f"**[ROUND 2 REBUTTAL] {role_name}**:\n"
            if res:
                if res.get("overall_portfolio_critique"):
                    msg += f"* **Portfolio Overview**: {res['overall_portfolio_critique']}\n"
                for v in res.get('portfolio_verdicts', []):
                    v_sym = v.get("symbol", "Unknown")
                    v_erd = v.get("verdict", "Hold")
                    v_sc = v.get("conviction_score", 5)
                    msg += f"* **{v_sym}**: {v_erd} ({v_sc}/10).\n"
                for v in res.get('watchlist_verdicts', []):
                    v_sym = v.get("symbol", "Unknown")
                    v_erd = v.get("verdict", "Pass")
                    v_sc = v.get("conviction_score", 5)
                    msg += f"* **{v_sym}**: {v_erd} ({v_sc}/10).\n"
            self.state.messages.append({"role": "assistant", "content": msg})

    async def execute_synthesis(self) -> None:
        matrix = {t: [] for t in self.state.all_symbols}
        sell_candidates = set()
        
        for agent, data in self.raw_verdicts.items():
            if not data: continue
            for v in data.get("portfolio_verdicts", []) + data.get("watchlist_verdicts", []):
                sym = v.get("symbol")
                verdict = v.get("verdict", "").upper()
                if sym in matrix:
                    matrix[sym].append(verdict)
                    if "SELL" in verdict or "TRIM" in verdict:
                        sell_candidates.add(sym)

        self.state.unicorn_trades = [{"symbol": s, "verdict": v[0].title()} for s, v in matrix.items() if len(v) == 5 and len(set(v)) == 1]
        self.state.sell_candidates = list(sell_candidates)
        
        history = "\n\n".join([m["content"] for m in self.state.messages])
        cos_res = await self._run_agent("clerk", f"Synthesize structural friction points into JSON:\n\n{history}", schema=ChiefOfStaffSynthesis)
        if cos_res:
            cos_res["state_of_the_union_quotes"] = build_state_of_union_quotes(self.raw_verdicts)
        self.state.chief_of_staff_json = json.dumps(cos_res) if cos_res else "{}"

    async def execute_munger_audit(self) -> None:
        roster = ["buffett", "huang", "lynch"]
        prompt = f"Concentration warning for: {self.state.heavy_tickers}. Validate structural health."
        tasks = [self._run_agent(a, prompt, schema=PanelistPortfolioVerdict) for a in roster]
        results = await asyncio.gather(*tasks)
        for agent_key, res in zip(roster, results):
            if res:
                self.state.munger_overrides[agent_key] = json.dumps(res)

    async def execute_chairman_arbitration(self) -> None:
        history = "\n\n".join([m["content"] for m in self.state.messages])
        munger_warning = ""
        if self.state.munger_overrides:
            munger_warning = "\n\n[CRITICAL MUNGER AUDIT CONCENTRATION WARNINGS]:\n"
            for agent, data in self.state.munger_overrides.items():
                munger_warning += f"--- {agent.upper()} ---\n{data}\n"
        corrections = f"\n\n[QA AMENDMENT REQUIRED]:\n{self.state.qa_feedback}" if self.state.qa_feedback else ""
        prompt = f"Review board arguments. Apply voting logic rules. Resolve contradictions.{munger_warning}{corrections}\n\n{history}"
        res = await self._run_agent("chairman", prompt, schema=ChairmanMasterSynthesis)

        if res:
            res = apply_chairman_guardrails(
                res,
                total_portfolio_value=self.state.total_portfolio_value,
                portfolio_holdings=self.state.portfolio_holdings,
                purchase_dates=self.state.purchase_dates,
            )

        self.state.chairman_draft_json = json.dumps(res) if res else "{}"

    async def execute_compliance_audit(self) -> None:
        if not self.state.chairman_draft_json or self.state.chairman_draft_json == "{}":
            self.state.is_approved = False
            self.state.qa_feedback = "Chairman produced empty execution arrays."
            return

        prompt = f"Audit implementation contract for ledger discrepancies:\n\n{self.state.chairman_draft_json}"
        res = await self._run_agent("compliance", prompt, schema=ComplianceReport)
        if res:
            self.state.is_approved = res.get("is_compliant", False)
            self.state.qa_feedback = res.get("feedback_to_chairman", "Compliance rejection triggered.")

    async def execute_red_team(self) -> None:
        unicorns = json.dumps(self.state.unicorn_trades or [])
        headlines = self.state.base_data_prompt or ""
        if "=== LIVE MARKET HEADLINES ===" in headlines:
            headlines = headlines[headlines.find("=== LIVE MARKET HEADLINES ==="):]
        headlines = headlines[:6000]
        prompt = (
            f"Construct adversarial bear-case narratives opposing the Chairman's plan.\n\n"
            f"LIVE MARKET HEADLINES (weaponize these):\n{headlines}\n\n"
            f"UNICORN PROTOCOL (unanimous panel verdict — you MUST output one `unicorn_rebuttals` "
            f"entry per symbol below):\n{unicorns}\n\n"
            f"Also write `bear_case_narrative` targeting the Alpha Pick only.\n\n"
            f"CHAIRMAN FINAL PLAN:\n{self.state.chairman_draft_json}"
        )
        res = await self._run_agent("red_teamer", prompt, schema=RedTeamReport)
        self.red_team_json = json.dumps(res) if res else "{}"

class AppWrapper:
    async def astream(self, initial_state: dict, config: dict = None):
        state = BoardroomState(**initial_state)
        orchestrator = StateMachineOrchestrator(state)
        final_state = await orchestrator.execute_pipeline()
        
        yield {"oracle": {"is_valid": orchestrator.oracle_valid, "reason": orchestrator.oracle_reason}}
        if not orchestrator.oracle_valid: return
            
        yield {"full_board": {"messages": final_state.messages}}
        yield {"synthesize": {"chief_of_staff_json": final_state.chief_of_staff_json, "unicorn_trades": final_state.unicorn_trades}}
        
        chair_data = json.loads(final_state.chairman_draft_json) if final_state.is_approved else {}
        red_data = json.loads(orchestrator.red_team_json) if final_state.is_approved else {}
        yield {"compliance": {"is_approved": final_state.is_approved, "chairman_data": chair_data, "red_team_data": red_data}}

app = AppWrapper()