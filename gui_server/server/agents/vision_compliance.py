"""
Agent 2: Vision & Strategy Compliance Filter.

Pure compliance checklist, not a signal generator: Agent 0 (the EA) already
decided the trigger fired and which direction, and Agent 1 already computed
the deterministic stop-loss/take-profit/risk-reward numbers. This agent's only
question is "does the active 1-minute chart visually and contextually match
our high-probability reference pattern, or does it look like the fail/trap
pattern?" - a 2-shot comparison against the direction-matched "ideal" template
and the "fail_trap" template, informed by the quantitative trigger metrics.

Fails closed: any parse failure or LLM error becomes a REJECT with confidence 0,
never a silent ACCEPT.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from llm.base import ContentPart, LLMProvider
from storage.template_image_store import TemplateImageStore
from storage.prompt_store import PromptStore

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_NAME = "vision_compliance_default"

IDEAL_SLOT_FOR_DIRECTION = {"BUY": "bullish_ideal", "SELL": "bearish_ideal"}
FAIL_TRAP_SLOT = "fail_trap"

DEFAULT_SYSTEM_PROMPT = """You are an expert quantitative trader and visual compliance filter for AegisVision AI. Your sole job is to evaluate 1-minute 20-MA trend-continuation pullbacks on XAUUSD to filter out low-probability setups and false breakouts.

TASK:
Compare the active live 1-minute chart (IMAGE C) against the annotated Ideal Continuation Setup (IMAGE A) and the annotated Invalid Trap Setup (IMAGE B), if provided. Synthesize the visual chart with the quantitative metrics given to you.

COMPLIANCE CHECKLIST:
1. SLOPE QUALITY: Is the 20 MA line sharply angled (>25 degree visual slope)? REJECT if flat, horizontal, or rounding over.
2. REJECTION STRUCTURE: Did the trigger candle wick into/touch the 20 MA and forcefully close AWAY from it in the direction of the trend? REJECT if it is a tiny doji or weak-bodied candle.
3. HEADROOM / CLEAR SPACE: Is there clear space on the chart between the entry price and the target swing high/low? REJECT if price is immediately slamming into major resistance or an opposing zone.
4. TREND ALIGNMENT: Does the 1m move align with the 5m market structure and 1h macro trend?

The trigger direction and the exact numeric metrics below have already been computed
deterministically - do not recompute or second-guess the arithmetic, only judge whether
the visual setup and these numbers together justify taking the trade.

If a reference image (A and/or B) was not provided (this can happen before the user has
uploaded one), judge purely from the checklist, the metrics, and the active chart - be
conservative (prefer REJECT) when the setup is ambiguous.

OUTPUT INSTRUCTIONS:
Return standard JSON ONLY. Do not include markdown code blocks, conversational intro text, or extra prose.

JSON OUTPUT SCHEMA:
{
  "verdict": "ACCEPT" or "REJECT",
  "confidence_score": 0.00 to 1.00,
  "visual_rejection_reason": "Clear, concise sentence describing why the setup passed or failed visual compliance."
}"""


@dataclass
class ComplianceVerdict:
    verdict: str  # ACCEPT | REJECT
    confidence: float  # normalized to 0-100 internally regardless of the LLM's 0-1 scale
    reasoning: str
    raw_response: str


class VisionComplianceFilter:
    def __init__(
        self,
        llm_provider: LLMProvider,
        template_store: TemplateImageStore,
        prompt_store: PromptStore,
        strategy_name: str = DEFAULT_STRATEGY_NAME,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ):
        self.llm_provider = llm_provider
        self.template_store = template_store
        self.prompt_store = prompt_store
        self.strategy_name = strategy_name
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Seed a version 1 prompt if none exists yet, so PromptStore always has
        # something to return and the GUI's Template Manager tab has a starting
        # point to edit rather than an empty box.
        if self.prompt_store.get_latest(self.strategy_name) is None:
            self.prompt_store.save_prompt(self.strategy_name, DEFAULT_SYSTEM_PROMPT, notes="seeded default")

    def get_active_prompt(self) -> str:
        latest = self.prompt_store.get_latest(self.strategy_name)
        return latest.text if latest else DEFAULT_SYSTEM_PROMPT

    def evaluate(
        self,
        market_summary_text: str,
        live_chart_b64: Optional[str],
        direction: str,
        calculated_slope: Optional[float] = None,
        headroom_pips: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None,
        higher_timeframe_bias: Optional[str] = None,
    ) -> ComplianceVerdict:
        parts = [ContentPart.text_part(self.get_active_prompt())]

        templates_attached = 0
        ideal_slot = IDEAL_SLOT_FOR_DIRECTION.get(direction)
        for slot, label in ((ideal_slot, "IMAGE A - Ideal Continuation Setup"), (FAIL_TRAP_SLOT, "IMAGE B - Invalid Trap Setup")):
            if not slot:
                continue
            record = self.template_store.get_template(slot)
            b64 = self.template_store.get_template_base64(slot) if record else None
            if not record or not b64:
                continue
            parts.append(ContentPart.text_part(f"{label}: {record.caption}"))
            parts.append(ContentPart.image_part(b64))
            templates_attached += 1

        if templates_attached == 0:
            logger.info("No matching template images uploaded yet - evaluating from text/live-chart only.")

        metrics_lines = [f"INPUT DATA METRICS:", f"- Trigger Direction: {direction}"]
        if calculated_slope is not None:
            metrics_lines.append(f"- Calculated 20 MA Slope Metric: {calculated_slope:.2f} points")
        if headroom_pips is not None:
            metrics_lines.append(f"- Distance to Nearest Target (Swing High/Low): {headroom_pips:.5f} headroom")
        if risk_reward_ratio is not None:
            metrics_lines.append(f"- Risk-to-Reward Ratio: {risk_reward_ratio:.2f}")
        if higher_timeframe_bias:
            metrics_lines.append(f"- 5m / 1h Macro Bias: {higher_timeframe_bias}")
        parts.append(ContentPart.text_part("\n".join(metrics_lines)))

        parts.append(ContentPart.text_part(f"MARKET DATA SUMMARY:\n{market_summary_text}"))

        if live_chart_b64:
            parts.append(ContentPart.text_part("IMAGE C - ACTIVE LIVE CHART (decide on this one):"))
            parts.append(ContentPart.image_part(live_chart_b64))

        try:
            raw_response = self.llm_provider.analyze(parts, max_tokens=self.max_tokens, temperature=self.temperature)
        except Exception as e:
            logger.error(f"Vision compliance LLM call failed: {e}")
            return ComplianceVerdict(verdict="REJECT", confidence=0, reasoning=f"LLM call failed: {e}", raw_response="")

        return self._parse_verdict(raw_response)

    def _parse_verdict(self, raw_response: str) -> ComplianceVerdict:
        try:
            if "{" not in raw_response or "}" not in raw_response:
                raise ValueError("no JSON object found in response")

            start = raw_response.find("{")
            end = raw_response.rfind("}") + 1
            data = json.loads(raw_response[start:end])

            verdict = str(data.get("verdict", "REJECT")).upper()
            if verdict not in ("ACCEPT", "REJECT"):
                verdict = "REJECT"

            # confidence_score is documented as 0.00-1.00, but tolerate a model
            # that returns 0-100 anyway rather than silently misreading it.
            raw_confidence = float(data.get("confidence_score", data.get("confidence", 0)) or 0)
            confidence = raw_confidence * 100.0 if raw_confidence <= 1.0 else raw_confidence
            confidence = max(0.0, min(100.0, confidence))

            reasoning = str(data.get("visual_rejection_reason", data.get("reasoning", "")))

            return ComplianceVerdict(
                verdict=verdict,
                confidence=confidence,
                reasoning=reasoning,
                raw_response=raw_response,
            )
        except Exception as e:
            logger.error(f"Failed to parse vision-compliance response, failing closed: {e}. Raw: {raw_response[:300]!r}")
            return ComplianceVerdict(
                verdict="REJECT",
                confidence=0,
                reasoning=f"Unparseable LLM response, failed closed: {e}",
                raw_response=raw_response,
            )
