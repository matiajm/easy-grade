"""Draft Pydantic models for notebook_cells.json (parser output, part 2).

LOCAL DRAFT: Lucas's shared contracts (task 0.1) will replace this. To swap,
re-export the same names from the shared module. Unknown fields are ignored
on read, as the team plan requires.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1"


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


Severity = Literal["info", "warn", "block"]


class Flag(_Base):
    code: str
    message: str
    severity: Severity


# Flag registry for the codes this parser uses: code -> (default message, severity).
FLAG_REGISTRY: dict[str, tuple[str, Severity]] = {
    # block: nothing to grade, the professor must handle the team by hand.
    "NOTEBOOK_EMPTY": ("Notebook has no code and no Markdown with content.", "block"),
    "NOTEBOOK_UNREADABLE": ("Notebook could not be read.", "block"),
    # A missing name does not stop grading (the professor can type it in), so warn.
    "NAME_NOT_FOUND": ("No student names were found in the header cell.", "warn"),
    "HEADER_RULES": ("Header is missing required fields.", "warn"),
    "FILENAME_RULES": ("Notebook file name does not follow the naming rule.", "warn"),
    "EXEC_ORDER": ("Cells were not run strictly top to bottom.", "warn"),
    "ERROR_OUTPUT": ("One or more cells have saved error output.", "warn"),
}


def make_flag(code: str, message: Optional[str] = None) -> Flag:
    """Build a Flag from the registry; message may override the default."""
    default_message, severity = FLAG_REGISTRY[code]
    return Flag(code=code, message=message or default_message, severity=severity)


class NameEntry(_Base):
    name: str
    cell_index: int


class Header(_Base):
    found: bool
    # field name -> value text found in the header (e.g. {"course": "STA 2023"})
    fields: dict[str, str] = Field(default_factory=dict)
    rules_ok: bool


class Output(_Base):
    kind: Literal["text", "table", "error", "image"]
    text: Optional[str] = None  # truncated to max_output_chars
    image_ref: Optional[str] = None  # path of the extracted image, for kind=image


class Cell(_Base):
    index: int
    cell_type: Literal["code", "markdown", "raw"]
    source: str
    execution_count: Optional[int] = None
    outputs: list[Output] = Field(default_factory=list)
    has_error: bool = False
    syntax_ok: Optional[bool] = None  # null for non-code cells


class ImageRef(_Base):
    cell_index: int
    path: str
    mime: str


class ExecutionOrder(_Base):
    strictly_increasing: bool
    # indices of non-empty code cells never run although a later cell was
    skipped: list[int] = Field(default_factory=list)
    out_of_order_cells: list[int] = Field(default_factory=list)


class Checks(_Base):
    empty: bool
    execution_order: ExecutionOrder
    error_cells: list[int] = Field(default_factory=list)
    unexecuted_code_cells: list[int] = Field(default_factory=list)


class NotebookCells(_Base):
    schema_version: Literal["1"]
    team_id: str  # opaque, never a student name
    produced_by: str  # part name plus code version
    names: list[NameEntry] = Field(default_factory=list)
    header: Header
    filename_ok: bool
    cells: list[Cell] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    checks: Checks
    flags: list[Flag] = Field(default_factory=list)
