"""Parser hardening (task 2.7): oversized, malformed and odd-looking notebooks.

Every notebook here is built inside the test. None of these may crash the parser or
produce a notebook_cells.json that cannot be written.
"""
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from easygrade.pipeline.notebook.config import load_config
from easygrade.pipeline.notebook.models import NotebookCells
from easygrade.pipeline.notebook.names import extract_names
from easygrade.pipeline.notebook.parse import parse_notebook, write_notebook_cells

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"


def md(source):
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code(source, outputs=None, count=1):
    return {"cell_type": "code", "metadata": {}, "execution_count": count, "source": source,
            "outputs": outputs or []}


def stream(text):
    return {"output_type": "stream", "name": "stdout", "text": text}


def image(payload, mime="image/png"):
    return {"output_type": "display_data", "metadata": {}, "data": {mime: payload}}


def small_config(**limits):
    data = load_config().model_dump()
    data.update(limits)
    return type(load_config()).model_validate(data)


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def write(self, cells, name="Rivera_Chen_FinalProject.ipynb", encoding="utf-8", ascii_only=False,
              prefix=b""):
        nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": cells}
        path = self.dir / name
        path.write_bytes(prefix + json.dumps(nb, ensure_ascii=ascii_only).encode(encoding))
        return path

    def parse(self, path, config=None):
        res = parse_notebook(path, "team-1", self.dir / "out", config)
        out = write_notebook_cells(res, self.dir / "out")  # must be writable as UTF-8 JSON
        NotebookCells.model_validate(json.loads(out.read_text(encoding="utf-8")))
        return res

    def codes(self, res):
        return [f.code for f in res.flags]

    def test_huge_output_is_truncated(self):
        res = self.parse(self.write([code("1", [stream("x" * 5_000_000)])]))
        text = res.cells[0].outputs[0].text
        self.assertLess(len(text), 2100)
        self.assertIn("truncated", text)

    def test_huge_source_is_truncated_and_not_syntax_checked(self):
        res = self.parse(self.write([code("x = 1\n" * 100_000)]))
        self.assertLess(len(res.cells[0].source), 20100)
        self.assertIsNone(res.cells[0].syntax_ok)  # too large to check cheaply

    def test_moderately_long_source_is_still_syntax_checked(self):
        res = self.parse(self.write([code("x = 1\n" * 5000 + "def f(:\n")]))
        self.assertIs(res.cells[0].syntax_ok, False)

    def test_image_limits(self):
        payload = base64.b64encode(PNG).decode()
        cells = [code("1", [image(payload)], count=i + 1) for i in range(5)]
        res = self.parse(self.write(cells), small_config(max_images=3))
        self.assertEqual(len(res.images), 3)
        skipped = [o.text for c in res.cells for o in c.outputs if o.kind == "text"]
        self.assertEqual(len(skipped), 2)
        self.assertIn("limit of 3 images", skipped[0])
        for img in res.images:
            self.assertTrue((self.dir / "out" / img.path).is_file())

    def test_oversized_image_skipped_without_decoding(self):
        payload = base64.b64encode(PNG + b"0" * 5000).decode()
        res = self.parse(self.write([code("1", [image(payload)])]), small_config(max_image_bytes=1000))
        self.assertEqual(res.images, [])
        self.assertIn("size limit", res.cells[0].outputs[0].text)

    def test_corrupt_images_are_reported_not_dropped(self):
        for payload, label in (("!!!not base64???", "corrupt"), (base64.b64encode(b"plain text").decode(), "not-image")):
            with self.subTest(label):
                res = self.parse(self.write([code("1", [image(payload)])]))
                self.assertEqual(res.images, [])
                self.assertIn("not saved", res.cells[0].outputs[0].text)

    def test_jpeg_images_are_kept(self):
        payload = base64.b64encode(b"\xff\xd8\xff\xe0jpeg").decode()
        res = self.parse(self.write([code("1", [image(payload, "image/jpeg")])]))
        self.assertEqual(res.images[0].mime, "image/jpeg")

    def test_lone_surrogate_does_not_crash(self):
        res = self.parse(self.write([md("**Students:** Al\ud800ex Rivera")], ascii_only=True))
        self.assertTrue(res.cells)

    def test_latin1_notebook_is_read(self):
        res = self.parse(self.write([md("**Students:** José Núñez")], encoding="cp1252"))
        self.assertNotIn("NOTEBOOK_UNREADABLE", self.codes(res))
        self.assertEqual(res.names[0].name, "José Núñez")

    def test_utf8_bom_notebook_is_read(self):
        res = self.parse(self.write([md("**Students:** Ana Rivera")], prefix=b"\xef\xbb\xbf"))
        self.assertNotIn("NOTEBOOK_UNREADABLE", self.codes(res))
        self.assertEqual([n.name for n in res.names], ["Ana Rivera"])

    def test_oversized_notebook_refused(self):
        res = self.parse(self.write([md("x" * 5000)]), small_config(max_notebook_bytes=1000))
        self.assertEqual(self.codes(res), ["NOTEBOOK_UNREADABLE"])

    def test_not_json_and_wrong_json_are_unreadable(self):
        for content in (b"", b"{ nope", b"[1, 2, 3]", b'{"cells": "oops"}', b"\x00\x01\x02"):
            with self.subTest(content=content):
                path = self.dir / "bad.ipynb"
                path.write_bytes(content)
                self.assertEqual(self.codes(self.parse(path)), ["NOTEBOOK_UNREADABLE"])

    def test_terminal_noise_is_cleaned(self):
        res = self.parse(self.write([code("1", [stream("\x1b[31mred\x1b[0m\nprogress 10%\rprogress 100%")])]))
        self.assertEqual(res.cells[0].outputs[0].text, "red\nprogress 100%")

    def test_missing_header_cell(self):
        res = self.parse(self.write([code("import pandas as pd")]))
        self.assertIn("NAME_NOT_FOUND", self.codes(res))
        self.assertIn("HEADER_RULES", self.codes(res))

    def test_header_cell_beyond_the_end(self):
        data = load_config().model_dump()
        data["name_rules"]["header_cell_index"] = 9
        res = self.parse(self.write([md("**Students:** Ana Rivera")]), type(load_config()).model_validate(data))
        self.assertIn("NAME_NOT_FOUND", self.codes(res))

    def test_cell_with_missing_fields(self):
        res = self.parse(self.write([{"cell_type": "code", "metadata": {}}, {"cell_type": "markdown", "metadata": {}}]))
        self.assertEqual(len(res.cells), 2)

    def test_many_cells(self):
        res = self.parse(self.write([code("x = 1", count=i + 1) for i in range(3000)]))
        self.assertEqual(len(res.cells), 3000)
        self.assertTrue(res.checks.execution_order.strictly_increasing)


class OddNameTests(unittest.TestCase):
    def names(self, text):
        return [n.name for n in extract_names(text, 0, load_config())]

    def test_last_first_with_semicolons(self):
        self.assertEqual(self.names("Students: Rivera, Ana; Chen, Marcus"), ["Rivera, Ana", "Chen, Marcus"])

    def test_suffix_and_initials_keep_their_dots(self):
        self.assertEqual(self.names("Students: Ana Rivera Jr., J. Smith"), ["Ana Rivera Jr.", "J. Smith"])

    def test_accents_hyphens_apostrophes_particles(self):
        self.assertEqual(
            self.names("Students: María de la Cruz, Seán O'Neil-Garcia"),
            ["María de la Cruz", "Seán O'Neil-Garcia"],
        )

    def test_markdown_links_and_html_tags(self):
        self.assertEqual(self.names("**Students:** [Ana Rivera](mailto:a@x.com), Sam Chen"), ["Ana Rivera", "Sam Chen"])
        self.assertEqual(self.names("<b>Students:</b> Ana Rivera and Sam Chen"), ["Ana Rivera", "Sam Chen"])

    def test_sentences_and_junk_are_not_names(self):
        for text in ("Students: writing code. in cells", "Students: see https://example.com/a",
                     "Students: TODO: fill in", "Students: 12345", "Students: a, b, c, d, e, f, g, h"):
            with self.subTest(text):
                self.assertEqual(self.names(text), [])

    def test_at_most_max_names(self):
        text = "Students: " + ", ".join(f"Name{chr(65 + i)} Last" for i in range(10))
        self.assertLessEqual(len(self.names(text)), load_config().name_rules.max_names)


if __name__ == "__main__":
    unittest.main()
