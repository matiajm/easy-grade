"""Draft model and loader for config/assignment.json (parser-relevant parts).

Unrelated keys (assigned questions, redact_names, ...) are ignored so Jorge's
final file can be a superset.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "assignment.json"


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _check_regex(pattern: str) -> str:
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"invalid regex {pattern!r}: {e}") from e
    return pattern


class NamePattern(_Base):
    label: str
    # Regex run per line of the header cell. Must have a named group "names".
    regex: str

    @field_validator("regex")
    @classmethod
    def _valid(cls, v: str) -> str:
        rx = re.compile(_check_regex(v))
        if "names" not in rx.groupindex:
            raise ValueError("name pattern needs a (?P<names>...) group")
        return v


class NameRules(_Base):
    header_cell_index: int = Field(0, ge=0)  # which cell holds the header
    patterns: list[NamePattern]
    # Regex that splits the captured text into individual names.
    separator_regex: str = r"\s*(?:,|;|&|\band\b)\s*"
    max_names: int = Field(6, ge=1)

    @field_validator("separator_regex")
    @classmethod
    def _valid_sep(cls, v: str) -> str:
        return _check_regex(v)

    @field_validator("patterns")
    @classmethod
    def _nonempty(cls, v: list) -> list:
        if not v:
            raise ValueError("at least one name pattern is required")
        return v


class HeaderRules(_Base):
    required_fields: list[str] = Field(default_factory=lambda: ["names", "course", "date"])
    # field -> regex (per line) whose group 1 is the value; "names" comes from name_rules.
    field_patterns: dict[str, str] = Field(default_factory=dict)

    @field_validator("field_patterns")
    @classmethod
    def _valid(cls, v: dict[str, str]) -> dict[str, str]:
        for p in v.values():
            _check_regex(p)
        return v

    @model_validator(mode="after")
    def _required_have_patterns(self):
        missing = [f for f in self.required_fields if f != "names" and f not in self.field_patterns]
        if missing:
            raise ValueError(f"required fields without a field_pattern: {missing}")
        return self


class AssignmentConfig(_Base):
    max_output_chars: int = Field(2000, gt=0)
    # Safety limits so one oversized notebook cannot blow up the bundle or the disk.
    max_source_chars: int = Field(20000, gt=0)
    max_images: int = Field(50, ge=0)
    max_image_bytes: int = Field(5_000_000, gt=0)
    max_notebook_bytes: int = Field(50_000_000, gt=0)
    filename_pattern: str
    name_rules: NameRules
    header_rules: HeaderRules

    @field_validator("filename_pattern")
    @classmethod
    def _valid_fn(cls, v: str) -> str:
        return _check_regex(v)


def load_config(path: Union[str, Path, None] = None) -> AssignmentConfig:
    """Load and validate assignment.json (raises pydantic.ValidationError)."""
    p = Path(path) if path else DEFAULT_PATH
    return AssignmentConfig.model_validate(json.loads(p.read_text(encoding="utf-8")))
