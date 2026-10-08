"""Grade one team bundle with Claude and write suggestion.json.

Run: python -m easygrade.pipeline.grader.grade <bundle_dir> <rubric.json> [--out FILE]
Needs ANTHROPIC_API_KEY in the local environment.
"""
import argparse
import json
from pathlib import Path

from .injection import find_injections
from .models import AiUsage, Evidence, Flag, ModelOutput, Section, Suggestion, Validation
from .prompt import PROMPT_VERSION, TOOL, build_system_prompt, build_user_message
from .verify import verify

MODEL = "claude-opus-5-5"
PRODUCED_BY = "grader 0.1"


def _redact(cells: list[dict], names: list[str]) -> list[dict]:
    def scrub(text):
        for n in names:
            text = text.replace(n, "[STUDENT]")
        return text

    return [{**c, "source": scrub(c.get("source", "")),
             "outputs": [{**o, "text": scrub(o["text"])} if o.get("text") else o
                         for o in c.get("outputs", [])]}
            for c in cells]


def check_sections(model_out: ModelOutput, rubric: dict) -> tuple[list[Section], list[str], bool]:
    """Match model sections to the rubric. Scores are never clamped."""
    spec = {s["section_id"]: s for s in rubric["sections"]}
    sections, errors, in_range = [], [], True
    seen = set()
    for raw in model_out.sections:
        s = spec.get(raw.section_id)
        if s is None:
            errors.append(f"{raw.section_id}: not a rubric section")
            continue
        if raw.section_id in seen:
            errors.append(f"{raw.section_id}: graded more than once")
            continue
        seen.add(raw.section_id)
        level = next((lv for lv in s["levels"] if lv["level"] == raw.level), None)
        if level is None:
            errors.append(f"{raw.section_id}: unknown level {raw.level!r}")
            in_range = False
        elif not level["min_points"] <= raw.score <= level["max_points"]:
            errors.append(f"{raw.section_id}: score {raw.score} outside {raw.level} range "
                          f"{level['min_points']}-{level['max_points']}")
            in_range = False
        sections.append(Section(
            **raw.model_dump(exclude={"evidence"}),
            evidence=[Evidence(**e.model_dump()) for e in raw.evidence],
            max_points=s["max_points"],
            checkable=s.get("checkable", "full"),
        ))
    for sid in sorted(spec.keys() - seen):
        errors.append(f"{sid}: not graded")
    return sections, errors, in_range


def _failed(base: dict, error: Exception) -> Suggestion:
    return Suggestion(**base, status="failed",
                      validation=Validation(errors=[f"{type(error).__name__}: {error}"]),
                      flags=[Flag.make("GRADER_FAILED", "The grader could not produce a suggestion.")])


AI_REVIEW_MESSAGE = "Worth a look: see the quoted evidence and note."  # placeholder until Jorge's 3.5 wording
AI_DROPPED_NOTE = "A possible concern was raised without evidence that could be verified, so it is not flagged."


def apply_ai_usage_rule(suggestion: Suggestion) -> None:
    """review only with at least one verified evidence item (run after verify)."""
    ai = suggestion.ai_usage
    if ai.status != "review":
        return
    if any(ev.verified for ev in ai.evidence):
        suggestion.flags.append(Flag.make("AI_USAGE_REVIEW", AI_REVIEW_MESSAGE))
    else:
        ai.status, ai.note = "no_concern", AI_DROPPED_NOTE


def grade(client, team_id: str, rubric: dict, transcript: dict | None, notebook: dict | None,
          model: str = MODEL, redact_names: bool = True, ai_policy: str | None = None) -> Suggestion:
    names = [n["name"] for n in (notebook or {}).get("names", [])]
    base = dict(team_id=team_id, produced_by=PRODUCED_BY, model=model, prompt_version=PROMPT_VERSION,
                rubric_version=str(rubric.get("rubric_version", "unknown")),
                names_sent_to_model=bool(names) and not redact_names)
    try:
        cells = (notebook or {}).get("cells", [])
        if redact_names:
            cells = _redact(cells, names)
        segments = transcript.get("segments") if transcript and transcript.get("status") == "ok" else None
        resp = client.messages.create(
            model=model,
            max_tokens=8000,
            system=build_system_prompt(rubric, ai_policy),
            tools=[TOOL],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": build_user_message(segments, cells)}],
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        raw = json.loads(block.input) if isinstance(block.input, str) else block.input
        model_out = ModelOutput.model_validate(raw)
        sections, errors, in_range = check_sections(model_out, rubric)
    except Exception as e:  # any failure becomes a failed suggestion, never a number
        return _failed(base, e)

    suggestion = Suggestion(
        **base,
        status="needs_manual" if errors else "ok",
        sections=sections,
        total=sum(s.score for s in sections),  # computed here, never taken from the model
        ai_usage=AiUsage(status=model_out.ai_usage.status, note=model_out.ai_usage.note,
                         evidence=[Evidence(**e.model_dump()) for e in model_out.ai_usage.evidence]),
        validation=Validation(scores_in_range=in_range, errors=errors),
        flags=find_injections(transcript, notebook),
    )
    verify(suggestion, transcript, notebook)
    apply_ai_usage_rule(suggestion)
    return suggestion


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def grade_bundle(client, bundle_dir: Path, rubric_path: Path, out_path: Path | None = None,
                 model: str = MODEL) -> Suggestion:
    team_id = bundle_dir.name
    try:
        rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
        suggestion = grade(client, team_id, rubric, _load(bundle_dir / "transcript.json"),
                           _load(bundle_dir / "notebook_cells.json"), model)
    except Exception as e:
        suggestion = _failed(dict(team_id=team_id, produced_by=PRODUCED_BY, model=model,
                                  prompt_version=PROMPT_VERSION, rubric_version="unknown",
                                  names_sent_to_model=False), e)
    out = out_path or bundle_dir / "suggestion.json"
    out.write_text(suggestion.model_dump_json(indent=2), encoding="utf-8")
    return suggestion


def main() -> None:
    import anthropic
    from dotenv import load_dotenv

    load_dotenv()  # reads ANTHROPIC_API_KEY from a local .env

    p = argparse.ArgumentParser()
    p.add_argument("bundle_dir", type=Path)
    p.add_argument("rubric", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--model", default=MODEL)
    a = p.parse_args()
    s = grade_bundle(anthropic.Anthropic(), a.bundle_dir, a.rubric, a.out, a.model)
    print(f"{s.team_id}: status={s.status} total={s.total} "
          f"quotes {s.validation.quotes_verified}/{s.validation.quotes_checked} verified")
    for err in s.validation.errors:
        print(f"  error: {err}")


if __name__ == "__main__":
    main()
