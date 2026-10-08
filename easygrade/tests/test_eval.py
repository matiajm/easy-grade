import json
from types import SimpleNamespace

from easygrade.eval import chart_check
from easygrade.eval.run_eval import evaluate, report

KEY = {
    "level_keys": ["excellent", "good", "needs_work"],
    "teams": {
        "team-001": {
            "planned_levels": {"cleaning": "excellent", "viz": "needs_work", "talk": "good"},
            "seeded_problems": [],
        },
        "team-002": {
            "planned_levels": {"cleaning": "good", "viz": None},
            "seeded_problems": [{"problem": "empty notebook", "flag": "NOTEBOOK_EMPTY"},
                                {"problem": "no name", "flag": "NAME_NOT_FOUND"}],
        },
    },
}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def suggestion(levels, version="grader-v1", flags=()):
    return {"prompt_version": version, "flags": [{"code": c} for c in flags],
            "sections": [{"section_id": s, "level": lv, "flags": []} for s, lv in levels.items()]}


def test_level_agreement_within_one_level(tmp_path):
    # team-001: cleaning exact, viz two levels off, talk one off (2/3); team-002: cleaning exact (1/1)
    write(tmp_path / "team-001/suggestion.json",
          suggestion({"cleaning": "excellent", "viz": "excellent", "talk": "needs_work"}))
    write(tmp_path / "team-002/suggestion.json", suggestion({"cleaning": "good"}))
    r = evaluate(tmp_path, KEY)
    assert (r.sections_agree, r.sections_total) == (3, 4)  # team-002 viz is null, skipped
    assert any("team-001/viz" in m for m in r.misses)


def test_failed_suggestion_counts_as_disagreement(tmp_path):
    write(tmp_path / "team-001/suggestion.json", {"prompt_version": "grader-v1", "status": "failed", "sections": []})
    r = evaluate(tmp_path, KEY)
    assert r.sections_ungraded == 4 and r.sections_agree == 0


def test_hard_failure_recall_reads_flags_from_any_bundle_file(tmp_path):
    write(tmp_path / "team-002/notebook_cells.json", {"flags": [{"code": "NOTEBOOK_EMPTY"}]})
    write(tmp_path / "team-002/suggestion.json", suggestion({"cleaning": "good"}, flags=["GRADER_FAILED"]))
    r = evaluate(tmp_path, KEY)
    assert (r.seeded_caught, r.seeded_total) == (1, 2)
    assert any("NAME_NOT_FOUND" in m for m in r.misses)


def test_report_prints_prompt_version_and_warns_on_mix(tmp_path):
    write(tmp_path / "team-001/suggestion.json", suggestion({}, version="grader-v1"))
    write(tmp_path / "team-002/suggestion.json", suggestion({}, version="grader-v2"))
    text = report(evaluate(tmp_path, KEY))
    assert "grader-v1, grader-v2" in text and "mixed versions" in text
    assert "Level agreement:" in text and "Hard-failure recall:" in text


def test_chart_judge_and_compare(tmp_path):
    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG fake")
    answer = {"has_title": True, "x_axis_labeled": True, "y_axis_labeled": False,
              "legend_ok": True, "title_text": "Prices", "notes": ""}
    block = SimpleNamespace(type="tool_use", input=answer)
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[block])))
    out = tmp_path / "charts.csv"
    chart_check.write_judgments(client, [img], out)

    import csv
    rows = list(csv.DictReader(out.open()))
    rows[0].update(human_has_title="true", human_x_axis_labeled="true", human_y_axis_labeled="true")
    result = chart_check.compare(rows)
    assert result["has_title"] == (1, 1)
    assert result["y_axis_labeled"] == (0, 1)
    assert result["legend_ok"] == (0, 0)  # human column left empty
