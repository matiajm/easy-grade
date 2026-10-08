"""Citation verifier: check every quote against the segment or cell it cites."""
import re
import unicodedata

from .models import Flag, Suggestion

_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip()


def _segment_texts(transcript: dict | None) -> dict[str, str]:
    if not transcript or transcript.get("status") != "ok":
        return {}
    return {str(s["id"]): s.get("text", "") for s in transcript.get("segments", [])}


def _cell_texts(notebook: dict | None) -> dict[str, str]:
    texts = {}
    for c in (notebook or {}).get("cells", []):
        outputs = [o["text"] for o in c.get("outputs", []) if o.get("text")]
        texts[str(c["index"])] = "\n".join([c.get("source", ""), *outputs])
    return texts


def verify(suggestion: Suggestion, transcript: dict | None, notebook: dict | None) -> Suggestion:
    sources = {"transcript": _segment_texts(transcript), "notebook": _cell_texts(notebook)}
    checked = verified = 0
    for section in suggestion.sections:
        for ev in section.evidence:
            checked += 1
            target = sources[ev.source].get(str(ev.ref))
            quote = normalize(ev.quote)
            ev.verified = bool(quote) and target is not None and quote in normalize(target)
            if ev.verified:
                verified += 1
            else:
                section.flags.append(Flag.make(
                    "QUOTE_UNVERIFIED", f"Quote not found in {ev.source} {ev.ref}."))
        if not any(ev.verified for ev in section.evidence):
            section.flags.append(Flag.make(
                "LOW_CONFIDENCE_SECTION", "No verified evidence for this section."))
    suggestion.validation.quotes_checked = checked
    suggestion.validation.quotes_verified = verified
    return suggestion
