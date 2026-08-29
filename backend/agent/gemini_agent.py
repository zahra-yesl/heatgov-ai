"""Gemini conversational agent with function calling.

Uses the modern `google-genai` SDK. The older `google-generativeai` package
reached end of life and prints a deprecation notice on import.

Run directly for a live conversation test:

    .venv/Scripts/python.exe backend/agent/gemini_agent.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

import config  # noqa: E402
from agent.tools import TOOL_FUNCTIONS  # noqa: E402

MAX_TOOL_ROUNDS = 6
MAX_RETRIES = 3

SYSTEM_PROMPT = """You are HeatGov AI, an advisor helping American municipal \
officials decide where to invest against urban heat.

You have access to a trained XGBoost model that predicts heat vulnerability \
scores for 94 census tracts in Central Los Angeles, built from FortyGuard \
hyperlocal temperature data and labelled against CalEnviroScreen 4.0.

When asked about priorities or investments, always:
1. Call get_top_risk_zones or optimize_budget first. Never guess a score.
2. Explain the top 2-3 zones using explain_zone.
3. Recommend interventions with concrete dollar figures.

Cite temp_max_22h - night-time heat - as our key scientific insight when it is \
relevant. Our measurement across 8,674 tiles found zero overlap between the 10% \
hottest tiles at 15:00 and the 10% hottest at 22:00: the neighbourhoods that \
bake in the afternoon are not the ones that stay hot overnight, and night heat \
is what prevents the body from recovering.

Ground rules:
- Report only numbers the tools return. If a tool did not give you a figure, \
say you do not have it.
- Costs are planning-grade estimates from public sources, never quotes. Say so \
when you present a budget.
- If a tool reports canopy_data_available as false or a confidence of \
"provisional", tell the official plainly which parts of the recommendation are \
firm and which are not.
- CalEnviroScreen contains no heat indicator. We test whether heat metrics \
predict an environmental-justice score; we do not reproduce an official heat \
index. Do not overstate this.
- Call FortyGuard tiles "modeled tiles" or simply "tiles", never "sensors" or \
"sensor tiles". They are hyperlocal modeled estimates at 100 m resolution, not \
physical instruments, and a FortyGuard reviewer would catch the difference.
- Write for a busy non-technical official: short paragraphs, concrete numbers, \
American English."""


def _declarations() -> list[types.FunctionDeclaration]:
    """Schemas Gemini reads to decide which tool to call and with what."""
    return [
        types.FunctionDeclaration(
            name="get_top_risk_zones",
            description=(
                "Return the most heat-vulnerable census tracts in Central Los "
                "Angeles, ranked by predicted risk score, with coordinates, "
                "night temperature, impervious surface and median income."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "top_n": {"type": "INTEGER",
                              "description": "How many zones to return (1-50, default 10)."}
                },
            },
        ),
        types.FunctionDeclaration(
            name="explain_zone",
            description=(
                "Explain why one census tract scores as it does, using SHAP on "
                "the physical-only model. Returns the three strongest physical "
                "drivers with their contribution in score points."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "tract_fips": {"type": "STRING",
                                   "description": "11-digit census tract FIPS code."}
                },
                "required": ["tract_fips"],
            },
        ),
        types.FunctionDeclaration(
            name="recommend_intervention",
            description=(
                "Recommend the intervention best suited to one tract's built "
                "form: cool_roof, trees or shade, with cost and expected "
                "temperature reduction."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "tract_fips": {"type": "STRING",
                                   "description": "11-digit census tract FIPS code."}
                },
                "required": ["tract_fips"],
            },
        ),
        types.FunctionDeclaration(
            name="optimize_budget",
            description=(
                "Compute the best combination of interventions for a given "
                "budget, maximising risk-weighted cooling. Returns the funded "
                "plan, total cost and coverage score."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "budget_usd": {"type": "NUMBER",
                                   "description": "Available budget in US dollars."},
                    "top_n": {"type": "INTEGER",
                              "description": "How many high-risk zones to consider (default 10)."},
                },
                "required": ["budget_usd"],
            },
        ),
        types.FunctionDeclaration(
            name="get_heatmap_stats",
            description=(
                "Return summary statistics for one FortyGuard layer. Valid "
                "values: tcm_peak_15h, tcm_peak_22h, tcm_daily, exceedance, "
                "persistence, time_of_measure."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "analytic_type": {"type": "STRING",
                                      "description": "Layer name."}
                },
                "required": ["analytic_type"],
            },
        ),
    ]


class AgentUnavailable(RuntimeError):
    """No API key, or Gemini could not be reached."""


class HeatGovAgent:
    """Runs the tool-calling loop and returns a finished answer."""

    def __init__(self, model: str | None = None) -> None:
        if not config.GEMINI_API_KEY:
            raise AgentUnavailable(
                "GEMINI_API_KEY is not set. Add it to .env. "
                "Get a key at https://ai.google.dev/"
            )
        self.model = model or config.GEMINI_MODEL
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.tools = [types.Tool(function_declarations=_declarations())]

    def _generate(self, contents: list) -> types.GenerateContentResponse:
        """One model call, retrying the 503 that flash models return under load."""
        last: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        tools=self.tools,
                        temperature=0.2,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                last = exc
                if "503" in str(exc) and attempt < MAX_RETRIES:
                    time.sleep(4 * attempt)
                    continue
                raise AgentUnavailable(f"{type(exc).__name__}: {exc}") from exc
        raise AgentUnavailable(str(last))

    def chat(self, user_message: str, session_history: list | None = None,
             verbose: bool = False) -> dict:
        """Answer one message, running any tools Gemini decides to call."""
        contents = list(session_history or [])
        contents.append(types.Content(role="user",
                                      parts=[types.Part(text=user_message)]))

        trace: list[dict] = []

        for round_index in range(MAX_TOOL_ROUNDS):
            response = self._generate(contents)
            calls = getattr(response, "function_calls", None) or []

            if not calls:
                text = response.text or ""
                if response.candidates and response.candidates[0].content:
                    contents.append(response.candidates[0].content)
                return {
                    "reply": text,
                    "tool_calls": trace,
                    "history": contents,
                    "model": self.model,
                    "rounds": round_index + 1,
                }

            contents.append(response.candidates[0].content)

            parts = []
            for call in calls:
                name = call.name
                arguments = dict(call.args or {})
                if verbose:
                    print(f"    -> {name}({arguments})")

                function = TOOL_FUNCTIONS.get(name)
                if function is None:
                    result = {"error": f"Unknown tool {name}"}
                else:
                    try:
                        result = function(**arguments)
                    except Exception as exc:  # noqa: BLE001
                        # Hand the failure back to Gemini rather than crashing:
                        # it can apologise or try a different tool.
                        result = {"error": f"{type(exc).__name__}: {exc}"}

                trace.append({"tool": name, "args": arguments, "result": result})
                parts.append(types.Part.from_function_response(
                    name=name, response={"result": result}
                ))

            contents.append(types.Content(role="user", parts=parts))

        return {
            "reply": ("I could not finish that within the tool-call budget. "
                      "Please narrow the question."),
            "tool_calls": trace,
            "history": contents,
            "model": self.model,
            "rounds": MAX_TOOL_ROUNDS,
        }


_AGENT: HeatGovAgent | None = None


def get_agent() -> HeatGovAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = HeatGovAgent()
    return _AGENT


def chat(user_message: str, session_history: list | None = None) -> dict:
    return get_agent().chat(user_message, session_history)


def main() -> int:
    try:
        agent = get_agent()
    except AgentUnavailable as exc:
        print(f"AGENT UNAVAILABLE: {exc}")
        return 1

    print(f"HeatGov AI agent - model {agent.model}")
    print("=" * 78)

    questions = [
        "I have $500,000 for Central Los Angeles. Where should I invest first, and why?",
        "Why does night-time heat matter more than the afternoon peak?",
    ]

    history: list = []
    for question in questions:
        print(f"\nUSER: {question}\n")
        started = time.time()
        result = agent.chat(question, history, verbose=True)
        history = result["history"]

        print(f"\n  [{len(result['tool_calls'])} tool call(s), "
              f"{result['rounds']} round(s), {time.time() - started:.1f}s]\n")
        print("AGENT:")
        print(result["reply"])
        print("-" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
