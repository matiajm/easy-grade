from types import SimpleNamespace

from easygrade.pipeline.grader import smoke


def test_parses_tool_use_into_model():
    payload = {"level": "strong", "score": 27, "confidence": "high",
               "rationale": "Explains each choice.", "quote": "dropped because price is the target"}
    block = SimpleNamespace(type="tool_use", input=payload)
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[block])))
    grade = smoke.grade_section(client, smoke.FAKE_RUBRIC_SECTION, smoke.FAKE_NOTEBOOK_TEXT)
    assert grade.level == "strong" and grade.score == 27
