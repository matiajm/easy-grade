import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "guard", Path(__file__).resolve().parents[2] / ".github/scripts/real_data_guard.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_guard_passes_on_fixtures(tmp_path):
    f = tmp_path / "easygrade/fixtures/fake.ipynb"
    f.parent.mkdir(parents=True)
    f.write_text("{}")
    assert guard.find_violations(tmp_path) == []


def test_guard_fails_on_planted_file(tmp_path):
    (tmp_path / "easygrade/pipeline").mkdir(parents=True)
    (tmp_path / "easygrade/pipeline/student.ipynb").write_text("{}")
    (tmp_path / "talk.mp4").write_text("x")
    assert guard.find_violations(tmp_path) == ["easygrade/pipeline/student.ipynb", "talk.mp4"]
