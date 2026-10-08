"""Generate batch A: 10 FAKE final projects (notebook + transcript) and the answer key.

Run from the repo root:   python easygrade/fixtures/make_batch_a.py
Needs: nbformat, matplotlib (used only here, to draw the charts saved inside the notebooks).

Everything is invented: the dataset (Miami-Dade restaurant inspections), the students and the
numbers. Notebooks are written, never executed; their outputs are typed in, the way a saved
notebook looks after a run. Output is deterministic, so rerunning gives identical files.

Writes easygrade/fixtures/batch_a/team-001 .. team-010 (final.ipynb, transcript.json) and
easygrade/eval/answer_key.json. Three of the teams are seeded failures (see SEEDED below).
"""
from __future__ import annotations

import base64
import io
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import nbformat  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "easygrade" / "fixtures" / "batch_a"
KEY_PATH = ROOT / "easygrade" / "eval" / "answer_key.json"

SECTIONS = ["data_cleaning", "analysis_viz", "interpretation", "code_quality", "presentation", "collaboration"]
LEVELS = ["excellent", "good", "needs_work"]  # best to worst
CUISINES = ["Cuban", "Haitian", "Italian", "Seafood", "Mexican", "Peruvian", "Chinese", "Steakhouse"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

E, G, N = "excellent", "good", "needs_work"

# One entry per team. levels = what a careful professor would give. quirks drive the notebook.
TEAMS = [
    dict(id="team-001", names=("Isabel Moreno", "Daniel Park"),
         levels=dict(data_cleaning=E, analysis_viz=E, interpretation=E, code_quality=E, presentation=E, collaboration=E),
         quirks=[]),
    dict(id="team-002", names=("Camila Reyes", "Omar Haddad"),
         levels=dict(data_cleaning=E, analysis_viz=E, interpretation=G, code_quality=E, presentation=G, collaboration=E),
         quirks=[]),
    dict(id="team-003", names=("Nadia Petrov", "Elijah Brooks"),
         levels=dict(data_cleaning=G, analysis_viz=G, interpretation=G, code_quality=G, presentation=G, collaboration=G),
         quirks=["leftover_cell"]),
    dict(id="team-004", names=("Tomas Ibarra", "Grace Okoye"),
         levels=dict(data_cleaning=G, analysis_viz=G, interpretation=G, code_quality=N, presentation=G, collaboration=G),
         quirks=["out_of_order"],
         seeded=[dict(problem="cells run out of order", flag="EXEC_ORDER")]),
    dict(id="team-005", names=("Layla Haddad", "Victor Salazar"),
         levels=dict(data_cleaning=E, analysis_viz=G, interpretation=N, code_quality=G, presentation=G, collaboration=G),
         quirks=["no_summaries"]),
    dict(id="team-006", names=("Marco Bianchi", "Sofia Duarte"),
         levels=dict(data_cleaning=N, analysis_viz=N, interpretation=N, code_quality=N, presentation=G, collaboration=G),
         quirks=["error_cell", "out_of_order", "no_q3_q4"],
         seeded=[dict(problem="a cell stops with an error", flag="ERROR_OUTPUT"),
                 dict(problem="cells run out of order", flag="EXEC_ORDER")]),
    dict(id="team-007", names=("Hannah Weiss", "Kwame Mensah"),
         levels=dict(data_cleaning=G, analysis_viz=E, interpretation=G, code_quality=G, presentation=N, collaboration=G),
         quirks=["one_speaker"]),
    dict(id="team-008", names=("Rafael Costa", "Mei Tanaka"),
         levels=dict(data_cleaning=None, analysis_viz=None, interpretation=None, code_quality=None, presentation=G,
                     collaboration=None),
         quirks=["no_notebook"],
         seeded=[dict(problem="no notebook submitted", flag="NOTEBOOK_MISSING")]),
    dict(id="team-009", names=("Aaliyah Grant", "Leandro Ferreira"),
         levels=dict(data_cleaning=N, analysis_viz=N, interpretation=N, code_quality=N, presentation=G, collaboration=N),
         quirks=["empty_notebook"],
         seeded=[dict(problem="empty notebook", flag="NOTEBOOK_EMPTY")]),
    dict(id="team-010", names=("Priscilla Ng", "Jonas Lindqvist"),
         levels=dict(data_cleaning=G, analysis_viz=G, interpretation=E, code_quality=G, presentation=G, collaboration=N),
         quirks=["no_names"],
         seeded=[dict(problem="no student names in the header", flag="NAME_NOT_FOUND")]),
]


# ---------------------------------------------------------------- charts
def png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=60)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def chart_bar(rng, level):
    zips = sorted(rng.sample(range(33010, 33190), 10))
    rates = sorted((round(rng.uniform(0.06, 0.24), 3) for _ in zips), reverse=True)
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.bar([str(z) for z in zips], rates, color="#2f6f9f")
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    if level == E:
        ax.set_title("Fail rate by ZIP code (top 10)")
        ax.set_xlabel("ZIP code")
        ax.set_ylabel("Share of inspections that failed")
    elif level == G:
        ax.set_title("Top 10 ZIP codes by fail rate")  # y axis unlabeled
        ax.set_xlabel("ZIP code")
    fig.tight_layout()
    return png(fig), zips, rates


def chart_line(rng, level):
    base = rng.uniform(84, 90)
    avg = [round(base + rng.uniform(-3, 3), 2) for _ in range(12)]
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.plot(MONTHS, avg, marker="o", color="#b5523b", label="Average score")
    if level == E:
        ax.set_title("Average inspection score by month, 2025")
        ax.set_xlabel("Month")
        ax.set_ylabel("Average score (0-100)")
        ax.legend()
    elif level == G:
        ax.set_title("Average score per month")
    fig.tight_layout()
    return png(fig), avg


def img_output(data):
    return nbformat.v4.new_output("display_data", data={"image/png": data, "text/plain": "<Figure size 360x204>"})


def text_output(text):
    return nbformat.v4.new_output("stream", name="stdout", text=text)


def table_output(text):
    return nbformat.v4.new_output("execute_result", data={"text/plain": text}, execution_count=None)


# ---------------------------------------------------------------- notebook
class Book:
    def __init__(self, team_id):
        self.cells = []
        self.team_id = team_id

    def _add(self, cell):
        cell["id"] = f"{self.team_id}-c{len(self.cells):03d}"  # fixed ids keep the output reproducible
        self.cells.append(cell)

    def md(self, text):
        self._add(nbformat.v4.new_markdown_cell(text))

    def code(self, source, outputs=()):
        cell = nbformat.v4.new_code_cell(source)
        cell.outputs = list(outputs)
        self._add(cell)

    def number(self, order_quirk, rng):
        counts = list(range(1, sum(c.cell_type == "code" for c in self.cells) + 1))
        if order_quirk and len(counts) >= 3:
            i = rng.randrange(0, len(counts) - 2)
            counts[i], counts[i + 2] = counts[i + 2], counts[i]  # two cells were re-run out of order
        it = iter(counts)
        for c in self.cells:
            if c.cell_type == "code":
                c.execution_count = next(it)
                for o in c.outputs:
                    if o.output_type == "execute_result":
                        o.execution_count = c.execution_count


def header(team, level_collab, quirks):
    if "no_names" in quirks:
        return "**Section:** A\n**Date:** May 3, 2026\n**Responsibilities:** We split the work evenly."
    a, b = team["names"]
    lines = [f"**Students:** {a}, {b}", "**Section:** A", "**Date:** May 3, 2026"]
    if "lopsided" in quirks:  # only one partner is credited with any work
        lines.append(f"**Responsibilities:** {a}: Q1 to Q4, all charts and the written summaries.")
    elif level_collab == E:
        lines.append(f"**Responsibilities:** {a}: Q1 cleaning, Q3 monthly trend, written summaries. "
                     f"{b}: Q2 ZIP code chart, Q4 cuisine table, chart formatting. Both: presentation.")
    elif level_collab == G:
        lines.append("**Responsibilities:** We shared the work and both presented.")
    return "\n".join(lines)


def build_notebook(team, rng):
    lv, qk = team["levels"], team["quirks"]
    a, b = team["names"]
    book = Book(team["id"])
    n_raw = rng.randrange(5000, 5400)
    n_miss = rng.randrange(25, 70)
    n_dup = rng.randrange(12, 40)
    n_final = n_raw - n_miss - n_dup
    cq = lv["code_quality"]

    book.md(header(team, lv["collaboration"], qk))
    if cq != N:
        book.md("# CAP3321C Final Project: Miami-Dade Restaurant Inspections")
    book.code("import pandas as pd\nimport matplotlib.pyplot as plt\n"
              if cq != N else "import pandas as pd, matplotlib.pyplot as plt")

    # ---- Q1 cleaning
    if cq != N:
        book.md("## Q1. Cleaning")
    book.code("df = pd.read_csv('mdc_restaurant_inspections_2025.csv')\nprint(df.shape)",
              [text_output(f"({n_raw}, 8)\n")])
    c = lv["data_cleaning"]
    if c == E:
        book.code("df.isna().sum()", [table_output(
            f"inspection_id     0\nrestaurant_name   0\nzip_code          0\ninspection_date   0\n"
            f"cuisine          {rng.randrange(8, 20)}\nscore            {n_miss}\nviolations        0\nresult            0\ndtype: int64")])
        book.md(f"`score` is what the whole project measures, so the {n_miss} inspections without a score cannot be "
                "imputed honestly. We dropped them. Missing `cuisine` values were kept and labeled 'Unknown' so we "
                "do not lose inspections for Q2 and Q3.")
        book.code("df = df.dropna(subset=['score'])\ndf['cuisine'] = df['cuisine'].fillna('Unknown')\nprint(len(df))",
                  [text_output(f"{n_raw - n_miss}\n")])
        book.code("df['inspection_date'] = pd.to_datetime(df['inspection_date'])\n"
                  "df['score'] = pd.to_numeric(df['score'])\ndf['violations'] = pd.to_numeric(df['violations'])\n"
                  "df['zip_code'] = df['zip_code'].astype(str).str.zfill(5)\nprint(df.dtypes)",
                  [text_output("inspection_id                int64\nrestaurant_name              object\n"
                               "zip_code                     object\ninspection_date      datetime64[ns]\n"
                               "cuisine                      object\nscore                       float64\n"
                               "violations                    int64\nresult                       object\n")])
        book.md("ZIP codes were stored as numbers, which drops leading zeros and breaks grouping, so we converted "
                "them to 5-character strings. Dates became real dates so Q3 can group by month.")
        book.code("df = df.drop_duplicates(subset='inspection_id')\nprint(len(df))", [text_output(f"{n_final}\n")])
        book.md(f"After removing {n_dup} duplicate inspection ids, **{n_final:,}** inspections remain.")
    elif c == G:
        book.code("df.isna().sum()", [table_output(
            f"zip_code 0\ninspection_date 0\ncuisine {rng.randrange(8, 20)}\nscore {n_miss}\ndtype: int64")])
        book.md(f"There are {n_miss} missing scores. We dropped them.")
        book.code("df = df.dropna(subset=['score'])\ndf['inspection_date'] = pd.to_datetime(df['inspection_date'])\n"
                  "df = df.drop_duplicates(subset='inspection_id')\nprint(len(df))", [text_output(f"{n_final}\n")])
        book.md(f"Dates are converted and duplicates are removed, leaving {n_final:,} inspections. "
                "(zip_code is still a number.)")
    else:
        book.code("df = df.dropna()\nprint(len(df))", [text_output(f"{n_raw - n_miss * 3}\n")])
        if "error_cell" in qk:
            book.code("clean = df_raw[df_raw['score'] > 0]",
                      [nbformat.v4.new_output("error", ename="NameError", evalue="name 'df_raw' is not defined",
                                              traceback=["NameError: name 'df_raw' is not defined"])])

    if "leftover_cell" in qk or cq == G:
        book.code("tmp = df.copy()")  # never used again
    # ---- Q2
    if cq != N:
        book.md("## Q2. Fail rate by ZIP code")
    data, zips, rates = chart_bar(rng, lv["analysis_viz"])
    comment = "# share of inspections with result == 'Fail', per ZIP" if cq == E else ""
    book.code(f"{comment}\nfail_rate = df.assign(fail=df['result'] == 'Fail').groupby('zip_code')['fail'].mean()\n"
              "top10 = fail_rate.sort_values(ascending=False).head(10)\ntop10.plot(kind='bar')\nplt.show()".strip(),
              [img_output(data)])
    top_zip, top_rate = zips[0], rates[0]
    if lv["interpretation"] == E:
        book.md(f"ZIP code {top_zip} has the highest fail rate at {top_rate:.1%}, about twice the county-wide rate. "
                "The top ZIP codes are spread across the county rather than clustered, which suggests the "
                "cause is individual restaurants, not one neighborhood.")
    elif lv["interpretation"] == G:
        book.md(f"ZIP code {top_zip} has the highest fail rate ({top_rate:.1%}). The other ZIP codes are lower.")
    elif "no_summaries" not in qk:
        book.md("The chart shows the results.")

    # ---- Q3
    if "no_q3_q4" not in qk:
        if cq != N:
            book.md("## Q3. Scores over time")
        data, avg = chart_line(rng, lv["analysis_viz"])
        book.code("monthly = df.groupby(df['inspection_date'].dt.month)['score'].mean()\nmonthly.plot(marker='o')\nplt.show()",
                  [img_output(data)])
        lo = MONTHS[avg.index(min(avg))]
        hi = MONTHS[avg.index(max(avg))]
        if lv["interpretation"] == E:
            book.md(f"Average scores peak in {hi} ({max(avg):.1f}) and are lowest in {lo} ({min(avg):.1f}). The swing "
                    "is only a few points, so there is no strong seasonal effect, but the dip in "
                    f"{lo} lines up with the summer months when kitchens run hotter and busier.")
        elif lv["interpretation"] == G:
            book.md(f"The average score is highest in {hi} and lowest in {lo}.")

        # ---- Q4
        if cq != N:
            book.md("## Q4. Violations by cuisine")
        picks = rng.sample(CUISINES, 4)
        vals = sorted((round(rng.uniform(1.8, 4.6), 2) for _ in picks), reverse=True)
        table = "cuisine   violations_per_inspection\n" + "\n".join(f"{c:<10}{v}" for c, v in zip(picks, vals))
        book.code("per = df.groupby('cuisine')['violations'].mean().sort_values(ascending=False)\nper.head(4)",
                  [table_output(table)])
        if lv["interpretation"] == E:
            book.md(f"{picks[0]} restaurants average {vals[0]} violations per inspection, nearly "
                    f"{vals[0] / vals[-1]:.1f} times {picks[-1]}. Cuisines with more cooking steps and more "
                    "ingredient handling have more chances to be cited, so this is likely about process, not quality.")
        elif lv["interpretation"] == G:
            book.md(f"{picks[0]} has the most violations per inspection ({vals[0]}), and {picks[-1]} the fewest ({vals[-1]}).")
    return book, n_final


def build_transcript(team, rng):
    a, b = team["names"]
    a1, b1 = a.split()[0], b.split()[0]
    lv, qk = team["levels"]["presentation"], team["quirks"]
    if lv == E:
        lines = [
            f"Hi, I'm {a1}, and this is {b1}. Our project looks at Miami-Dade restaurant inspections from 2025.",
            f"I'll start with cleaning. We dropped inspections with no score because the score is what we measure, and we converted ZIP codes to strings so leading zeros are not lost.",
            "After removing duplicates we kept about five thousand inspections.",
            f"Now {b1} will walk through the charts.",
            f"Thanks {a1}. In our bar chart of fail rate by ZIP code, the highest ZIP code fails about twice as often as the county average, and the top ZIPs are spread out, so it looks like a restaurant problem, not a neighborhood problem.",
            "The line chart shows the monthly average score. It only moves a few points, with the lowest month in the summer.",
            f"{a1}: For cuisines, the table shows the cuisine with the most violations per inspection is several times higher than the lowest one, which we think reflects how many handling steps the food needs.",
            f"{b1}: To wrap up, cleaning choices mattered most, and the results point to individual restaurants rather than areas. Thank you.",
        ]
    elif lv == G and "one_speaker" not in qk:
        lines = [
            f"Hello, I'm {a1} and this is {b1}. We analyzed restaurant inspections.",
            "First we cleaned the data, we dropped missing scores and removed duplicates.",
            f"{b1} here. The bar chart shows the ZIP codes with the highest fail rates.",
            "The line chart is the average score by month, it goes up and down a little.",
            "For cuisines, one cuisine has the most violations. That is our main finding. Thank you.",
        ]
    else:  # one speaker, vague
        lines = [
            f"Hi this is {a1}. This is our final project about restaurant inspections.",
            "We did the cleaning and the charts and they look okay.",
            "The charts show the results of the questions. I think the results are what you would expect.",
            "That is it for the project. Thank you.",
        ]
    segments, t = [], 0.0
    for i, text in enumerate(lines, 1):
        dur = round(len(text.split()) / 2.6, 1)
        segments.append({"id": f"s{i}", "start_s": round(t, 1), "end_s": round(t + dur, 1), "text": text,
                         "confidence": round(rng.uniform(0.84, 0.96), 2), "speaker": None})
        t += dur
    return {
        "schema_version": "1", "team_id": team["id"], "produced_by": "fixture", "status": "ok", "language": "en",
        "duration_seconds": round(t, 1),
        "engine": {"name": "whisper", "model_size": "base", "local": True},
        "speaker_labels_available": False,
        "segments": segments, "low_confidence_segment_ids": [], "flags": [],
    }


def main(batch: Path = BATCH, key_path: Path = KEY_PATH):
    answer = {
        "description": "FAKE answer key for batch A (synthetic data, invented students). Used only by evals; never given to the model.",
        "level_keys": LEVELS,
        "rubric_note": "Levels follow the 200-point CAP3321C Final Project rubric. null = no grade expected.",
        "teams": {},
    }
    for idx, team in enumerate(TEAMS):
        rng = random.Random(1000 + idx)
        out = batch / team["id"]
        out.mkdir(parents=True, exist_ok=True)
        qk = team["quirks"]
        if "no_notebook" not in qk:
            if "empty_notebook" in qk:
                nb = nbformat.v4.new_notebook()
            else:
                book, _ = build_notebook(team, rng)
                book.number("out_of_order" in qk, rng)
                nb = nbformat.v4.new_notebook(cells=book.cells)
            nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
            nbformat.validate(nb)
            (out / "final.ipynb").write_bytes(nbformat.writes(nb).encode("utf-8") + b"\n")
        transcript = json.dumps(build_transcript(team, rng), indent=2) + "\n"
        (out / "transcript.json").write_bytes(transcript.encode("utf-8"))  # bytes: same output on every OS
        entry = {"students": list(team["names"]), "planned_levels": team["levels"],
                 "seeded_problems": team.get("seeded", [])}
        answer["teams"][team["id"]] = entry
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes((json.dumps(answer, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {len(TEAMS)} teams to {batch} and {key_path}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, help="write batch_a/ and answer_key.json here instead of the repo")
    a = ap.parse_args()
    if a.out:
        main(a.out / "batch_a", a.out / "answer_key.json")
    else:
        main()
