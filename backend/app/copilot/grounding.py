"""Grounding validator and renderer.

The language model returns sentences made of plain connective words and {{fact_id}} placeholders, plus the fact ids each sentence
cites. This module (1) checks the reply against the fact sheet and a set of hard rules and (2) renders every value, name and path
from the fact sheet. If anything is uncertain the whole reply is rejected and the caller falls back to deterministic templates.

What this does NOT guarantee: it blocks literal numbers, unknown ids, unsupported entity names, forbidden claim vocabulary and
misuse of "robust"/"fragile"; it cannot prove that a sentence's *reasoning* is sound. Wrong comparisons made only with allowed words
(for example calling a smaller value larger) are not detected, which is why every sentence is shown with its cited facts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from ..schemas.copilot import SECTIONS, Sentence
from .facts import FactSheet

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
NUMBER_WORDS = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
                "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "hundred", "thousand", "million",
                "billion", "half", "double", "triple", "quarter", "percent", "dozen", "tenfold"}
FORBIDDEN = re.compile(r"\b(probab\w*|likel\w+|forecast\w*|predict\w*|saving\w*|saves?|saved|guarantee\w*|proven|proves?|accura\w+|"
                       r"empiric\w*|validated|verified|observed|certain(ly)?|inevitabl\w+|will\s+(lose|cost|reduce|save|happen)|expected\s+loss|"
                       r"return\s+on|payback|profit\w*|should|must|recommend\w*|advis\w*|ought|need(s)?\s+to)\b", re.I)
STABILITY_WORDS = re.compile(r"\b(robust\w*|stable|stability|reliabl\w+|confident\w*|dependabl\w+)\b", re.I)
FRAGILE_WORDS = re.compile(r"\bfragile\b", re.I)
REAL_WORDS = re.compile(r"\breal\b", re.I)
ALLOWED_CAPS = {"JRC", "Copernicus", "CEMS", "EU", "I", "A", "The", "This", "These", "It", "In", "At", "Because", "While", "Although"}
MITIGATION_PREFIXES = ("mit_", "plan_", "cost_", "tail_", "reduction_", "residual_", "exhaustive_", "optimality_", "robust_", "budget", "events_considered", "tail_events")
UNSUPPORTED_MESSAGES = {
    "probability": "The model has no event probabilities, so it cannot say how likely this event is.",
    "forecast": "This is a scenario ranking under synthetic assumptions, not a forecast.",
    "savings": "Intervention costs are synthetic placeholders; the model makes no claim about real-world savings, returns or payback.",
    "real_world_validation": "No empirical validation exists: the model has not been checked against observed disruptions or losses.",
    "advice": "The copilot does not give advice or decide priorities; it reports the options the model evaluated and what each does in the model.",
    "worst_case": "The model reports ranked scenario results and parameter-draw ranges, not a worst-case or maximum loss.",
    "other_no_evidence": "The fact sheet does not contain evidence for part of this question, so the model does not answer it.",
}
Q_RULES = {
    "probability": re.compile(r"\b(probab\w*|likelihood|how likely|chance|odds|return period)\b", re.I),
    "forecast": re.compile(r"\b(forecast\w*|predict\w*|next (year|decade|summer)|will (it|this) (happen|occur))\b", re.I),
    "savings": re.compile(r"\b(sav(e|es|ing|ings)|roi|return on|payback|profit\w*|worth (it|the)|break[- ]?even)\b", re.I),
    "advice": re.compile(r"\b(should|recommend\w*|advice|advise|what (do|to do)|do first|next steps?|priorit\w+)\b", re.I),
    "worst_case": re.compile(r"\b(worst[- ]case|maximum loss|max loss|upper bound|biggest possible|at most)\b", re.I),
    "real_world_validation": re.compile(r"\b(validat\w*|accura\w+|proven|proof|true loss|real loss(es)?|how (sure|certain))\b", re.I),
}


class LLMSentence(BaseModel):
    text: str = Field(min_length=3, max_length=420)
    cites: list[str] = Field(min_length=1, max_length=8)


class LLMAnswer(BaseModel):
    sections: dict[str, list[LLMSentence]]
    unsupported: list[str] = Field(default_factory=list, max_length=5)


@dataclass
class Violation:
    section: str
    index: int
    code: str
    detail: str = ""


@dataclass
class Validation:
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    sentences_checked: int = 0
    sentences_failed: int = 0

    def codes(self) -> list[str]:
        return sorted({v.code for v in self.violations})


def classify_question(q: str) -> list[str]:
    return [code for code, rx in Q_RULES.items() if rx.search(q)]


def parse_llm_json(raw: str) -> tuple[Optional[LLMAnswer], Optional[str]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|```$", "", raw).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid_json: {e.msg}"
    try:
        ans = LLMAnswer.model_validate(obj)
    except ValidationError as e:
        return None, "schema_mismatch: " + str(e.errors()[0].get("loc"))
    unknown = [k for k in ans.sections if k not in SECTIONS]
    if unknown:
        return None, f"schema_mismatch: unknown section {unknown[0]}"
    return ans, None


def _check_sentence(sheet: FactSheet, section: str, i: int, s: LLMSentence) -> list[Violation]:
    out: list[Violation] = []
    v = lambda code, detail="": out.append(Violation(section, i, code, detail))  # noqa: E731
    facts = sheet.facts
    for c in s.cites:
        if c not in facts:
            v("unknown_cite", c)
    holders = [m for m in PLACEHOLDER.findall(s.text)]
    for h in holders:
        if h not in facts:
            v("unknown_placeholder", h)
        elif h not in s.cites:
            v("placeholder_not_cited", h)
    bare = PLACEHOLDER.sub(" ", s.text)
    if "{{" in bare or "}}" in bare:
        v("malformed_placeholder")
    if re.search(r"\d", bare):
        v("literal_number", re.search(r".{0,12}\d.{0,12}", bare).group(0))
    if re.search(r"[%$€£]", bare):
        v("literal_unit_symbol")
    words = re.findall(r"[A-Za-z']+", bare)
    low = {w.lower() for w in words}
    if low & NUMBER_WORDS:
        v("number_word", ", ".join(sorted(low & NUMBER_WORDS)))
    m = FORBIDDEN.search(bare)
    if m:
        v("forbidden_claim_word", m.group(0))
    if re.search(r"[<>`*_#|]|https?://|→|->|=>", bare):
        v("markup_or_url")
    # unsupported proper nouns: capitalised tokens (not sentence-initial common words) that are not placeholders
    toks = bare.split()
    for k, t in enumerate(toks):
        w = re.sub(r"[^A-Za-z]", "", t)
        if not w or not w[0].isupper() or w in ALLOWED_CAPS:
            continue
        if k == 0 and w not in sheet.all_entity_vocab:
            continue                       # sentence-initial ordinary word
        v("proper_noun_not_from_facts", w)
    cited = [facts[c] for c in s.cites if c in facts]
    if STABILITY_WORDS.search(bare):
        if not any(f.is_stability for f in cited):
            v("stability_claim_without_stability_fact")
        if any(f.is_magnitude for f in cited):
            v("stability_claim_mixed_with_magnitude")
        for f in cited:
            if f.id in ("p_top5", "robust_positive") and isinstance(f.value, (int, float)) and f.value < 0.9:
                v("stability_claim_contradicted_by_value", f"{f.id}={f.rendered}")
    if FRAGILE_WORDS.search(bare):
        f = facts.get("fragile")
        if f is None or f.value is not True or "fragile" not in s.cites:
            v("fragile_claim_unsupported")
    if REAL_WORDS.search(bare) and not any(f.provenance == "real_hazard_context" for f in cited):
        v("real_claim_without_real_data_fact")
    if section == "mitigations" and not any(c.startswith(MITIGATION_PREFIXES) or c == "residual_loss" for c in s.cites):
        v("mitigation_without_mitigation_fact")
    return out


def normalise(ans: LLMAnswer) -> LLMAnswer:
    """Harmless clean-up: a placeholder the sentence uses but forgot to list is added to cites (cites only drive provenance labels; unknown ids
    stay violations). Nothing else is changed."""
    for sents in ans.sections.values():
        for s in sents:
            for h in PLACEHOLDER.findall(s.text):
                if h not in s.cites and len(s.cites) < 8:
                    s.cites.append(h)
    return ans


def validate(sheet: FactSheet, ans: LLMAnswer) -> Validation:
    val = Validation(ok=True)
    for sec, sents in ans.sections.items():
        if len(sents) > 3:
            val.violations.append(Violation(sec, 0, "too_many_sentences"))
        for i, s in enumerate(sents):
            val.sentences_checked += 1
            vs = _check_sentence(sheet, sec, i, s)
            if vs:
                val.sentences_failed += 1
                val.violations.extend(vs)
    # an empty answer is legitimate when the model declined the question as unsupported: the server then writes the answer from templates
    if (not ans.sections.get("answer")) and not ans.unsupported:
        val.violations.append(Violation("answer", 0, "missing_answer"))
    if "uncertainty" not in ans.sections or not ans.sections["uncertainty"]:
        val.violations.append(Violation("uncertainty", 0, "missing_uncertainty_section"))
    for code in ans.unsupported:
        if code not in UNSUPPORTED_MESSAGES:
            val.violations.append(Violation("unsupported", 0, "bad_unsupported_code", code))
    val.ok = not val.violations
    return val


HEDGE = " (modelled value, not validated)"


def render_sentence(sheet: FactSheet, text: str, cites: list[str], template: bool = False) -> Sentence:
    out = PLACEHOLDER.sub(lambda m: sheet.facts[m.group(1)].rendered, text)
    # a sentence that states a loss, impact or cost figure always says it is a model output, whatever the wording around it
    if any(sheet.facts[c].is_magnitude for c in cites) and not re.search(r"\b(model|modelled|placeholder)\b", out, re.I):
        out = out.rstrip().rstrip(".") + HEDGE + "."
    prov: list[str] = []
    for c in cites:
        p = sheet.facts[c].provenance
        if p not in prov:
            prov.append(p)
    return Sentence(text=out, cites=list(cites), provenance=prov, template=template)  # type: ignore[arg-type]


def render_answer(sheet: FactSheet, ans: LLMAnswer) -> dict[str, list[Sentence]]:
    return {sec: [render_sentence(sheet, s.text, s.cites) for s in sents] for sec, sents in ans.sections.items()}
