"""Run with:  python -m unittest discover tests"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from easygrade.pipeline.notebook.config import AssignmentConfig, load_config
from easygrade.pipeline.notebook.models import FLAG_REGISTRY, NotebookCells, make_flag

DRAFT = Path(__file__).resolve().parents[1] / "easygrade" / "contracts_draft"


def _load(name):
    return json.loads((DRAFT / name).read_text(encoding="utf-8"))


class ModelTests(unittest.TestCase):
    def test_valid_example_validates(self):
        nb = NotebookCells.model_validate(_load("notebook_cells.valid.example.json"))
        self.assertEqual(nb.team_id, "team-001")
        self.assertEqual(len(nb.cells), 3)
        self.assertIsNone(nb.cells[0].syntax_ok)

    def test_invalid_example_fails(self):
        with self.assertRaises(ValidationError):
            NotebookCells.model_validate(_load("notebook_cells.invalid.example.json"))

    def test_unknown_fields_ignored(self):
        data = _load("notebook_cells.valid.example.json")
        data["cells"][1]["brand_new"] = 1
        data["checks"]["execution_order"]["extra"] = True
        nb = NotebookCells.model_validate(data)
        self.assertFalse(hasattr(nb, "future_field"))
        self.assertFalse(hasattr(nb.cells[1], "brand_new"))

    def test_bad_severity_rejected(self):
        data = copy.deepcopy(_load("notebook_cells.valid.example.json"))
        data["flags"] = [{"code": "X", "message": "m", "severity": "fatal"}]
        with self.assertRaises(ValidationError):
            NotebookCells.model_validate(data)

    def test_schema_file_matches_model(self):
        schema = json.loads((DRAFT / "notebook_cells.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema, NotebookCells.model_json_schema())

    def test_flag_registry(self):
        self.assertEqual(
            set(FLAG_REGISTRY),
            {"NOTEBOOK_EMPTY", "NOTEBOOK_UNREADABLE", "NAME_NOT_FOUND", "HEADER_RULES",
             "FILENAME_RULES", "EXEC_ORDER", "ERROR_OUTPUT"},
        )
        f = make_flag("NOTEBOOK_EMPTY")
        self.assertEqual(f.severity, "block")
        self.assertEqual(make_flag("EXEC_ORDER", "custom").message, "custom")


class ConfigTests(unittest.TestCase):
    def test_default_config_loads(self):
        cfg = load_config()
        self.assertEqual(cfg.header_rules.required_fields, ["names"])
        self.assertGreaterEqual(len(cfg.name_rules.patterns), 4)

    def test_invalid_regex_rejected(self):
        data = json.loads(json.dumps(load_config().model_dump()))
        data["filename_pattern"] = "(unclosed"
        with self.assertRaises(ValidationError):
            AssignmentConfig.model_validate(data)

    def test_required_field_needs_pattern(self):
        data = load_config().model_dump()
        data["header_rules"]["required_fields"] = ["names", "section"]
        with self.assertRaises(ValidationError):
            AssignmentConfig.model_validate(data)

    def test_unknown_config_keys_ignored(self):
        data = load_config().model_dump()
        data["redact_names"] = True
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(load_config(p).max_output_chars, 2000)


if __name__ == "__main__":
    unittest.main()
