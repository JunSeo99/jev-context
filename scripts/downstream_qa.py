"""Optional blind, tool-free answer evaluation using an authenticated Claude CLI.

Each answer is a fresh process with only the request and one condition's packet.
The grader sees anonymized answers and the frozen rubric, never condition names.
This evaluates decision answers, not executed code changes.
"""

import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks/results/downstream"


def call(prompt, system, schema=None):
    command = [
        "claude",
        "--safe-mode",
        "--print",
        "--tools",
        "",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format",
        "json",
        "--max-budget-usd",
        "0.40",
        "--system-prompt",
        system,
    ]
    if schema:
        command += ["--json-schema", json.dumps(schema)]
    with tempfile.TemporaryDirectory(prefix="jev-blind-") as cwd:
        response = subprocess.run(
            command,
            input=json.dumps(prompt, ensure_ascii=False),
            text=True,
            capture_output=True,
            cwd=cwd,
            timeout=150,
        )
    start = response.stdout.find("{")
    if start < 0:
        raise RuntimeError("CLI returned no JSON; check authentication and quota")
    data = json.loads(response.stdout[start:])
    if response.returncode or data.get("is_error"):
        raise RuntimeError("CLI generation failed")
    return {
        k: data[k]
        for k in [
            "result",
            "structured_output",
            "usage",
            "modelUsage",
            "total_cost_usd",
            "stop_reason",
        ]
        if k in data
    }


def answer(cid, arm, run):
    path = OUT / f"{cid}-{arm}.json"
    if path.exists():
        return
    task = json.loads((ROOT / f"benchmarks/cases/{cid}/task.json").read_text())
    prompt = {
        "request": task["request"],
        "question": task["downstream_question"],
        "evidence": run["cases"][cid]["outputs"][arm]["packet"],
    }
    result = call(
        prompt,
        "Answer only from the supplied evidence. Do not use tools or unstated assumptions. State missing information. Cite source paths and line ranges. Answer the question directly in at most 220 words, covering concrete constraints and exceptions.",
    )
    result["input_sha256"] = hashlib.sha256(
        json.dumps(prompt, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(cid, arm, "answered", flush=True)


def grade(cid):
    target = OUT / f"{cid}-grade.json"
    if target.exists():
        return
    gold = json.loads((ROOT / f"benchmarks/gold/{cid}.json").read_text())
    task = json.loads((ROOT / f"benchmarks/cases/{cid}/task.json").read_text())
    arms = ["baseline_snippets", "advisory"]
    if int(cid[-1]) % 2:
        arms.reverse()
    responses = {
        chr(65 + i): json.loads((OUT / f"{cid}-{arm}.json").read_text())["result"]
        for i, arm in enumerate(arms)
    }
    concepts = gold["downstream_qa"]["expected_answer_concepts"]
    schema = {
        "type": "object",
        "properties": {
            "grades": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "answer_id": {"type": "string", "enum": ["A", "B"]},
                        "concepts_covered": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0},
                        },
                        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "answer_id",
                        "concepts_covered",
                        "unsupported_claims",
                        "explanation",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["grades"],
        "additionalProperties": False,
    }
    prompt = {
        "question": task["downstream_question"],
        "rubric": dict(enumerate(concepts)),
        "evidence": gold["obligations"],
        "unanswerable": gold["unanswerable_questions"],
        "answers": responses,
        "full_source_corpus": {
            str(p.relative_to(ROOT / f"benchmarks/cases/{cid}/corpus")): p.read_text()
            for p in sorted((ROOT / f"benchmarks/cases/{cid}/corpus").rglob("*"))
            if p.is_file()
        },
    }
    result = call(
        prompt,
        "Grade each anonymous answer against the frozen concepts. Credit a concept only when its concrete requirements are substantively present and correct. An explicit lack of evidence does not earn a missing factual concept. Identify unsupported definitive claims. Be conservative; do not infer details omitted from an answer. Rubric concept IDs start at zero.",
        schema,
    )
    result["arm_mapping"] = {chr(65 + i): arm for i, arm in enumerate(arms)}
    result["concept_count"] = len(concepts)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(cid, "graded", flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run = json.loads((ROOT / "benchmarks/results/v3-dev.json").read_text())
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(answer, cid, arm, run)
            for cid in run["cases"]
            for arm in ["baseline_snippets", "advisory"]
        ]
        for f in as_completed(futures):
            f.result()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(grade, cid) for cid in run["cases"]]):
            f.result()


if __name__ == "__main__":
    main()
