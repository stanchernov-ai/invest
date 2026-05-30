import json
import logging
import asyncio
from pydantic import BaseModel
from google.genai import types

from src.core.schemas import (
    BoardroomState, PanelistPortfolioVerdict, PanelistRebuttalVerdict, ChiefOfStaffSynthesis, 
    ChairmanMasterSynthesis, ComplianceReport, RedTeamReport, DATA_SCHEMA_BINDING, 
    TONE_OVERRIDE, MUNGER_DOCTRINE, CHAIRMAN_MANDATE, RETAIL_EDGE_DOCTRINE, 
    WATCHLIST_RULING, ROUND_2_REBUTTAL_DIRECTIVE,
)
from src.core.rebuttal import build_round2_user_prompt
from src.core.data_oracle import validate_price_feed
from src.core.guardrails import apply_chairman_guardrails
from src.core.state_of_union import build_state_of_union_quotes
from src.core.boardroom_brawl import (
    build_clerk_debate_digest,
    fallback_boardroom_brawl,
    is_boardroom_brawl_complete,
)
from src.core.vote_engine import (
    apply_conviction_scores,
    build_chairman_allocation,
    build_vote_summaries,
    can_determine_allocation,
    detect_sell_candidates,
    detect_unicorn_trades,
    enforce_alpha_pick_from_executed_buys,
    format_vote_digest,
)
from src.core.agents import call_gemini_async, agent_config, FAST_MODEL, FLASH_TOKEN_LIMIT
from src.core.board_roster import CONCENTRATION_AUDIT_KEYS, PANELIST_KEYS

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
        self.round1_portfolio_critiques: dict[str, str] = {}
        self.oracle_valid = False
        self.oracle_reason = "Default security stance. Awaiting Oracle clearance."
        self.red_team_json = "{}"
        self.compliance_attempts: list[dict] = []
        self.chairman_bypassed: bool = False
        self.allocation_source: str = "llm"
        self.compliance_source: str = "python+llm"
        self.munger_skipped: bool = False

    def _portfolio_symbols(self) -> set[str]:
        return set((self.state.portfolio_holdings or {}).keys())

    def _watchlist_symbols(self) -> set[str]:
        universe = set(self.state.all_symbols or []) | self._portfolio_symbols()
        return universe - self._portfolio_symbols()

    def _vote_summaries(self):
        return build_vote_summaries(
            self.raw_verdicts,
            self.state.all_symbols,
            portfolio_symbols=self._portfolio_symbols(),
        )

    def _finalize_chairman(self, chairman: dict | None) -> dict | None:
        if not chairman:
            return None
        chairman = apply_conviction_scores(chairman, self.raw_verdicts)
        chairman = apply_chairman_guardrails(
            chairman,
            total_portfolio_value=self.state.total_portfolio_value,
            portfolio_holdings=self.state.portfolio_holdings,
            purchase_dates=self.state.purchase_dates,
            raw_verdicts=self.raw_verdicts,
            all_symbols=self.state.all_symbols,
        )
        return enforce_alpha_pick_from_executed_buys(
            chairman,
            self.raw_verdicts,
            self.state.all_symbols,
            portfolio_symbols=self._portfolio_symbols(),
        )

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

        summaries = self._vote_summaries()
        if self.state.heavy_tickers and not can_determine_allocation(summaries):
            await self.execute_munger_audit()
        elif self.state.heavy_tickers:
            self.munger_skipped = True
            logger.info(
                "Munger audit skipped — vote_engine will bypass chairman (concentration pass unused)."
            )

        # Single pass — no chairman/compliance retry on audit failure (see .cursorrules).
        await self.execute_chairman_arbitration()
        await self.execute_compliance_audit()

        if self.state.is_approved:
            await self.execute_red_team()
                 
        return self.state

    async def _run_agent(
        self,
        agent_key: str,
        context_msg: str,
        schema: type[BaseModel] = None,
        extra_instructions: list[str] | None = None,
        include_base_data: bool = True,
    ) -> dict:
        member_info = agent_config["board_members"][agent_key]
        
        instructions = [
            member_info['system_instruction'],
            CONCENTRATION_EXEMPTION,
            DATA_SCHEMA_BINDING,
            self.state.live_mandate,
            MUNGER_DOCTRINE,
            RETAIL_EDGE_DOCTRINE,
            WATCHLIST_RULING,
            TONE_OVERRIDE,
        ]
        if extra_instructions:
            instructions.extend(extra_instructions)
        system_prompt = "\n\n".join(instructions)
        prompt_text = (
            f"{self.state.base_data_prompt}\n\n{context_msg}"
            if include_base_data
            else context_msg
        )
        
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
        agents = list(PANELIST_KEYS)
        tasks = [self._run_agent(a, "Provide initial asset analysis.", schema=PanelistPortfolioVerdict) for a in agents]
        results = await asyncio.gather(*tasks)
        
        for agent_key, res in zip(agents, results):
            role_name = agent_config["board_members"][agent_key]["role"]
            if res and res.get("overall_portfolio_critique"):
                self.round1_portfolio_critiques[agent_key] = (
                    res["overall_portfolio_critique"].strip()
                )
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
        agents = list(PANELIST_KEYS)
        tasks = [
            self._run_agent(
                a,
                build_round2_user_prompt(a, self.state.messages),
                schema=PanelistRebuttalVerdict,
                extra_instructions=[ROUND_2_REBUTTAL_DIRECTIVE],
            )
            for a in agents
        ]
        results = await asyncio.gather(*tasks)
        
        for agent_key, res in zip(agents, results):
            self.raw_verdicts[agent_key] = res
            role_name = agent_config["board_members"][agent_key]["role"]
            msg = f"**[ROUND 2 REBUTTAL] {role_name}**:\n"
            if res:
                if res.get("overall_portfolio_critique"):
                    msg += f"* **Rebuttal Summary**: {res['overall_portfolio_critique']}\n"
                for v in res.get('portfolio_verdicts', []):
                    v_sym = v.get("symbol", "Unknown")
                    v_erd = v.get("verdict", "Hold")
                    v_sc = v.get("conviction_score", 5)
                    v_ans = (v.get("analysis") or "").strip()
                    if v_ans:
                        msg += f"* **{v_sym}**: {v_erd} ({v_sc}/10). {v_ans}\n"
                    else:
                        msg += f"* **{v_sym}**: {v_erd} ({v_sc}/10).\n"
                for v in res.get('watchlist_verdicts', []):
                    v_sym = v.get("symbol", "Unknown")
                    v_erd = v.get("verdict", "Pass")
                    v_sc = v.get("conviction_score", 5)
                    v_ans = (v.get("analysis") or "").strip()
                    if v_ans:
                        msg += f"* **{v_sym}**: {v_erd} ({v_sc}/10). {v_ans}\n"
                    else:
                        msg += f"* **{v_sym}**: {v_erd} ({v_sc}/10).\n"
            self.state.messages.append({"role": "assistant", "content": msg})

        self.state.raw_verdicts = dict(self.raw_verdicts)

    async def execute_synthesis(self) -> None:
        summaries = self._vote_summaries()
        self.state.unicorn_trades = detect_unicorn_trades(summaries)
        self.state.sell_candidates = detect_sell_candidates(summaries)
        
        debate_digest = build_clerk_debate_digest(self.state.messages)
        vote_digest = format_vote_digest(summaries, portfolio_symbols=self._portfolio_symbols())
        clerk_prompt = (
            f"{vote_digest}\n\n"
            "Synthesize the board debate into boardroom_brawl JSON — exactly 3 paragraphs "
            "separated by blank lines. Name panelists and describe Round 2 attacks.\n\n"
            f"{debate_digest}"
        )
        cos_res = await self._run_agent(
            "clerk", clerk_prompt, schema=ChiefOfStaffSynthesis, include_base_data=False,
        )
        brawl = (cos_res or {}).get("boardroom_brawl", "")
        if cos_res and not is_boardroom_brawl_complete(brawl):
            logger.warning("Clerk boardroom_brawl incomplete (%d chars) — retrying focused synthesis.", len(brawl))
            retry_prompt = (
                "Your previous boardroom_brawl was truncated or incomplete. "
                "Return ONLY valid JSON with a complete boardroom_brawl field: exactly 3 full "
                "paragraphs (blank line between each), 3-4 sentences per paragraph, ending with "
                "proper punctuation. Name Benjamin Franklin, Charles Darwin, Sun Tzu, Nikola Tesla, "
                "and Pythagoras where relevant.\n\n"
                f"{debate_digest}"
            )
            retry_res = await self._run_agent(
                "clerk", retry_prompt, schema=ChiefOfStaffSynthesis, include_base_data=False,
            )
            if retry_res and is_boardroom_brawl_complete(retry_res.get("boardroom_brawl", "")):
                cos_res = retry_res
                brawl = retry_res["boardroom_brawl"]
            else:
                cos_res = cos_res or {}
                cos_res["boardroom_brawl"] = fallback_boardroom_brawl(
                    self.state.messages, self.raw_verdicts,
                )
                logger.warning("Clerk retry still incomplete — using deterministic boardroom_brawl fallback.")
        if cos_res:
            cos_res["state_of_the_union_quotes"] = build_state_of_union_quotes(
                self.raw_verdicts,
                round1_critiques=self.round1_portfolio_critiques,
            )
        self.state.chief_of_staff_json = json.dumps(cos_res) if cos_res else "{}"

    async def execute_munger_audit(self) -> None:
        roster = list(CONCENTRATION_AUDIT_KEYS)
        prompt = f"Concentration warning for: {self.state.heavy_tickers}. Validate structural health."
        tasks = [self._run_agent(a, prompt, schema=PanelistPortfolioVerdict) for a in roster]
        results = await asyncio.gather(*tasks)
        for agent_key, res in zip(roster, results):
            if res:
                self.state.munger_overrides[agent_key] = json.dumps(res)

    async def execute_chairman_arbitration(self) -> None:
        summaries = self._vote_summaries()
        vote_digest = format_vote_digest(summaries, portfolio_symbols=self._portfolio_symbols())
        portfolio_symbols = self._portfolio_symbols()
        watchlist_symbols = self._watchlist_symbols()

        if can_determine_allocation(summaries):
            logger.info(
                "Chairman Pro bypass — vote_engine allocation (board majority resolved in Python)."
            )
            self.chairman_bypassed = True
            self.allocation_source = "vote_engine"
            res = build_chairman_allocation(
                self.raw_verdicts,
                self.state.all_symbols,
                portfolio_symbols=portfolio_symbols,
                watchlist_symbols=watchlist_symbols,
            )
            res = self._finalize_chairman(res)
            self.state.chairman_draft_json = json.dumps(res) if res else "{}"
            return

        self.chairman_bypassed = False
        self.allocation_source = "llm"
        history = "\n\n".join([m["content"] for m in self.state.messages])
        munger_warning = ""
        if self.state.munger_overrides:
            munger_warning = "\n\n[CRITICAL MUNGER AUDIT CONCENTRATION WARNINGS]:\n"
            for agent, data in self.state.munger_overrides.items():
                munger_warning += f"--- {agent.upper()} ---\n{data}\n"
        corrections = ""
        prompt = (
            f"{vote_digest}\n\n"
            f"Review board arguments. Apply the pre-computed vote digest — do NOT re-count votes. "
            f"Resolve contradictions and write narratives.{munger_warning}{corrections}\n\n{history}"
        )
        res = await self._run_agent("chairman", prompt, schema=ChairmanMasterSynthesis)

        if res:
            res = self._finalize_chairman(res)

        self.state.chairman_draft_json = json.dumps(res) if res else "{}"

    async def execute_compliance_audit(self) -> None:
        if not self.state.chairman_draft_json or self.state.chairman_draft_json == "{}":
            self.state.is_approved = False
            self.state.qa_feedback = "Chairman produced empty execution arrays."
            return

        from src.core.compliance_audit import (
            audit_chairman_compliance,
            format_compliance_digest,
            format_compliance_failure_summary,
            format_debate_for_compliance,
            merge_compliance_reports,
        )

        try:
            chairman = json.loads(self.state.chairman_draft_json)
        except json.JSONDecodeError:
            self.state.is_approved = False
            self.state.qa_feedback = "Chairman output is not valid JSON."
            return

        from src.core.chairman_alignment import apply_board_and_cap_coherence

        portfolio_symbols = set((self.state.portfolio_holdings or {}).keys())
        universe = set(self.state.all_symbols or []) | portfolio_symbols
        apply_board_and_cap_coherence(
            chairman,
            self.raw_verdicts,
            portfolio_symbols=portfolio_symbols,
            watchlist_symbols=universe - portfolio_symbols,
        )
        chairman = apply_conviction_scores(chairman, self.raw_verdicts)
        self.state.chairman_draft_json = json.dumps(chairman)

        deterministic_violations = audit_chairman_compliance(
            chairman,
            self.raw_verdicts,
            all_symbols=self.state.all_symbols,
            portfolio_symbols=portfolio_symbols,
        )

        if self.allocation_source == "vote_engine":
            logger.info(
                "Compliance LLM skipped — vote_engine allocation; Python gate only."
            )
            merged = merge_compliance_reports(
                deterministic_violations, None, chairman=chairman,
            )
            self.compliance_source = "python_only"
        else:
            debate_text = format_debate_for_compliance(self.state.messages)
            digest = format_compliance_digest(deterministic_violations)

            prompt = (
                f"{digest}\n\n"
                f"{format_vote_digest(self._vote_summaries(), portfolio_symbols=portfolio_symbols)}\n\n"
                f"Python already verified max buys, hedge, majority alignment, originator rule, and alpha pick — "
                f"do NOT contradict a PASS on those items.\n\n"
                f"RAW BOARD DEBATE LOG (Round 2 votes are ground truth for funding/deathmatch checks):\n"
                f"{debate_text}\n\n"
                f"CHAIRMAN JSON OUTPUT (audit deathmatch / capital flow only):\n"
                f"{self.state.chairman_draft_json}"
            )
            res = await self._run_agent("compliance", prompt, schema=ComplianceReport)
            merged = merge_compliance_reports(deterministic_violations, res, chairman=chairman)
            self.compliance_source = "python+llm"

        self.compliance_attempts.append({
            "attempt": len(self.compliance_attempts) + 1,
            "is_compliant": merged.get("is_compliant", False),
            "violations": merged.get("violations") or [],
            "feedback_to_chairman": merged.get("feedback_to_chairman", ""),
        })
        self.state.is_approved = merged.get("is_compliant", False)
        self.state.qa_feedback = merged.get("feedback_to_chairman", "Compliance rejection triggered.")
        if not self.state.is_approved:
            summary = format_compliance_failure_summary(
                violations=merged.get("violations") or [],
                feedback=merged.get("feedback_to_chairman", ""),
                attempts=len(self.compliance_attempts),
            )
            logger.error("[COMPLIANCE] Attempt %s rejected:\n%s", len(self.compliance_attempts), summary)

    def build_compliance_failure_detail(self) -> dict:
        """Structured failure payload for debate phase logging and persistence."""
        from src.core.compliance_audit import format_compliance_failure_summary

        last = self.compliance_attempts[-1] if self.compliance_attempts else {}
        violations = last.get("violations") or []
        feedback = last.get("feedback_to_chairman") or self.state.qa_feedback or ""
        chairman_empty = (
            not self.state.chairman_draft_json
            or self.state.chairman_draft_json == "{}"
        )
        summary = format_compliance_failure_summary(
            violations=violations,
            feedback=feedback,
            attempts=len(self.compliance_attempts),
            chairman_empty=chairman_empty,
        )
        return {
            "gate": "compliance",
            "attempts": self.compliance_attempts,
            "violations": violations,
            "feedback_to_chairman": feedback,
            "summary": summary,
            "chairman_draft_present": not chairman_empty,
            "requires_expert_review": True,
            "expert_review_domains": ["prompt_engineering", "data_quality"],
            "allocation_source": self.allocation_source,
            "chairman_bypassed": self.chairman_bypassed,
            "compliance_source": self.compliance_source,
        }

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
        yield {"synthesize": {
            "chief_of_staff_json": final_state.chief_of_staff_json,
            "unicorn_trades": final_state.unicorn_trades,
            "raw_verdicts": final_state.raw_verdicts,
        }}
        
        chair_data = json.loads(final_state.chairman_draft_json) if final_state.is_approved else {}
        red_data = json.loads(orchestrator.red_team_json) if final_state.is_approved else {}
        compliance_payload = {
            "is_approved": final_state.is_approved,
            "chairman_data": chair_data,
            "red_team_data": red_data,
            "chairman_bypassed": orchestrator.chairman_bypassed,
            "allocation_source": orchestrator.allocation_source,
            "compliance_source": orchestrator.compliance_source,
            "munger_skipped": orchestrator.munger_skipped,
        }
        if not final_state.is_approved:
            compliance_payload["failure_detail"] = orchestrator.build_compliance_failure_detail()
        yield {"compliance": compliance_payload}

app = AppWrapper()