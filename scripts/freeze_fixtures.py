"""Materialize independently authored fixtures and validate all exact evidence quotes."""

import datetime
import hashlib
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "benchmarks"


def main():
    fixtures = runpy.run_path(str(ROOT / "author_corpus.py"))["CASES"]
    if (ROOT / "freeze.json").exists():
        raise SystemExit("Already frozen; do not overwrite evaluation data")
    for task, files, gold in fixtures:
        case = ROOT / "cases" / task["id"]
        for path, content in files.items():
            target = case / "corpus" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        (case / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        for obligation in gold["obligations"]:
            for alternative in obligation["alternatives"]:
                for e in alternative:
                    assert e["quote"] in files[e["path"]], (task["id"], obligation["id"])
        (ROOT / "gold").mkdir(exist_ok=True)
        (ROOT / "gold" / f"{task['id']}.json").write_text(
            json.dumps(gold, ensure_ascii=False, indent=2) + "\n"
        )
    paths = sorted([*ROOT.glob("cases/**/*"), *ROOT.glob("gold/*.json")])
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
        if p.is_file()
    }
    freeze = {
        "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cases": [t["id"] for t, _, _ in fixtures],
        "files": hashes,
        "disclosure": "Independent fixture author produced 8 development cases before model outputs. Its usage limit prevented planned extra cases and final review. Parent only materialized and validated exact quotes; gold was not adjusted to results.",
    }
    (ROOT / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n")
    print(f"Frozen {len(fixtures)} cases and {len(hashes)} files")


if __name__ == "__main__":
    main()
