import unittest
from types import SimpleNamespace

import anthropic

from rubric import roast
from rubric.roast import RoastError, parse_score, parse_verdict, run_council
from rubric.storage import Idea

JUDGE_REPORT = """## THE VERDICT: RESHAPE
Confidence: medium

**The call in one line:** Narrow it.
"""


def idea(**kw):
    base = dict(name="Widget", concept="c", customer="u", edge="e", constraints="k")
    return Idea(**{**base, **kw})


def message(text, stop="end_turn"):
    return SimpleNamespace(
        stop_reason=stop, content=[SimpleNamespace(type="text", text=text)]
    )


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    """`answer(kwargs)` returns the message, or raises, for each streamed call."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.answer(kwargs))


def council_answer(kwargs):
    if kwargs["model"] == roast.JUDGE_MODEL:
        return message(JUDGE_REPORT)
    return message("STANCE: x\nSCORE: 6/10")


class ParsingTests(unittest.TestCase):
    def test_score_takes_the_last_one_and_clamps(self):
        self.assertEqual(parse_score("SCORE: 3/10 ... SCORE: **7/10**"), 7)
        self.assertEqual(parse_score("SCORE: 15/10"), 10)
        self.assertEqual(parse_score("SCORE: 0/10"), 1)
        self.assertIsNone(parse_score("no score here"))

    def test_verdict_and_confidence(self):
        self.assertEqual(parse_verdict(JUDGE_REPORT), ("RESHAPE", "medium"))
        self.assertEqual(parse_verdict("## THE VERDICT: **kill**\nConfidence: High"), ("KILL", "high"))
        self.assertEqual(parse_verdict("nothing"), ("", ""))

    def test_brief_has_all_four_parts(self):
        brief = roast.build_brief(idea())
        for label in roast.BRIEF_LABELS.values():
            self.assertIn(label, brief)

    def test_missing_fields(self):
        self.assertEqual(roast.missing_fields(idea()), [])
        self.assertEqual(roast.missing_fields(idea(edge=" ")), ["The founder's edge"])


class CouncilTests(unittest.TestCase):
    def test_happy_path(self):
        client = FakeClient(council_answer)
        result = run_council(idea(), client)
        self.assertEqual((result.verdict, result.confidence), ("RESHAPE", "medium"))
        self.assertEqual(set(result.reports), {p.name for p in roast.PERSONAS})
        self.assertEqual(set(result.scores.values()), {6})
        self.assertEqual(result.failed, {})
        models = [c["model"] for c in client.calls]
        self.assertEqual(models.count(roast.PERSONA_MODEL), 5)
        self.assertEqual(models.count(roast.JUDGE_MODEL), 1)

    def test_only_the_researcher_gets_web_search(self):
        client = FakeClient(council_answer)
        run_council(idea(), client)
        with_tools = [c for c in client.calls if "tools" in c]
        self.assertEqual(len(with_tools), 1)
        self.assertIn("Researcher", with_tools[0]["system"])

    def test_judge_sees_the_reports_and_the_brief(self):
        client = FakeClient(council_answer)
        run_council(idea(), client)
        judge = next(c for c in client.calls if c["model"] == roast.JUDGE_MODEL)
        user = judge["messages"][0]["content"]
        self.assertIn("### Contrarian", user)
        self.assertIn("THE BRIEF", user)

    def test_one_failed_persona_is_reported_and_the_judge_proceeds(self):
        def answer(kwargs):
            if "Logician" in kwargs["system"]:
                raise RoastError("boom")
            return council_answer(kwargs)

        client = FakeClient(answer)
        result = run_council(idea(), client)
        self.assertEqual(result.failed, {"Logician": "boom"})
        self.assertNotIn("Logician", result.reports)
        judge = next(c for c in client.calls if c["model"] == roast.JUDGE_MODEL)
        self.assertIn("Missing from the council: Logician", judge["messages"][0]["content"])

    def test_all_personas_failing_raises(self):
        def answer(kwargs):
            raise RoastError("down")

        with self.assertRaises(RoastError):
            run_council(idea(), FakeClient(answer))

    def test_judge_failure_raises(self):
        def answer(kwargs):
            if kwargs["model"] == roast.JUDGE_MODEL:
                raise RoastError("nope")
            return council_answer(kwargs)

        with self.assertRaisesRegex(RoastError, "Judge failed: nope"):
            run_council(idea(), FakeClient(answer))

    def test_incomplete_idea_makes_no_calls(self):
        client = FakeClient(council_answer)
        with self.assertRaisesRegex(RoastError, "Fill in"):
            run_council(idea(customer=""), client)
        self.assertEqual(client.calls, [])

    def test_refusal_counts_as_a_failure(self):
        def answer(kwargs):
            if "Buyer" in kwargs["system"]:
                return message("", stop="refusal")
            return council_answer(kwargs)

        result = run_council(idea(), FakeClient(answer))
        self.assertIn("Buyer", result.failed)

    def test_pause_turn_is_resumed(self):
        seen = []

        def answer(kwargs):
            if "Researcher" in kwargs["system"]:
                seen.append(len(kwargs["messages"]))
                if len(kwargs["messages"]) == 1:
                    return message("", stop="pause_turn")
            return council_answer(kwargs)

        result = run_council(idea(), FakeClient(answer))
        self.assertEqual(seen, [1, 2])
        self.assertIn("Researcher", result.reports)

    def test_progress_reports_every_member(self):
        events = []
        run_council(idea(), FakeClient(council_answer), lambda who, s: events.append((who, s)))
        self.assertIn(("Judge", "done"), events)
        for p in roast.PERSONAS:
            self.assertIn((p.name, "working"), events)
            self.assertIn((p.name, "done"), events)

    def test_api_errors_explained_without_leaking(self):
        req = SimpleNamespace(method="POST", url="https://x")
        resp = SimpleNamespace(status_code=401, headers={}, request=req)
        err = anthropic.AuthenticationError("bad key sk-secret", response=resp, body=None)
        self.assertEqual(roast._explain(err), "The API key was rejected.")


class StoredResultTests(unittest.TestCase):
    def test_result_round_trips_through_an_idea(self):
        result = run_council(idea(), FakeClient(council_answer))
        i = idea(roast=result.to_dict())
        self.assertEqual(Idea.from_dict(vars(i)).roast["verdict"], "RESHAPE")


if __name__ == "__main__":
    unittest.main()
