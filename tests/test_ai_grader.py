"""AI grader tests with a fake API (no network, no key, no cost).

Run with:  python -m unittest discover tests
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grader.ai_grader import (TOOL_NAME, AIConfig, AIError, AnthropicClient, build_request,
                              grade_notebook, make_scrubber)
from grader.cli import SAMPLES, build_demo_submissions
from grader.rubric import load_rubric
from desktop.api import SAMPLE_RUBRIC

RUBRIC = load_rubric(SAMPLE_RUBRIC)
NB = SAMPLES / "sample_project.ipynb"
NB_IDS = [c.id for c in RUBRIC.criteria if c.source == "notebook"]


def good_answer(**override):
    crit = {cid: {"score": RUBRIC.criterion(cid).levels[1].score, "reason": "ok", "evidence": ["cell 4"],
                  "confidence": 0.8} for cid in NB_IDS}
    crit.update(override)
    return {"criteria": crit, "feedback": "Nice charts. Check residuals.", "flags": []}


class FakeAPI:
    """Records requests and replies with the queued responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, headers, body, timeout):
        self.requests.append({"headers": headers, "body": json.loads(body)})
        status, data = self.responses.pop(0)
        return status, data, {}

    @staticmethod
    def tool(answer, tool_id="t1"):
        return 200, {"content": [{"type": "tool_use", "id": tool_id, "name": TOOL_NAME, "input": answer}],
                     "stop_reason": "tool_use", "usage": {"input_tokens": 1000, "output_tokens": 200}}


def client(fake):
    return AnthropicClient("sk-test", post=fake, sleep=lambda s: None)


class RequestTests(unittest.TestCase):
    def test_request_shape(self):
        payload, only, info = build_request(RUBRIC, NB, AIConfig(api_key="k"))
        self.assertEqual(only, NB_IDS)
        self.assertEqual(payload["tool_choice"], {"type": "tool", "name": TOOL_NAME})
        schema = payload["tools"][0]["input_schema"]["properties"]["criteria"]
        self.assertEqual(sorted(schema["required"]), sorted(NB_IDS))   # video criteria not included
        content = payload["messages"][0]["content"]
        self.assertTrue(any(b["type"] == "image" for b in content))
        text = "".join(b.get("text", "") for b in content)
        self.assertIn("### cell 7", text)
        self.assertNotIn("Video Matches Notebook", text)
        self.assertNotIn("explains_reasoning", text)
        self.assertEqual(info["images_sent"], 2)

    def test_no_images_option(self):
        payload, _, info = build_request(RUBRIC, NB, AIConfig(api_key="k", send_images=False))
        self.assertFalse(any(b["type"] == "image" for b in payload["messages"][0]["content"]))
        self.assertEqual(info["images_skipped"], 2)

    def test_scrubber(self):
        f = make_scrubber("Jamal Price", "4410123", "jamal.price@example.edu")
        out = f("By Jamal Price, Price, Jamal (jamal.price@example.edu) id 4410123. df['price'] Price ($)")
        self.assertNotIn("Jamal", out)
        self.assertNotIn("4410123", out)
        self.assertIn("df['price'] Price ($)", out)  # data columns untouched


class GradeTests(unittest.TestCase):
    def test_grades_and_headers(self):
        fake = FakeAPI(FakeAPI.tool(good_answer()))
        r = grade_notebook(RUBRIC, NB, AIConfig(api_key="sk-test"), client=client(fake))
        self.assertEqual(len(r.results), len(NB_IDS))
        self.assertEqual(r.usage, {"input_tokens": 1000, "output_tokens": 200})
        h = fake.requests[0]["headers"]
        self.assertEqual(h["x-api-key"], "sk-test")
        self.assertIn("anthropic-version", h)
        self.assertNotIn("sk-test", json.dumps(r.log))           # key never in the log
        self.assertNotIn("iVBOR", json.dumps(r.log))             # image data not in the log

    def test_retry_when_score_not_a_level(self):
        bad = good_answer(modeling={"score": 17, "reason": "x", "evidence": [], "confidence": 0.5})
        fake = FakeAPI(FakeAPI.tool(bad), FakeAPI.tool(good_answer()))
        r = grade_notebook(RUBRIC, NB, AIConfig(api_key="sk-test"), client=client(fake))
        self.assertEqual(r.log["attempts"], 2)
        second = fake.requests[1]["body"]["messages"]
        self.assertEqual(second[-1]["content"][0]["type"], "tool_result")
        self.assertTrue(second[-1]["content"][0]["is_error"])

    def test_gives_up_after_two_bad_answers(self):
        bad = good_answer(modeling={"score": 17, "reason": "x", "evidence": [], "confidence": 0.5})
        fake = FakeAPI(FakeAPI.tool(bad), FakeAPI.tool(bad))
        with self.assertRaises(AIError) as cm:
            grade_notebook(RUBRIC, NB, AIConfig(api_key="sk-test"), client=client(fake))
        self.assertIn("by hand", str(cm.exception))

    def test_model_that_cannot_force_tools(self):
        no_force = (400, {"error": {"message": 'tool_choice: type "tool" and "any" are not supported for this model.'}})
        text_only = (200, {"content": [{"type": "text", "text": "Here are my thoughts..."}], "stop_reason": "end_turn",
                           "usage": {"input_tokens": 10, "output_tokens": 5}})
        fake = FakeAPI(no_force, text_only, FakeAPI.tool(good_answer()))
        r = grade_notebook(RUBRIC, NB, AIConfig(api_key="sk-test"), client=client(fake))
        self.assertEqual(fake.requests[1]["body"]["tool_choice"], {"type": "auto"})
        last = fake.requests[2]["body"]["messages"][-1]["content"][0]["text"]
        self.assertIn("submit_grades", last)
        self.assertEqual(r.log["tool_choice"], "auto")
        self.assertEqual(len(r.results), len(NB_IDS))

    def test_busy_then_ok(self):
        fake = FakeAPI((529, {"error": {"message": "Overloaded"}}), FakeAPI.tool(good_answer()))
        r = grade_notebook(RUBRIC, NB, AIConfig(api_key="sk-test"), client=client(fake))
        self.assertEqual(len(fake.requests), 2)
        self.assertTrue(r.results)

    def test_clear_errors(self):
        for status, msg, expect in [(401, "invalid x-api-key", "API key was rejected"),
                                    (404, "model: nope", "wasn't found"),
                                    (400, "something odd", "(400)")]:
            fake = FakeAPI((status, {"error": {"message": msg}}))
            with self.assertRaises(AIError) as cm:
                grade_notebook(RUBRIC, NB, AIConfig(api_key="sk-test", model="nope"), client=client(fake))
            self.assertIn(expect, str(cm.exception))


class DesktopAITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"EASYGRADE_CONFIG_DIR": str(Path(self.tmp.name) / "cfg")})
        self.env.start()
        os.environ.pop("ANTHROPIC_API_KEY", None)
        from desktop.api import Api
        self.folder = build_demo_submissions(Path(self.tmp.name))
        self.api = Api()
        self.api.open_folder(str(self.folder))
        self.api.use_sample_rubric()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_settings_and_grade_student(self):
        api = self.api
        self.assertFalse(api.get_state()["ai_ready"])
        self.assertFalse(api.grade_student("1002")["ok"])                  # no key yet
        self.assertFalse(api.save_settings({"api_key": "hello"})["ok"])    # not a key
        s = api.save_settings({"api_key": "sk-ant-test-1234567890", "anonymize": True})
        self.assertTrue(s["has_key"])
        self.assertNotIn("1234567890", s["key_hint"])
        self.assertTrue(api.get_state()["ai_ready"])

        fake = FakeAPI(FakeAPI.tool(good_answer()))
        with mock.patch("grader.ai_grader.http_post", fake), \
             mock.patch.object(AnthropicClient.__init__, "__defaults__", (180, fake, lambda s: None)):
            r = api.grade_student("1002")
        self.assertTrue(r["ok"], r)
        d = api.get_student("1002")
        scored = {c["id"] for c in d["criteria"] if c["final"] is not None}
        self.assertEqual(scored, set(NB_IDS))                                # video criteria left for later
        self.assertEqual(d["status"], "graded")
        log = json.loads((self.folder / "_grading" / "ai_log" / "1002.json").read_text())
        sent = json.dumps(log["request"])
        self.assertNotIn("Marcus Bell", sent)
        self.assertNotIn("sk-ant", sent)

        r = api.grade_student("1010")   # nothing submitted
        self.assertTrue(r.get("skipped"))


if __name__ == "__main__":
    unittest.main()
