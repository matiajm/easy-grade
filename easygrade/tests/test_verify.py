import json
from pathlib import Path

from easygrade.pipeline.grader.models import Evidence, Section, Suggestion
from easygrade.pipeline.grader.verify import verify

BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "bundles" / "team-001"
TRANSCRIPT = json.loads((BUNDLE / "transcript.json").read_text())
NOTEBOOK = json.loads((BUNDLE / "notebook_cells.json").read_text())


def suggestion_with(*evidence):
    sec = Section(section_id="data_cleaning", level="strong", score=27, max_points=30,
                  confidence="high", rationale="fake", evidence=list(evidence))
    return Suggestion(team_id="team-001", produced_by="test", status="ok", model="fake",
                      prompt_version="t", rubric_version="t", names_sent_to_model=False, sections=[sec])


def codes(s):
    return [f.code for f in s.sections[0].flags]


def test_made_up_quote_fails():
    s = verify(suggestion_with(Evidence(source="notebook", ref=1, quote="we imputed with the median")),
               TRANSCRIPT, NOTEBOOK)
    assert s.sections[0].evidence[0].verified is False
    assert codes(s) == ["QUOTE_UNVERIFIED", "LOW_CONFIDENCE_SECTION"]


def test_real_quote_passes():
    s = verify(suggestion_with(Evidence(source="notebook", ref=1, quote="dropna(subset=['price'])")),
               TRANSCRIPT, NOTEBOOK)
    assert s.sections[0].evidence[0].verified is True
    assert codes(s) == []


def test_quote_pointing_to_wrong_cell_fails():
    s = verify(suggestion_with(Evidence(source="notebook", ref=2, quote="dropna(subset=['price'])")),
               TRANSCRIPT, NOTEBOOK)
    assert s.sections[0].evidence[0].verified is False
    assert "QUOTE_UNVERIFIED" in codes(s)


def test_spaces_and_curly_quotes_are_normalized():
    quote = "removed  houses above the\n99th percentile, since a few mansions"
    s = verify(suggestion_with(Evidence(source="transcript", ref="s2", quote=quote),
                               Evidence(source="notebook", ref=1, quote="dropna(subset=[‘price’])")),
               TRANSCRIPT, NOTEBOOK)
    assert [e.verified for e in s.sections[0].evidence] == [True, True]


def test_quote_in_cell_output_passes():
    s = verify(suggestion_with(Evidence(source="notebook", ref=1, quote="1457")), TRANSCRIPT, NOTEBOOK)
    assert s.sections[0].evidence[0].verified is True


def test_transcript_quote_fails_when_transcript_not_ok():
    s = verify(suggestion_with(Evidence(source="transcript", ref="s1", quote="price is what we are predicting")),
               {**TRANSCRIPT, "status": "failed"}, NOTEBOOK)
    assert s.sections[0].evidence[0].verified is False


def test_counts_filled_in():
    s = verify(suggestion_with(Evidence(source="notebook", ref=1, quote="dropna"),
                               Evidence(source="notebook", ref=1, quote="made up")),
               TRANSCRIPT, NOTEBOOK)
    assert (s.validation.quotes_checked, s.validation.quotes_verified) == (2, 1)
    assert codes(s) == ["QUOTE_UNVERIFIED"]  # one verified item, so no LOW_CONFIDENCE_SECTION
