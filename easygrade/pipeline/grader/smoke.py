"""Smoke test: grade one fake rubric section through Claude tool use into a Pydantic model.

Needs ANTHROPIC_API_KEY in the local environment (never committed).
Run: python -m easygrade.pipeline.grader.smoke
"""
import os
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-sonnet-5-5"

FAKE_RUBRIC_SECTION = """Section: Data Cleaning (max 30 points)
- Strong (24-30): handles missing values and outliers, explains each choice.
- Adequate (15-23): handles missing values, little explanation.
- Weak (0-14): no meaningful cleaning."""

FAKE_NOTEBOOK_TEXT = """# Cleaning
df = df.dropna(subset=['price'])  # 3 rows had no price, dropped because price is the target
df = df[df['price'] < df['price'].quantile(0.99)]  # removed extreme outliers above the 99th percentile"""


class SectionGrade(BaseModel):
    level: Literal["strong", "adequate", "weak"]
    score: int = Field(ge=0, le=30)
    confidence: Literal["low", "medium", "high"]
    rationale: str
    quote: str = Field(description="Exact quote from the notebook supporting the grade")


TOOL = {
    "name": "submit_grade",
    "description": "Submit the grade for one rubric section.",
    "input_schema": SectionGrade.model_json_schema(),
}


def grade_section(client: anthropic.Anthropic, rubric: str, notebook: str) -> SectionGrade:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[TOOL],
        tool_choice={"type": "auto"},
        messages=[{
            "role": "user",
            "content": f"Grade this notebook against the rubric section.\n\n<rubric>\n{rubric}\n</rubric>\n\n<notebook>\n{notebook}\n</notebook>",
        }],
    )
    block = next(b for b in resp.content if b.type == "tool_use")
    return SectionGrade.model_validate(block.input)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()  # reads ANTHROPIC_API_KEY from a local .env
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set in your environment.")
    grade = grade_section(anthropic.Anthropic(), FAKE_RUBRIC_SECTION, FAKE_NOTEBOOK_TEXT)
    print(grade.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
