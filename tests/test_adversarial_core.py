"""Offline behavioral checks; run with unittest or pytest, without the live extra."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from jev_context.engine import Advisor, Policy
from jev_context.models import Excerpt, Judgment, Question, Task
from jev_context.provider import Batch, JevJudge, ProviderError
from jev_context.sources import SourceError, read_document, safe_path, split_blocks, verify_excerpt


def task(*ids):
    return Task(
        "Implement the upload policy",
        "uploads",
        "edit upload validation",
        tuple(Question(q, f"What is required for {q}?") for q in (ids or ("q1",))),
        hypotheses=("Uploads are unrestricted",),
    )


class FakeClient:
    def __init__(self, value=0.9, failure=None):
        self.value = value
        self.failure = failure
        self.calls = []

    def system_one(self, *, state, questions):
        self.calls.append((state, questions))
        if self.failure:
            raise self.failure
        return SimpleNamespace(
            nouls={key: SimpleNamespace(noul=self.value) for key in questions},
            usage=SimpleNamespace(input_tokens=17),
            model="jev-1.13.0",
        )


class StubJudge:
    def __init__(self, evaluator):
        self.evaluator = evaluator
        self.paths = []

    def evaluate(self, requested_task, document):
        self.paths.append(document.path)
        return self.evaluator(requested_task, document)


class TemporarySources(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        return target

    def doc(self, path="rules.md", text="# Uploads\nOnly owners may upload.\n", **kwargs):
        self.write(path, text)
        return read_document(self.root, path, **kwargs)

    def advisor(self, *, max_chars=24000, block_chars=2400, judge=None, **policy):
        return Advisor(
            self.root,
            judge,
            Policy(max_context_chars=max_chars, block_chars=block_chars, workers=1, **policy),
        )

    def evidence(self, document, **values):
        return [
            Judgment(document.path, block.id, values or {"q1": 0.9}) for block in document.blocks
        ]


class SourceIntegrityTests(TemporarySources):
    def test_utf8_crlf_hash_and_exact_spans(self):
        raw = "# 권한\r\n소유자만 업로드 가능.\r\n\r\n# Exception\r\nNever bypass 🔒".encode()
        document = self.doc(text=raw, block_chars=100)
        self.assertEqual(document.digest, hashlib.sha256(raw).hexdigest())
        self.assertEqual(document.text.encode(), raw)
        self.assertEqual("".join(b.text for b in document.blocks), document.text)
        last_end = 0
        for block in document.blocks:
            self.assertGreater(block.start, last_end)
            excerpt = Excerpt(document.path, document.digest, block.start, block.end, block.text)
            self.assertEqual(verify_excerpt(self.root, excerpt), block.text)
            last_end = block.end
        self.assertEqual(last_end, 5)

    def test_oversized_line_and_negation_are_never_truncated(self):
        text = "# Requirement\n" + "permit " * 1000 + "only if approved; otherwise DO NOT upload.\n"
        blocks = split_blocks(text, max_chars=100)
        self.assertEqual("".join(block.text for block in blocks), text)
        self.assertIn("otherwise DO NOT upload.", blocks[-1].text)
        self.assertGreater(len(blocks[-1].text), 100)

    def test_split_body_retains_enclosing_heading(self):
        blocks = split_blocks(
            "# Owners\n" + "A rule applies to owners.\n" * 15 + "# Guests\nGuests cannot upload.\n",
            max_chars=100,
        )
        owner_blocks = [b for b in blocks if "A rule" in b.text]
        self.assertGreater(len(owner_blocks), 1)
        self.assertTrue(all(b.heading == "# Owners" for b in owner_blocks))
        self.assertEqual(blocks[-1].heading, "# Guests")

    def test_different_or_shorter_fence_cannot_close_code_block(self):
        for opening, decoy, closing in (("```python", "~~~", "```"), ("````python", "```", "````")):
            with self.subTest(opening=opening):
                text = f"# Real heading\n{opening}\n{decoy}\n# code comment\nx = 1\n{closing}\n# Next heading\nRule.\n"
                blocks = split_blocks(text, max_chars=1000)
                self.assertNotIn("# code comment", [b.heading for b in blocks])
                self.assertEqual(blocks[-1].heading, "# Next heading")

    def test_unicode_separators_in_source_do_not_shift_line_numbers(self):
        text = "value = 'alpha\u2028beta\u2029gamma'\n\ndef upload():\n    return value\n"
        blocks = split_blocks(text, max_chars=1000)
        function_block = next(b for b in blocks if "def upload" in b.text)
        self.assertEqual(function_block.start, 3)
        self.assertEqual(function_block.end, 4)

    def test_freshness_uses_whole_file_hash_and_rejects_forged_ranges(self):
        document = self.doc(text="# One\nA rule.\n# Two\nAnother rule.\n")
        block = document.blocks[0]
        excerpt = Excerpt(document.path, document.digest, block.start, block.end, block.text)
        for invalid in (
            replace(excerpt, start=0),
            replace(excerpt, end=1000),
            replace(excerpt, text=excerpt.text + "forged"),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(SourceError):
                    verify_excerpt(self.root, invalid)
        self.write(document.path, document.text.replace("Another rule.", "Changed rule."))
        with self.assertRaisesRegex(SourceError, "source_changed"):
            verify_excerpt(self.root, excerpt)

    def test_containment_secrets_and_ignored_directories(self):
        for path in (
            "../outside.md",
            "nested/../../outside.md",
            str(self.root / "rules.md"),
            ".env",
            "nested/.env.production",
            "credentials.json",
            "id_ed25519",
            "private.pem",
            "private.key",
            ".git/config",
            "a/node_modules/package.md",
            ".ssh/config",
        ):
            with self.subTest(path=path):
                with self.assertRaises(SourceError):
                    safe_path(self.root, path)

    def test_symlinks_to_inside_outside_and_secret_are_rejected(self):
        self.write("safe.md", "Allowed source")
        self.write(".env", "TOKEN=do-not-read")
        self.write("sub/inside.md", "Allowed nested source")
        for name, target in (
            ("alias.md", self.root / "safe.md"),
            ("secret.md", self.root / ".env"),
            ("outside.md", self.root.parent / "outside.md"),
            ("linked", self.root / "sub"),
        ):
            (self.root / name).symlink_to(target, target_is_directory=name == "linked")
            path = "linked/inside.md" if name == "linked" else name
            with self.subTest(path=path):
                with self.assertRaises(SourceError):
                    read_document(self.root, path)

    def test_unreadable_binary_non_utf8_empty_and_size_limits(self):
        for name, contents, kind in (
            ("binary", b"a\x00b", "binary"),
            ("invalid", b"\xff", "not_utf8"),
            ("empty", b" \r\n\t", "empty"),
            ("large", b"x" * 11, "file_too_large"),
        ):
            self.write(name, contents)
            with self.subTest(name=name):
                with self.assertRaisesRegex(SourceError, kind):
                    read_document(self.root, name, max_bytes=10)
        self.write("exact", b"x" * 10)
        self.assertEqual(len(read_document(self.root, "exact", max_bytes=10).text), 10)
        with self.assertRaisesRegex(SourceError, "unreadable"):
            read_document(self.root, "missing")


class PolicyBehaviorTests(TemporarySources):
    def test_all_independent_evidence_spans_for_same_question_survive(self):
        document = self.doc(
            text="# Eligibility\nOnly owners may upload.\n# Exception\nSuspended owners cannot upload.\n"
        )
        advice = self.advisor().select(task(), {document.path: document}, self.evidence(document))
        self.assertIn("Only owners may upload.", advice.render())
        self.assertTrue(any("Suspended" in e.text for e in advice.excerpts))
        self.assertEqual(advice.unresolved, [])

    def test_constraints_and_conflicts_survive_without_question_matches(self):
        document = self.doc(
            text="# Constraint\nUploads require approval.\n# Conflict\nGuests cannot upload.\n"
        )
        judgments = [
            Judgment(document.path, document.blocks[0].id, {"q1": 0.01}, 0.99),
            Judgment(document.path, document.blocks[1].id, {"q1": 0.02}, 0, 0.99),
        ]
        advice = self.advisor().select(task(), {document.path: document}, judgments)
        self.assertIn("Uploads require approval.", advice.render())
        self.assertIn("Guests cannot upload.", advice.render())
        self.assertEqual(
            {r for e in advice.excerpts for r in e.reasons},
            {"constraint", "conflict", "short_source"},
        )
        self.assertEqual(advice.unresolved, ["q1"])

    def test_thresholds_are_inclusive_without_promoting_below_threshold(self):
        document = self.doc(text="# At\nAccepted.\n# Below\nNot accepted.\n")
        at, below = document.blocks
        judgments = [
            Judgment(document.path, at.id, {"q1": 0.60}, 0.70, 0.65),
            Judgment(document.path, below.id, {"q1": 0.5999}, 0.6999, 0.6499),
        ]
        advice = self.advisor(
            evidence_threshold=0.60, constraint_threshold=0.70, short_source_chars=0
        ).select(task(), {document.path: document}, judgments)
        self.assertEqual([e.start for e in advice.excerpts], [at.start])
        self.assertEqual(set(advice.excerpts[0].reasons), {"evidence", "constraint", "conflict"})

    def test_unanswered_questions_remain_explicit(self):
        document = self.doc()
        advice = self.advisor().select(
            task("known", "unknown"),
            {document.path: document},
            self.evidence(document, known=0.95, unknown=0.44),
        )
        self.assertEqual(advice.unresolved, ["unknown"])
        self.assertEqual(advice.excerpts[0].questions, ("known",))
        self.assertIn("Unresolved evidence questions: unknown", advice.render())

    def test_modes_preserve_original_reads_and_control_supplements(self):
        picked = self.doc(
            "picked.md", "# Chosen\nOriginal first part.\n# Rest\nOriginal second part.\n"
        )
        extra = self.doc("extra.md", "# Extra\nAdditional rule.\n")
        docs = {d.path: d for d in (picked, extra)}
        judgments = [self.evidence(picked)[0], *self.evidence(extra)]
        ranges = self.advisor().select(
            task(), docs, judgments, agent_picks=[picked.path], mode="ranges"
        )
        self.assertEqual({e.path for e in ranges.excerpts}, {picked.path})
        combined = self.advisor().select(task(), docs, judgments, agent_picks=[picked.path])
        self.assertEqual({e.path for e in combined.excerpts}, set(docs))
        supplement = self.advisor().select(
            task(), docs, judgments, agent_picks=[picked.path, picked.path], mode="supplement"
        )
        self.assertEqual(supplement.original_reads, [picked.path])
        self.assertEqual(
            next(e.text for e in supplement.excerpts if e.path == picked.path), picked.text
        )

    def test_api_failure_keeps_original_pick_and_explicit_unresolved(self):
        document = self.doc()

        def fail(*_):
            raise ProviderError("api_503 source text must not escape")

        advice = self.advisor(judge=StubJudge(fail)).advise(
            task(), [document.path], agent_picks=[document.path]
        )
        self.assertEqual(advice.excerpts[0].text, document.text)
        self.assertEqual(advice.unresolved, ["q1"])
        self.assertEqual(advice.errors, [{"path": document.path, "kind": "ProviderError"}])
        self.assertNotIn("source text must not escape", advice.render())

    def test_candidate_deduplication_and_usage_accounting(self):
        first, second = self.doc("a.md"), self.doc("b.md")
        judge = StubJudge(lambda requested, doc: Batch(self.evidence(doc), 17, 1, 2, "fixed"))
        docs, judgments, errors, usage = self.advisor(judge=judge).score(
            task(), [first.path, first.path, second.path, "missing.md"]
        )
        self.assertEqual(judge.paths, [first.path, second.path])
        self.assertEqual(set(docs), {first.path, second.path})
        self.assertEqual(len(judgments), 2)
        self.assertEqual(errors, [{"path": "missing.md", "kind": "unreadable"}])
        self.assertEqual(
            (usage["input_tokens"], usage["requests"], usage["cache_hits"]), (34, 2, 4)
        )

    def test_budget_includes_all_visible_metadata_and_never_truncates_spans(self):
        documents = [
            self.doc(f"rule-{i}.md", f"# Rule {i}\n" + "x" * 300 + " DO NOT bypass.\n")
            for i in range(5)
        ]
        advice = self.advisor(max_chars=1024).select(
            task(),
            {d.path: d for d in documents},
            [j for d in documents for j in self.evidence(d)],
            agent_picks=[documents[0].path],
        )
        self.assertLessEqual(len(advice.render()), 1024)
        self.assertTrue(advice.excerpts)
        self.assertTrue(advice.deferred)
        for excerpt in advice.excerpts:
            self.assertEqual(verify_excerpt(self.root, excerpt), excerpt.text)
            self.assertTrue(excerpt.text.endswith(" DO NOT bypass.\n"))
        self.assertEqual(
            set(advice.deferred), {d.path for d in documents} - {e.path for e in advice.excerpts}
        )

    def test_metadata_that_cannot_fit_is_reported_instead_of_truncated(self):
        picks = ["candidate-" + str(i) + "x" * 60 + ".md" for i in range(30)]
        with self.assertRaisesRegex(ValueError, "[Bb]udget"):
            self.advisor(max_chars=1024).select(task(), {}, [], agent_picks=picks)

    def test_changed_source_during_judging_is_removed_and_reopened_as_unresolved(self):
        document = self.doc()

        def edit_after_read(requested, doc):
            self.write(doc.path, "# Changed\nThe old permission was revoked.\n")
            return Batch(self.evidence(doc))

        advice = self.advisor(judge=StubJudge(edit_after_read)).advise(task(), [document.path])
        self.assertEqual(advice.excerpts, [])
        self.assertEqual(advice.unresolved, ["q1"])
        self.assertIn({"path": document.path, "kind": "source_changed"}, advice.errors)

    def test_unknown_documents_blocks_and_incomplete_answers_are_rejected(self):
        document = self.doc()
        invalid = (
            Judgment("unknown.md", document.blocks[0].id, {"q1": 0.99}),
            Judgment(document.path, "missing", {"q1": 0.99}),
            Judgment(document.path, document.blocks[0].id, {}),
            Judgment(document.path, document.blocks[0].id, {"q1": 0.99, "invented": 0.99}),
        )
        for judgment in invalid:
            with self.subTest(judgment=judgment):
                with self.assertRaises(ValueError):
                    self.advisor().select(task(), {document.path: document}, [judgment])


class ProviderBoundaryTests(TemporarySources):
    def make_judge(self, *, cache=True, client=None, **kwargs):
        judge = JevJudge(cache=self.root / "cache" if cache else None, **kwargs)
        fake = client or FakeClient()
        judge._local.client = fake
        return judge, fake

    def test_probabilities_must_be_finite_and_within_unit_interval(self):
        for value in (float("nan"), float("inf"), float("-inf"), -0.01, 1.01):
            for field in ("answer", "constraint", "conflict"):
                with self.subTest(value=value, field=field):
                    with self.assertRaises(ValueError):
                        Judgment(
                            "a",
                            "b1",
                            {"q1": value if field == "answer" else 0.5},
                            value if field == "constraint" else 0.0,
                            value if field == "conflict" else 0.0,
                        )
        self.assertEqual(Judgment("a", "b1", {"q1": 0.0}, 1.0).constraint, 1.0)

    def test_cache_hit_avoids_network_and_omits_source_text(self):
        document = self.doc(text="# Policy\nPRIVATE-SOURCE-MARKER only owners may upload.\n")
        judge, fake = self.make_judge()
        initial = judge.evaluate(task(), document)
        repeat = judge.evaluate(task(), document)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(initial.judgments, repeat.judgments)
        self.assertEqual((repeat.requests, repeat.input_tokens, repeat.cache_hits), (0, 0, 1))
        cached_text = next((self.root / "cache").glob("*.json")).read_text()
        self.assertNotIn("PRIVATE-SOURCE-MARKER", cached_text)

    def test_source_task_and_model_changes_each_invalidate_cache(self):
        document = self.doc()
        judge, fake = self.make_judge()
        judge.evaluate(task(), document)
        changed_doc = self.doc(text=document.text + "A new condition.\n")
        judge.evaluate(task(), changed_doc)
        changed_task = replace(task(), next_action="delete upload validation")
        judge.evaluate(changed_task, changed_doc)
        other_judge, other_fake = self.make_judge(model="jev-1.12.0")
        other_judge.evaluate(changed_task, changed_doc)
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(len(other_fake.calls), 1)

    def test_malformed_cache_is_ignored_and_refetched(self):
        document = self.doc()
        judge, fake = self.make_judge()
        judge.evaluate(task(), document)
        cache_path = next((self.root / "cache").glob("*.json"))
        original = json.loads(cache_path.read_text())
        bad_probability = {**original, "answers": {key: None for key in original["answers"]}}
        bad_container = {**original, "answers": ["bad"]}
        for malformed in (None, [], "bad", bad_probability, bad_container):
            with self.subTest(malformed=malformed):
                cache_path.write_text(json.dumps(malformed))
                previous_calls = len(fake.calls)
                result = judge.evaluate(task(), document)
                self.assertEqual(len(fake.calls), previous_calls + 1)
                self.assertEqual(result.cache_hits, 0)
                self.assertEqual(result.judgments[0].answers["q1"], 0.9)

    def test_invalid_live_probabilities_never_poison_cache(self):
        document = self.doc()
        for value in (float("nan"), float("inf"), -0.1, 1.1):
            with self.subTest(value=value):
                for old in (self.root / "cache").glob("*.json"):
                    old.unlink()
                judge, _ = self.make_judge(client=FakeClient(value=value))
                with self.assertRaises((ProviderError, ValueError)):
                    judge.evaluate(task(), document)
                self.assertEqual(list((self.root / "cache").glob("*.json")), [])

    def test_missing_live_answer_is_a_sanitized_provider_error(self):
        class IncompleteClient(FakeClient):
            def system_one(self, *, state, questions):
                response = super().system_one(state=state, questions=questions)
                response.nouls.pop(next(iter(questions)))
                return response

        judge, _ = self.make_judge(client=IncompleteClient())
        with self.assertRaises(ProviderError) as failure:
            judge.evaluate(task(), self.doc())
        self.assertEqual(str(failure.exception), "api_failure")
        self.assertEqual(list((self.root / "cache").glob("*.json")), [])

    def test_api_error_body_is_not_exposed(self):
        class UpstreamFailure(RuntimeError):
            status_code = 503

        judge, _ = self.make_judge(
            client=FakeClient(failure=UpstreamFailure("PRIVATE-TOKEN and source body"))
        )
        with self.assertRaises(ProviderError) as failure:
            judge.evaluate(task(), self.doc())
        self.assertEqual(str(failure.exception), "api_503")
        self.assertNotIn("PRIVATE", str(failure.exception))

    def test_utf8_request_splitting_preserves_every_source_block(self):
        text = "".join(f"# Rule {i}\n" + "권한 " * 55 + "\n" for i in range(6))
        document = self.doc(text=text, block_chars=300)
        judge, fake = self.make_judge(cache=False, max_state_bytes=2400)
        batch = judge.evaluate(task(), document)
        expected_ids = [b.id for b in document.blocks]
        self.assertEqual([j.block_id for j in batch.judgments], expected_ids)
        sent_ids = [bid for state, _ in fake.calls for bid in state["source"]["blocks"]]
        self.assertCountEqual(sent_ids, expected_ids)
        self.assertGreater(len(fake.calls), 1)
        self.assertEqual(batch.requests, len(fake.calls))
        self.assertEqual(batch.input_tokens, len(fake.calls) * 17)
        for state, _ in fake.calls:
            for bid, sent in state["source"]["blocks"].items():
                self.assertEqual(sent["text"], next(b.text for b in document.blocks if b.id == bid))

    def test_unsplittable_input_fails_without_sending_truncated_content(self):
        document = self.doc(text="x" * 10000, block_chars=2400)
        judge, fake = self.make_judge(cache=False, max_state_bytes=1000)
        with self.assertRaises(ProviderError):
            judge.evaluate(task(), document)
        self.assertEqual(fake.calls, [])

    def test_wrong_cache_keys_or_request_hash_require_fresh_request(self):
        document = self.doc()
        judge, fake = self.make_judge()
        judge.evaluate(task(), document)
        cache_path = next((self.root / "cache").glob("*.json"))
        original = json.loads(cache_path.read_text())
        for malformed in (
            {**original, "request_hash": "forged"},
            {**original, "answers": {"another-block:q:q1": 0.99}},
        ):
            with self.subTest(malformed=malformed):
                cache_path.write_text(json.dumps(malformed))
                previous_calls = len(fake.calls)
                judge.evaluate(task(), document)
                self.assertEqual(len(fake.calls), previous_calls + 1)


if __name__ == "__main__":
    unittest.main()
