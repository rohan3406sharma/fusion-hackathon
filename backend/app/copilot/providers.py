"""Language-model providers. All of them only ever receive the fact sheet and the user's question, and return raw text that is
validated by grounding.py before anything is shown. Keys stay server-side."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from ..config import Settings
from ..schemas.copilot import SECTIONS
from .facts import FactSheet
from .grounding import UNSUPPORTED_MESSAGES


class ProviderError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass
class Generation:
    text: str
    model: str
    latency_ms: int


SYSTEM = """You write short, plain-English explanations for climate-risk analysts, using ONLY the fact sheet you are given.

HARD RULES (a program checks them; any violation discards your whole answer):
1. Never type a digit, a number word (one, two, half, percent, ...), a percent sign or a currency symbol. Every number, name, path and ranking appears ONLY as a placeholder like {{impact_network}} that refers to a fact id. The program fills in the real value.
2. Every sentence lists in "cites" every fact id it uses, and every placeholder must also be in "cites". Use only ids that appear in the fact sheet.
3. Do not mention any company, place or person by name in plain text; use the placeholder of the fact that holds the name.
4. Never use these words, even to deny them: probability, likely, forecast, predict, save, savings, guarantee, accurate, validated, verified, observed, empirical, certain, profit, real, robust, stable, reliable, confident, fragile. The server writes all statements about validation, data status and ranking stability itself, so do not write any caveats of your own.
5. The "mitigations" section may only cite facts whose ids start with mit_, plan_, cost_, tail_, reduction_, residual_, exhaustive_, optimality_, robust_, budget. If there are none, return an empty list for mitigations.
6. If the question asks about likelihood, forecasts, money saved or whether results are validated, do NOT answer that part (the server answers it); add the code to "unsupported": probability, forecast, savings, real_world_validation, advice, worst_case, other_no_evidence. Never give advice or say what someone should do; only explain what the facts show. Answer only the part the facts support.
7. In the fact sheet, values shown as <name>, <number> or <notice> are hidden on purpose: refer to them only with their placeholder. Facts are listed in order of importance (holding_1 is the most affected).
8. If the facts you need for the question do not exist in the sheet, do not invent ids: leave the section empty and add other_no_evidence to "unsupported".
9. At most 2 sentences per section, each under 40 words, in plain connective English. Sections: answer (directly answers the question), why_it_matters, how_it_propagates, holdings_affected, mitigations, uncertainty (what is still unknown, using only the facts given).
Return ONLY JSON matching the schema."""

EXAMPLE = ('{"sections":{"answer":[{"text":"{{event_label}} costs the portfolio {{impact_network}} in the model, mostly through supply links.",'
           '"cites":["event_label","impact_network"]}],"why_it_matters":[],"how_it_propagates":[],"holdings_affected":[],"mitigations":[],'
           '"uncertainty":[{"text":"{{notice_unvalidated}}","cites":["notice_unvalidated"]}]},"unsupported":[]}')


def schema() -> dict:
    sent = {"type": "object", "properties": {"text": {"type": "string"}, "cites": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8}},
            "required": ["text", "cites"]}
    return {"type": "object", "properties": {
        "sections": {"type": "object", "properties": {s: {"type": "array", "items": sent, "maxItems": 2} for s in SECTIONS}, "required": list(SECTIONS)},
        "unsupported": {"type": "array", "items": {"type": "string", "enum": list(UNSUPPORTED_MESSAGES)}, "maxItems": 5}},
        "required": ["sections", "unsupported"]}


PROMPT_TAGS = {"synthetic_input": "SYNTHETIC", "model_assumption": "ASSUMPTION", "real_hazard_context": "HAZARD-CONTEXT", "unvalidated_model_output": "MODEL-RESULT",
               "model_robustness": "RANK-STABILITY", "empirically_validated": "CHECKED"}


def prompt_value(f) -> str:
    """What the model is shown. Names, paths, notices and numbers are hidden (the server renders them from the placeholder), so the model
    cannot copy them into its text. Yes/no flags and short non-name text stay visible; ranking stability is shown as a plain band."""
    if f.kind == "text":
        if f.id.endswith(("_name", "_label")) or f.id.startswith(("path_", "no_path")):
            return "<name>"
        if f.id.startswith("notice_"):
            return "<notice>"
        return f.rendered[:60]
    if f.kind == "yesno":
        return f.rendered
    if f.is_stability and f.kind == "pct0" and isinstance(f.value, (int, float)):
        return "high" if f.value >= 0.9 else ("medium" if f.value >= 0.5 else "low")
    return "<number>"


def prompt_label(label: str) -> str:
    """Labels shown to the model contain no digits (it would otherwise restate thresholds like 'over 1%' in its own words)."""
    return re.sub(r"[<>=]*\s?\d+(\.\d+)?%?", "N", label)


def build_prompt(sheet: FactSheet, question: str) -> str:
    skip = lambda i: "_hop_" in i or i.startswith(("orderN_", "evidence_", "cost_sens_", "kendall")) or i == "entities_hit_directly"   # ambiguous: counts non-holding entities  # noqa: E731
    lines = [f"{f.id} | {prompt_label(f.label)} | {PROMPT_TAGS[f.provenance]} | {prompt_value(f)}" for f in sheet.facts.values() if not skip(f.id)]
    return ("FACT SHEET (id | label | kind of fact | value):\n" + "\n".join(lines) + f"\n\nQUESTION: {question}\n\n"
            f"Example of the required shape (different facts):\n{EXAMPLE}\n\nNow answer the question as JSON.")


class OllamaProvider:
    name = "ollama"

    def __init__(self, s: Settings):
        self.url, self.model, self.timeout = s.ollama_url.rstrip("/"), s.ollama_model, s.llm_timeout_s

    def status(self) -> dict:
        try:
            r = httpx.get(self.url + "/api/tags", timeout=2.5)
            names = [m.get("name") for m in r.json().get("models", [])]
            return {"reachable": True, "model": self.model, "model_present": self.model in names, "url": self.url}
        except Exception as e:  # noqa: BLE001
            return {"reachable": False, "model": self.model, "model_present": False, "url": self.url, "error": type(e).__name__}

    def generate(self, sheet: FactSheet, question: str) -> Generation:
        body = {"model": self.model, "stream": False, "think": False, "format": schema(),
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_prompt(sheet, question)}],
                "options": {"temperature": 0, "seed": 7, "num_predict": 1100, "num_ctx": 8192}}
        t0 = time.perf_counter()
        try:
            r = httpx.post(self.url + "/api/chat", json=body, timeout=self.timeout)
        except httpx.TimeoutException:
            raise ProviderError("timeout", f"no reply within {self.timeout}s")
        except httpx.HTTPError as e:
            raise ProviderError("unreachable", type(e).__name__)
        if r.status_code == 404:
            raise ProviderError("model_missing", self.model)
        if r.status_code != 200:
            raise ProviderError("http_error", str(r.status_code))
        try:
            text = r.json()["message"]["content"]
        except Exception:  # noqa: BLE001
            raise ProviderError("bad_response", "no message content")
        return Generation(text, self.model, int((time.perf_counter() - t0) * 1000))


class AnthropicProvider:
    """Optional, off by default. Requires FIN04_ANTHROPIC_API_KEY on the server; the key is never sent to the browser."""
    name = "anthropic"

    def __init__(self, s: Settings):
        self.key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None
        self.model, self.timeout = s.anthropic_model, s.llm_timeout_s

    def status(self) -> dict:
        return {"configured": bool(self.key), "model": self.model}

    def generate(self, sheet: FactSheet, question: str) -> Generation:
        if not self.key:
            raise ProviderError("not_configured", "no API key configured on the server")
        body = {"model": self.model, "max_tokens": 1200, "temperature": 0, "system": SYSTEM,
                "messages": [{"role": "user", "content": build_prompt(sheet, question)}]}
        t0 = time.perf_counter()
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", json=body, timeout=self.timeout,
                           headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        except httpx.TimeoutException:
            raise ProviderError("timeout", f"no reply within {self.timeout}s")
        except httpx.HTTPError as e:
            raise ProviderError("unreachable", type(e).__name__)
        if r.status_code != 200:
            raise ProviderError("http_error", str(r.status_code))
        try:
            text = "".join(b.get("text", "") for b in r.json()["content"])
        except Exception:  # noqa: BLE001
            raise ProviderError("bad_response", "no text content")
        return Generation(text, self.model, int((time.perf_counter() - t0) * 1000))


def get_provider(name: str, s: Settings):
    if name == "ollama":
        return OllamaProvider(s)
    if name == "anthropic":
        return AnthropicProvider(s)
    return None
