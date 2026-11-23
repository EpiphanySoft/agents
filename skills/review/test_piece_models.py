"""piece_models.py: what each piece ran on, read from its transcript.

Run with `python3 skills/review/test_piece_models.py` from the repository's root (standard library only).
"""

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import piece_models  # noqa: E402

NAMED = "claude-opus-5-5,claude-sonnet-5-5"


def answer(model, stop="end_turn", when="2026-01-01T00:00:00Z"):
    return {"type": "assistant", "timestamp": when, "message": {"model": model, "stop_reason": stop}}


class PieceModels(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))

    def piece(self, name, entries, description=None):
        path = self.dir / f"agent-{name}.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        if description:
            (self.dir / f"agent-{name}.meta.json").write_text(json.dumps({"description": description}), encoding="utf-8")
        return path

    def run_it(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = piece_models.main(list(args))
        return status, out.getvalue(), err.getvalue()

    def test_a_piece_on_its_named_model_is_ok(self):
        self.piece("a", [{"type": "user", "message": {"content": "go"}}, answer("claude-opus-5-5"), answer("claude-opus-5-5")],
                   description="unit 07")
        status, out, _ = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 0)
        self.assertIn("ok       unit 07: claude-opus-5-5 (2 of 2 answers)", out)
        self.assertIn("1 pieces read, 0 to check", out)

    def test_a_refusal_and_the_model_that_took_over_are_both_reported(self):
        self.piece("b", [answer("claude-opus-5-5"), answer("claude-opus-5-5", stop="refusal", when="T1"),
                         answer("claude-opus-4-8", when="T2"), answer("claude-opus-4-8")], description="checker")
        status, out, _ = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 1)
        self.assertIn("CHECK    checker: ", out)
        self.assertIn("ran on claude-opus-4-8, which the proposal doesn't name", out)
        self.assertIn("changed from claude-opus-5-5 to claude-opus-4-8 at answer 3 of 4 (T2)", out)
        self.assertIn("claude-opus-5-5 refused at answer 2 (T1)", out)

    def test_a_change_between_two_named_models_is_still_reported(self):
        # A checker that falls onto the model that made its claims shares their blind spots.
        self.piece("c", [answer("claude-opus-5-5"), answer("claude-sonnet-5-5")])
        status, out, _ = self.run_it("--models", NAMED, str(self.dir / "agent-c.jsonl"))
        self.assertEqual(status, 1)
        self.assertIn("changed from claude-opus-5-5 to claude-sonnet-5-5 at answer 2 of 2", out)

    def test_a_piece_wholly_on_an_unnamed_model_is_reported(self):
        self.piece("d", [answer("claude-opus-4-8")])
        status, out, _ = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 1)
        self.assertIn("which the proposal doesn't name", out)

    def test_a_refusal_with_no_change_is_reported(self):
        self.piece("e", [answer("claude-sonnet-5-5"), answer("claude-sonnet-5-5", stop="refusal")])
        status, out, _ = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 1)
        self.assertIn("claude-sonnet-5-5 refused at answer 2", out)

    def test_nothing_readable_is_never_a_clean_run(self):
        status, _, err = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 2)
        self.assertIn("no transcript found", err)
        self.piece("f", [{"type": "user", "message": {"content": "go"}}, {"kind": "another format"}])
        status, out, err = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 2)
        self.assertIn("UNREAD", out)
        self.assertIn("nothing was checked", err)

    def test_one_unread_transcript_among_read_ones_fails_the_check(self):
        self.piece("g", [answer("claude-opus-5-5")])
        self.piece("h", [{"type": "user", "message": {"content": "go"}}])
        status, out, _ = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 1)
        self.assertIn("1 pieces read, 0 to check, 1 unread", out)

    def test_synthetic_answers_and_broken_lines_are_skipped(self):
        path = self.piece("i", [answer("<synthetic>"), answer("claude-opus-5-5")])
        path.write_text(path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
        status, out, _ = self.run_it("--models", NAMED, str(self.dir))
        self.assertEqual(status, 0)
        self.assertIn("claude-opus-5-5 (1 of 1 answers)", out)


if __name__ == "__main__":
    unittest.main()
