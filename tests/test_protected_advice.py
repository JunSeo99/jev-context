from pathlib import Path

import pytest

from jev_context import Advisor, Policy, Question, Task
from jev_context.models import Excerpt, Judgment
from jev_context.sources import read_document, source_lines


def setup(tmp_path: Path):
    (tmp_path / "code.py").write_text("# Main\nvalue = 1\n# Exception\nvalue = 2\n")
    (tmp_path / "rules.md").write_text("# Global rule\nRequire the owner role before writing.\n")
    docs = {p: read_document(tmp_path, p) for p in ("code.py", "rules.md")}
    task = Task("Change writes", "workspace writes", "edit", (Question("q", "What applies?"),))
    d = docs["code.py"]
    original = Excerpt(d.path, d.digest, 2, 2, source_lines(d.text)[1], reasons=("baseline",))
    return task, docs, original


def test_low_scores_cannot_remove_original_range(tmp_path):
    task, docs, original = setup(tmp_path)
    scores = [Judgment(d.path, b.id, {"q": 0.0}) for d in docs.values() for b in d.blocks]
    advice = Advisor(tmp_path, None).select(
        task, docs, scores, original_ranges=[original], mode="advisory"
    )
    assert original.text in advice.render()
    assert advice.unresolved == ["q"]


def test_overlapping_supplement_preserves_source_once(tmp_path):
    task, docs, original = setup(tmp_path)
    d = docs["code.py"]
    scores = [Judgment(d.path, b.id, {"q": 0.9}) for b in d.blocks]
    advice = Advisor(tmp_path, None).select(
        task, docs, scores, original_ranges=[original], mode="advisory"
    )
    assert advice.render().count("value = 1") == 1
    assert advice.render().count("value = 2") == 1
    assert any(e.start <= original.start and e.end >= original.end for e in advice.excerpts)


def test_budget_rejects_instead_of_dropping_protected_content(tmp_path):
    task, docs, _ = setup(tmp_path)
    (tmp_path / "large.md").write_text("Mandatory original text.\n" * 200)
    d = read_document(tmp_path, "large.md")
    docs[d.path] = d
    original = Excerpt(d.path, d.digest, 1, len(source_lines(d.text)), d.text)
    with pytest.raises(ValueError, match="Protected original"):
        Advisor(tmp_path, None, Policy(max_context_chars=1024)).select(
            task, docs, [], original_ranges=[original], mode="advisory"
        )


def test_missing_or_stale_original_source_is_not_accepted(tmp_path):
    task, docs, original = setup(tmp_path)
    altered = Excerpt(original.path, "wrong", original.start, original.end, original.text)
    with pytest.raises(ValueError, match="unavailable or changed"):
        Advisor(tmp_path, None).select(task, docs, [], original_ranges=[altered], mode="advisory")


def test_bounded_supplement_preserves_all_original_characters(tmp_path):
    task, docs, original = setup(tmp_path)
    for i in range(10):
        name = f"extra{i}.md"
        (tmp_path / name).write_text(f"# Rule {i}\n" + "The owner must approve the change. " * 20)
        docs[name] = read_document(tmp_path, name)
    scores = [Judgment(d.path, b.id, {"q": 0.9}, 0.9) for d in docs.values() for b in d.blocks]
    policy = Policy(max_extra_chars=1000)
    advisor = Advisor(tmp_path, None, policy)
    base = advisor.select(task, docs, [], original_ranges=[original], mode="advisory")
    out = advisor.select(task, docs, scores, original_ranges=[original], mode="advisory")
    assert original.text in out.render()
    assert len(out.render()) <= len(base.render()) + 1000
    assert out.deferred
