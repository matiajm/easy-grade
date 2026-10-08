"""Chart-reading test (task 2.4): can Claude judge a chart's title, axes and legend?

Step 1, ask Claude:
    python -m easygrade.eval.chart_check judge IMG [IMG ...] --out charts.csv
  Writes one row per image with Claude's answers and empty human_* columns.

Step 2, a person opens each image and fills in the human_* columns (true/false).

Step 3, compare:
    python -m easygrade.eval.chart_check compare charts.csv
  Prints agreement per check. Use it to decide whether chart quality is
  full, partial or none checkable, and log that in docs/DECISIONS.md.

Needs ANTHROPIC_API_KEY in the local environment for step 1. Fake charts only.
"""
import argparse
import base64
import csv
import mimetypes
from pathlib import Path

from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"
CHECKS = ["has_title", "x_axis_labeled", "y_axis_labeled", "legend_ok"]


class ChartJudgment(BaseModel):
    has_title: bool
    x_axis_labeled: bool
    y_axis_labeled: bool
    legend_ok: bool = Field(description="True if a legend is present when needed, or not needed (single series)")
    title_text: str = Field(description="The title as written, or empty")
    notes: str


TOOL = {
    "name": "judge_chart",
    "description": "Report what the chart shows for title, axes and legend.",
    "input_schema": ChartJudgment.model_json_schema(),
}

PROMPT = ("Look at this chart from a student notebook. Report only what is visible: is there a title, "
          "are the x and y axes labeled (not just tick values), and is a legend present where more than "
          "one series is plotted? Answer with the judge_chart tool.")


def judge(client, image: Path) -> ChartJudgment:
    media_type = mimetypes.guess_type(image.name)[0] or "image/png"
    data = base64.standard_b64encode(image.read_bytes()).decode()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[TOOL],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    block = next(b for b in resp.content if b.type == "tool_use")
    return ChartJudgment.model_validate(block.input)


def write_judgments(client, images: list[Path], out: Path) -> None:
    fields = ["image", *CHECKS, "title_text", "notes", *(f"human_{c}" for c in CHECKS)]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for img in images:
            j = judge(client, img)
            w.writerow({"image": img.name, **j.model_dump()})


def _bool(v: str) -> bool | None:
    v = (v or "").strip().lower()
    return True if v in ("true", "yes", "1") else False if v in ("false", "no", "0") else None


def compare(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """Per check: (agreements, rows where the human column is filled)."""
    out = {}
    for c in CHECKS:
        pairs = [(_bool(r[c]), _bool(r[f"human_{c}"])) for r in rows]
        pairs = [(m, h) for m, h in pairs if h is not None]
        out[c] = (sum(m == h for m, h in pairs), len(pairs))
    return out


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()  # reads ANTHROPIC_API_KEY from a local .env
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge")
    j.add_argument("images", nargs="+", type=Path)
    j.add_argument("--out", type=Path, default=Path("charts.csv"))
    c = sub.add_parser("compare")
    c.add_argument("csv", type=Path)
    a = p.parse_args()

    if a.cmd == "judge":
        import anthropic
        write_judgments(anthropic.Anthropic(), a.images, a.out)
        print(f"Wrote {a.out}. Fill in the human_* columns, then run compare.")
    else:
        with a.csv.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for check, (agree, n) in compare(rows).items():
            print(f"{check}: {agree}/{n} agree" if n else f"{check}: no human answers yet")


if __name__ == "__main__":
    main()
