"""Schemas for the AI Climate Risk Copilot. The language model never produces a number, entity name, path or probability:
it selects fact ids; the server renders every value from the deterministic fact sheet."""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from .finder import FinderRequest, OptimiseRequest
from .scenario import HoldingView

Provenance = Literal["synthetic_input", "model_assumption", "real_hazard_context", "unvalidated_model_output", "model_robustness",
                     "empirically_validated"]
Provider = Literal["ollama", "anthropic", "deterministic"]
SECTIONS = ("answer", "why_it_matters", "how_it_propagates", "holdings_affected", "mitigations", "uncertainty")


class FinderEventFocus(BaseModel):
    kind: Literal["finder_event"] = "finder_event"
    event_id: str = Field(min_length=1, max_length=200)
    finder: FinderRequest = Field(default_factory=FinderRequest, description="Same settings the Finder page used")


class ScenarioFocus(BaseModel):
    kind: Literal["scenario"] = "scenario"
    scenario_id: str = Field(min_length=1, max_length=64)
    max_depth: Optional[int] = Field(default=None, ge=1, le=10)
    holding_view: HoldingView = Field(default="company", description="Same holding definition the Results page used")


class MitigationFocus(BaseModel):
    kind: Literal["mitigation_plan"] = "mitigation_plan"
    optimise: OptimiseRequest = Field(default_factory=lambda: OptimiseRequest(budget_musd=3.0))


Focus = Union[FinderEventFocus, ScenarioFocus, MitigationFocus]


class FactOut(BaseModel):
    id: str
    label: str
    value: Union[float, int, str, bool, None]
    rendered: str
    unit: str
    provenance: Provenance
    source: str = Field(description="API field or model result this value comes from")


class FactsRequest(BaseModel):
    focus: Focus = Field(discriminator="kind")


class FactsResponse(BaseModel):
    title: str
    focus_kind: str
    facts: list[FactOut]
    standing_notes: list[str]


class ReportRequest(BaseModel):
    focus: Focus = Field(discriminator="kind")
    use_model: bool = Field(default=False, description="Phrase the summary with the language model; used only if its reply passes grounding validation")
    provider: Optional[Provider] = None


class AskRequest(BaseModel):
    focus: Focus = Field(discriminator="kind")
    question: str = Field(default="Explain why this matters, how it propagates, what could help and what is uncertain.", min_length=3, max_length=500)
    provider: Optional[Provider] = Field(default=None, description="Override the configured provider; 'anthropic' only works if a key is configured server-side")


class Sentence(BaseModel):
    text: str = Field(description="Server-rendered text: all values, names and paths substituted from the fact sheet")
    cites: list[str]
    provenance: list[Provenance]
    template: bool = Field(default=False, description="True when the sentence came from a deterministic template, not the language model")


class AskResponse(BaseModel):
    title: str
    question: str
    mode: Literal["llm", "deterministic"]
    provider: str
    model: Optional[str] = None
    fallback_reason: Optional[str] = None
    latency_ms: int
    sections: dict[str, list[Sentence]]
    unsupported: list[str] = Field(description="Parts of the question the model cannot answer from its evidence, stated by the server")
    standing_notes: list[str]
    facts: list[FactOut]
    validation: dict = Field(description="Validator outcome for the language-model reply (accepted, violation codes)")


class ReportResponse(BaseModel):
    title: str
    mode: Literal["llm", "deterministic"]
    fallback_reason: Optional[str]
    markdown: str


class StatusResponse(BaseModel):
    configured_provider: str
    ollama: dict
    anthropic: dict
    deterministic: bool = True
