"""Find student text that addresses the grader (prompt injection).

Detection is done in code, so it is the same on every run. The text itself is
never removed or rewritten: it stays data for the model, and the professor
sees the flag. Flag messages give the location only, never the text.
"""
import re

from .models import Flag

PATTERNS = [
    r"\bignore\s+(?:all\s+|the\s+|any\s+|previous\s+|prior\s+|above\s+)*(?:rubric|instructions?|rules|prompt)\b",
    r"\bdisregard\s+(?:all\s+|the\s+|any\s+|previous\s+)*(?:rubric|instructions?|rules|prompt)\b",
    r"\bgive\s+(?:this|it|us|me|them|the\s+team)\s+(?:a|an|the)?\s*(?:\d+|full|perfect|max(?:imum)?|top|excellent|strong|high)",
    r"\b(?:grade|score|mark|rate)\s+(?:this|it|us|me)\s+(?:as\s+)?(?:a\s+)?(?:\d+|excellent|strong|perfect|full|max(?:imum)?|a\+?)\b",
    r"^\s*(?:system|assistant|developer)\s*:",
    r"<\s*/?\s*(?:system|instructions?|rubric|transcript|notebook)\s*>",
    r"\b(?:to|dear|attention|note\s+to)\s+(?:the\s+)?(?:ai|grader|model|llm|claude|assistant)\b",
    r"\byou\s+are\s+(?:now\s+)?(?:a|an|the)\s+(?:grader|assistant|ai|model)\b",
    r"\bnew\s+instructions?\b",
    r"\boverride\s+(?:the\s+)?(?:score|grade|rubric|instructions?)\b",
]
_RE = re.compile("|".join(f"(?:{p})" for p in PATTERNS), re.IGNORECASE | re.MULTILINE)


def addresses_grader(text: str | None) -> bool:
    return bool(text) and _RE.search(text) is not None


def find_injections(transcript: dict | None, notebook: dict | None) -> list[Flag]:
    where = []
    for s in (transcript or {}).get("segments", []):
        if addresses_grader(s.get("text")):
            where.append(f"transcript segment {s['id']}")
    for c in (notebook or {}).get("cells", []):
        if addresses_grader(c.get("source")):
            where.append(f"notebook cell {c['index']}")
        if any(addresses_grader(o.get("text")) for o in c.get("outputs", [])):
            where.append(f"output of notebook cell {c['index']}")
    for n in (notebook or {}).get("names", []):
        if addresses_grader(n.get("name")):
            where.append("student name field")
    return [Flag.make("INJECTION_SUSPECTED",
                      f"Text in {w} seems to address the grader. It was treated as data, not instructions. "
                      "Check this section's suggestion yourself.")
            for w in dict.fromkeys(where)]
