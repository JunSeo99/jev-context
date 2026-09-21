import json
from pathlib import Path

from jev_context.cli import main


def test_documented_inspection_command_works_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    root = Path(__file__).parents[1] / "benchmarks/cases/case-001"
    assert main([str(root / "task.json"), "--root", str(root / "corpus"), "--inspect"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result and all(x["blocks"] and x["sha256"] for x in result)


def test_invalid_task_returns_a_sanitized_error(tmp_path, capsys):
    path = tmp_path / "task.json"
    path.write_text(json.dumps({"request": "x", "questions": [{"id": 1, "text": "secret text"}]}))
    assert main([str(path), "--root", str(tmp_path), "--inspect"]) == 2
    assert "secret text" not in capsys.readouterr().err
