"""Build the chart-reading test set (task 2.4) from batch A, through the real parser.

Run from the repo root:   python easygrade/fixtures/make_chart_set.py
Writes easygrade/fixtures/charts/*.png and charts_truth.csv.

The chart images are the ones the parser extracts from the fake notebooks, so the set tests the same path the
grader will use. The truth columns come from how make_batch_a.py draws each chart, not from anyone's opinion:
  excellent viz -> title, both axis labels (line chart also has a legend)
  good viz      -> title only for the line chart; title and x label for the bar chart
  legend_ok is True for every single-series chart (no legend needed), as in chart_check.py's definition
  needs_work    -> no title, no axis labels
charts_truth.csv has Diego's columns (see easygrade/eval/chart_check.py): fill the model's answers with
`chart_check judge`, then `compare` uses the human_* columns below.
"""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from easygrade.pipeline.notebook.config import load_config  # noqa: E402
from easygrade.pipeline.notebook.parse import parse_notebook  # noqa: E402

FIXTURES = Path(__file__).resolve().parent
OUT = FIXTURES / "charts"
CHECKS = ["has_title", "x_axis_labeled", "y_axis_labeled", "legend_ok"]

# (team, which image in the notebook, name, truth). Image 0 is the Q2 bar chart, image 1 the Q3 line chart.
SET = [
    ("team-001", 0, "excellent_bar", dict(has_title=True, x_axis_labeled=True, y_axis_labeled=True, legend_ok=True)),
    ("team-001", 1, "excellent_line", dict(has_title=True, x_axis_labeled=True, y_axis_labeled=True, legend_ok=True)),
    ("team-003", 0, "good_bar", dict(has_title=True, x_axis_labeled=True, y_axis_labeled=False, legend_ok=True)),
    ("team-003", 1, "good_line", dict(has_title=True, x_axis_labeled=False, y_axis_labeled=False, legend_ok=True)),
    ("team-006", 0, "poor_bar", dict(has_title=False, x_axis_labeled=False, y_axis_labeled=False, legend_ok=True)),
]


def main():
    data = load_config().model_dump()
    data["filename_pattern"] = r"^.+\.ipynb$"
    config = type(load_config()).model_validate(data)
    OUT.mkdir(exist_ok=True)
    rows = []
    for team, which, name, truth in SET:
        with tempfile.TemporaryDirectory() as tmp:
            res = parse_notebook(FIXTURES / "batch_a" / team / "final.ipynb", team, tmp, config)
            src = Path(tmp) / res.images[which].path
            dest = OUT / f"{team}_{name}.png"
            shutil.copyfile(src, dest)
        rows.append({"image": dest.name, **{c: "" for c in CHECKS}, "title_text": "", "notes": "",
                     **{f"human_{c}": str(truth[c]).lower() for c in CHECKS}})
    with (OUT / "charts_truth.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["image", *CHECKS, "title_text", "notes", *(f"human_{c}" for c in CHECKS)],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} charts to {OUT}")


if __name__ == "__main__":
    main()
