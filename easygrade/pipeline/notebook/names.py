"""Header, names and file-name checks for the notebook parser.

All rules come from config/assignment.json (see config.py). Only the header
cell is read, and only as text; nothing is executed.
"""
from __future__ import annotations

import re
from typing import Optional

from .config import AssignmentConfig
from .models import Header, NameEntry

_MD_NOISE = re.compile(r"[*_`#>]+")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # [text](url) -> text
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_SUFFIX = re.compile(r"\s+(?:Jr|Sr)\.?$")
_MAX_NAME_WORDS = 5
_MAX_NAME_CHARS = 60
# Characters a person's name does not contain; seeing one means the text is a sentence or data.
_NOT_NAME_CHARS = re.compile(r"[!?:;=()\[\]{}<>/\\@\d]|\.{2,}")
_SENTENCE_BREAK = re.compile(r"\.\s+[a-z]")  # "... code. in cells"


def _clean_line(line: str) -> str:
    """Drop Markdown/HTML decoration (**bold**, # headings, links, <b> tags, list bullets)."""
    line = _MD_LINK.sub(r"\1", line)
    line = _HTML_TAG.sub("", line)
    line = _MD_NOISE.sub("", line)
    line = re.sub(r"^\s*(?:[-+]|\d+[.)])\s+", "", line)
    return line.strip()


def _tidy_name(part: str) -> str:
    """Trim separators and a sentence-ending dot, but keep the dot of Jr., Sr. and initials (J.)."""
    name = part.strip(" \t,;")
    if name.endswith(".") and not _SUFFIX.search(name) and not re.search(r"(?:^|\s)[A-Z]\.$", name):
        name = name.rstrip(". ")
    return name


def _plausible_name(name: str) -> bool:
    """A short run of words that looks like a person's name, not a sentence."""
    if len(name) < 2 or not name[0].isalpha():  # a lone letter is a placeholder, not a name
        return False
    return (
        len(name.split()) <= _MAX_NAME_WORDS
        and len(name) <= _MAX_NAME_CHARS
        and not _NOT_NAME_CHARS.search(name)
        and not _SENTENCE_BREAK.search(name)
    )


def extract_names(source: str, cell_index: int, config: AssignmentConfig) -> list[NameEntry]:
    rules = config.name_rules
    sep = re.compile(rules.separator_regex)
    patterns = [re.compile(p.regex) for p in rules.patterns]
    found: list[str] = []
    for raw in source.splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        for rx in patterns:
            m = rx.match(line)
            if not m:
                continue
            captured = m.group("names")
            if ";" in captured:
                # "Last, First; Last, First": the commas belong to the names, so split on ; only.
                parts = re.split(r"\s*(?:;|&|\band\b)\s*", captured)
            else:
                parts = sep.split(captured)
            for part in parts:
                name = _tidy_name(part)
                if _plausible_name(name) and name not in found:
                    found.append(name)
            break
    return [NameEntry(name=n, cell_index=cell_index) for n in found[: rules.max_names]]


def read_header(cells: list, config: AssignmentConfig) -> tuple[Header, list[NameEntry]]:
    """cells: parsed Cell objects. Returns the Header and the names found in it."""
    idx = config.name_rules.header_cell_index
    source = cells[idx].source if idx < len(cells) else ""
    names = extract_names(source, idx, config) if source.strip() else []

    fields: dict[str, str] = {}
    for field, pattern in config.header_rules.field_patterns.items():
        rx = re.compile(pattern)
        for raw in source.splitlines():
            m = rx.match(_clean_line(raw))
            if m and m.group(1).strip():
                fields[field] = m.group(1).strip()
                break
    if names:
        fields["names"] = ", ".join(n.name for n in names)

    header = Header(found=bool(source.strip()), fields=fields, rules_ok=True)
    header.rules_ok = not missing_header_fields(header, config)
    return header, names


def missing_header_fields(header: Header, config: AssignmentConfig) -> list[str]:
    """Required fields other than names (a missing name has its own flag, NAME_NOT_FOUND)."""
    return [f for f in config.header_rules.required_fields if f != "names" and f not in header.fields]


def filename_ok(filename: Optional[str], config: AssignmentConfig) -> bool:
    return bool(filename) and re.match(config.filename_pattern, filename) is not None
