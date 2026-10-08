"""Grader-side models for suggestion.json.

Stand-ins written from the team plan (section "suggestion.json"). Replace with the
shared models in easygrade/contracts/ once task 0.1 lands.
"""
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

Ref = Union[int, str]  # notebook cell_index or transcript segment id

FLAG_SEVERITY = {
    "GRADER_FAILED": "block",
    "QUOTE_UNVERIFIED": "warn",
    "LOW_CONFIDENCE_SECTION": "warn",
}


class Flag(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warn", "block"]

    @classmethod
    def make(cls, code: str, message: str) -> "Flag":
        return cls(code=code, message=message, severity=FLAG_SEVERITY[code])


# --- What the model returns (tool input) ---

class ModelEvidence(BaseModel):
    source: Literal["transcript", "notebook"]
    ref: Ref = Field(description="Transcript segment id or notebook cell index")
    quote: str = Field(description="Exact text copied from that segment or cell")


class ModelSection(BaseModel):
    section_id: str
    level: str
    score: float
    confidence: Literal["low", "medium", "high"]
    rationale: str
    evidence: list[ModelEvidence] = []


class ModelOutput(BaseModel):
    sections: list[ModelSection]


# --- suggestion.json ---

class Evidence(ModelEvidence):
    verified: bool = False


class Section(BaseModel):
    section_id: str
    level: str
    score: float
    max_points: float
    confidence: Literal["low", "medium", "high"]
    rationale: str
    checkable: Literal["full", "partial", "none"] = "full"
    evidence: list[Evidence] = []
    flags: list[Flag] = []


class AiUsage(BaseModel):
    status: Literal["no_concern", "review"] = "no_concern"
    evidence: list[Evidence] = []
    note: str = "Not assessed by this grader version."


class Validation(BaseModel):
    scores_in_range: bool = False
    quotes_checked: int = 0
    quotes_verified: int = 0
    errors: list[str] = []


class Suggestion(BaseModel):
    schema_version: str = "1"
    team_id: str
    produced_by: str
    status: Literal["ok", "failed", "needs_manual"]
    model: str
    prompt_version: str
    rubric_version: str
    names_sent_to_model: bool
    sections: list[Section] = []
    total: Optional[float] = None  # computed by code; None when failed
    comments: dict[str, str] = {}
    ai_usage: AiUsage = AiUsage()
    validation: Validation = Validation()
    flags: list[Flag] = []
