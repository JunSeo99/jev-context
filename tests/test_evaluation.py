import importlib.util
from pathlib import Path

from jev_context.models import Excerpt

spec = importlib.util.spec_from_file_location(
    "evaluate", Path(__file__).parents[1] / "scripts/evaluate.py"
)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_alternative_evidence_is_sufficient_but_conjunction_is_required(tmp_path):
    (tmp_path / "a.md").write_text("First rule.\nSecond condition.\n")
    (tmp_path / "b.md").write_text("Equivalent complete statement.\n")
    gold = {
        "obligations": [
            {
                "id": "o",
                "alternatives": [
                    [
                        {"path": "a.md", "quote": "First rule."},
                        {"path": "a.md", "quote": "Second condition."},
                    ],
                    [{"path": "b.md", "quote": "Equivalent complete statement."}],
                ],
            }
        ]
    }
    one = Excerpt("a.md", "unused", 1, 1, "First rule.\n")
    two = Excerpt("a.md", "unused", 2, 2, "Second condition.\n")
    alternative = Excerpt("b.md", "unused", 1, 1, "Equivalent complete statement.\n")
    assert evaluation.evidence_metrics(gold, [one], tmp_path)["recall"] == 0
    assert evaluation.evidence_metrics(gold, [one, two], tmp_path)["recall"] == 1
    assert evaluation.evidence_metrics(gold, [alternative], tmp_path)["recall"] == 1


def test_disjoint_ranges_cannot_fabricate_a_contiguous_quote(tmp_path):
    (tmp_path / "a.md").write_text("A\nmissing\nB\n")
    gold = {"obligations": [{"id": "o", "alternatives": [[{"path": "a.md", "quote": "A\nB"}]]}]}
    selected = [Excerpt("a.md", "unused", 1, 1, "A\n"), Excerpt("a.md", "unused", 3, 3, "B\n")]
    assert evaluation.evidence_metrics(gold, selected, tmp_path)["recall"] == 0
