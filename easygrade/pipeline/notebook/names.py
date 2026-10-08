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
_MAX_NAME_WORDS = 5
_MAX_NAME_CHARS = 60


def _clean_line(line: str) -> str:
    """Drop Markdown decoration (**bold**, # headings, `code`, > quotes, list bullets)."""
    line = _MD_NOISE.sub("", line)
    line = re.sub(r"^\s*(?:[-+]|\d+[.)])\s+", "", line)
    return line.strip()


def _plausible_name(name: str) -> bool:
    words = name.split()
    return (
        0 < len(words) <= _MAX_NAME_WORDS
        and len(name) <= _MAX_NAME_CHARS
        and name[0].isalpha()
        and not re.search(r"[.!?:;=()\[\]{}<>/\\@\d]", name)
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
            for part in sep.split(m.group("names")):
                name = part.strip(" \t.,;")
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
