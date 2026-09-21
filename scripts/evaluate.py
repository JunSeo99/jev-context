#!/usr/bin/env python3
"""Run frozen fact-evidence experiments. Gold is loaded only AFTER inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from jev_context import Advisor, Policy, Task
from jev_context.models import Advice, Excerpt
from jev_context.provider import PROMPT_VERSION, JevJudge
from jev_context.sources import source_lines


def fingerprint(root: Path) -> str:
    import jev_context

    h = hashlib.sha256()
    for p in sorted(Path(jev_context.__file__).parent.glob("*.py")):
        h.update(("src/jev_context/" + p.name).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def ranges_packet(root, selected):
    excerpts = []
    for r in selected:
        raw = (root / r["path"]).read_bytes()
        text = raw.decode()
        start = r.get("start_line", r.get("start", 1))
        end = r.get("end_line", r.get("end", len(source_lines(text))))
        excerpts.append(
            Excerpt(
                r["path"],
                hashlib.sha256(raw).hexdigest(),
                start,
                end,
                "".join(source_lines(text)[start - 1 : end]),
                reasons=("baseline",),
            )
        )
    return Advice(excerpts, [], [], [], []).render(), excerpts


def evidence_metrics(gold, excerpts, root):
    # Match exact golden text against contiguous ORIGINAL source intervals.
    intervals = {}
    for e in excerpts:
        intervals.setdefault(e.path, set()).update(range(e.start, e.end + 1))
    chunks = {}
    for path, selected in intervals.items():
        source = source_lines((root / path).read_bytes().decode())
        parts, current = [], []
        for i, line in enumerate(source, 1):
            if i in selected:
                current.append(line)
            elif current:
                parts.append("".join(current))
                current = []
        if current:
            parts.append("".join(current))
        chunks[path] = parts

    def present(e):
        return any(e["quote"] in c for c in chunks.get(e["path"], []))

    obligations = gold["obligations"]
    covered = [
        o["id"]
        for o in obligations
        if any(all(present(e) for e in option) for option in o["alternatives"])
    ]
    critical = [o["id"] for o in obligations if o.get("critical", True)]
    return {
        "covered": covered,
        "missing": [o["id"] for o in obligations if o["id"] not in covered],
        "obligations": len(obligations),
        "recall": len(covered) / len(obligations) if obligations else 1,
        "all_critical": all(x in covered for x in critical),
    }


def load_baseline(case, baseline_dir):
    paths = [case / "baseline.json"]
    if baseline_dir:
        paths = [
            baseline_dir / f"{case.name}.json",
            baseline_dir / case.name / "baseline.json",
        ] + paths
    for p in paths:
        if p.is_file():
            data = json.loads(p.read_text())
            selected = data.get("selected", data.get("ranges", []))
            picks = data.get("paths", list(dict.fromkeys(r["path"] for r in selected)))
            return selected or [{"path": p} for p in picks], picks
    raise ValueError(f"Frozen baseline missing: {case.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-chars", type=int, default=24000)
    parser.add_argument("--threshold", type=float, default=Policy().evidence_threshold)
    parser.add_argument("--constraint-threshold", type=float, default=Policy().constraint_threshold)
    parser.add_argument("--replay", type=Path, help="Reuse saved judgments; no model calls")
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if args.env_file:
        import os

        # Deliberately read one known key without logging or sourcing shell code.
        for line in args.env_file.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                os.environ["TYPESAFE_API_KEY"] = line.partition("=")[2].strip().strip("\"'")
    import tiktoken

    tokenizer = tiktoken.get_encoding("cl100k_base")
    root = Path(__file__).resolve().parents[1]
    policy = Policy(
        max_context_chars=args.max_chars,
        evidence_threshold=args.threshold,
        constraint_threshold=args.constraint_threshold,
    )
    record = {
        "schema_version": 1,
        "started_at_unix": time.time(),
        "source_sha256": fingerprint(root),
        "prompt_version": PROMPT_VERSION,
        "policy": asdict(policy),
        "tokenizer": "cl100k_base (comparison proxy, not Jev tokenizer)",
        "cases": {},
    }
    replay = json.loads(args.replay.read_text()) if args.replay else None
    cases_root = args.suite / "cases" if (args.suite / "cases").is_dir() else args.suite
    cases = []
    for p in sorted(cases_root.glob("*/task.json")):
        data = json.loads(p.read_text())
        if data.get("split") == args.split and (not args.case or data["id"] in args.case):
            cases.append((p.parent, data))
    if not cases:
        raise ValueError("No cases matched")
    with JevJudge(cache=args.cache) as judge:
        for case, data in cases:
            task = Task.from_dict(data)
            corpus = case / "corpus"
            selected, picks = load_baseline(case, args.baseline_dir)
            advisor = Advisor(corpus, judge, policy)
            if replay:
                from jev_context.models import Judgment
                from jev_context.sources import read_document

                old = replay["cases"][data["id"]]
                docs = {
                    p: read_document(corpus, p, block_chars=policy.block_chars)
                    for p in old["documents"]
                }
                if any(d.digest != old["documents"][p] for p, d in docs.items()):
                    raise ValueError("Replay source hash mismatch")
                judgments = [Judgment(**j) for j in old["judgments"]]
                errors, usage = old["errors"], {**old["usage"], "replayed": True}
            else:
                docs, judgments, errors, usage = advisor.score(task, data["candidates"])
            outputs = {}
            for name, ranges in [
                ("baseline_snippets", selected),
                ("baseline_full", [{"path": p} for p in picks]),
                ("all_sources", [{"path": p} for p in docs]),
            ]:
                packet, excerpts = ranges_packet(corpus, ranges)
                outputs[name] = {"packet": packet, "excerpts": [asdict(e) for e in excerpts]}
            for mode in ["ranges", "supplement", "combined"]:
                advice = advisor.select(
                    task, docs, judgments, agent_picks=picks, errors=errors, usage=usage, mode=mode
                )
                outputs[mode] = {
                    "packet": advice.render(),
                    "excerpts": [asdict(e) for e in advice.excerpts],
                    "unresolved": advice.unresolved,
                    "deferred": advice.deferred,
                }
            if hasattr(policy, "max_extra_chars"):
                _, planned = ranges_packet(corpus, selected)
                protected_policy = Policy(
                    max_context_chars=max(
                        policy.max_context_chars,
                        len(outputs["baseline_snippets"]["packet"]) + policy.max_extra_chars + 1500,
                    ),
                    evidence_threshold=policy.evidence_threshold,
                    constraint_threshold=policy.constraint_threshold,
                )
                protected = Advisor(corpus, judge, protected_policy).select(
                    task,
                    docs,
                    judgments,
                    agent_picks=picks,
                    original_ranges=planned,
                    errors=errors,
                    usage=usage,
                    mode="advisory",
                )
                outputs["advisory"] = {
                    "packet": protected.render(),
                    "excerpts": [asdict(e) for e in protected.excerpts],
                    "unresolved": protected.unresolved,
                    "deferred": protected.deferred,
                    "max_extra_chars": protected_policy.max_extra_chars,
                    "max_context_chars": protected_policy.max_context_chars,
                }
            # No labels were consulted when producing any of the packets above.
            gold_path = case / "gold.json"
            if not gold_path.exists():
                gold_path = args.suite / "gold" / f"{data['id']}.json"
            gold = json.loads(gold_path.read_text())
            for output in outputs.values():
                excerpts = [Excerpt(**e) for e in output["excerpts"]]
                output.update(evidence_metrics(gold, excerpts, corpus))
                output["context_chars"] = len(output["packet"])
                output["context_tokens"] = len(
                    tokenizer.encode(output["packet"], disallowed_special=())
                )
                output["unanswerable_questions"] = gold.get("unanswerable_questions", [])
            record["cases"][data["id"]] = {
                "kind": data["kind"],
                "task_sha256": hashlib.sha256((case / "task.json").read_bytes()).hexdigest(),
                "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
                "documents": {p: d.digest for p, d in docs.items()},
                "judgments": [asdict(j) for j in judgments],
                "errors": errors,
                "usage": usage,
                "outputs": outputs,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            summary = {
                k: {"recall": round(v["recall"], 3), "tokens": v["context_tokens"]}
                for k, v in outputs.items()
            }
            print(data["id"], json.dumps(summary), flush=True)
    totals = {}
    for arm in [
        "baseline_snippets",
        "baseline_full",
        "all_sources",
        "ranges",
        "supplement",
        "combined",
        "advisory",
    ]:
        if arm not in next(iter(record["cases"].values()))["outputs"]:
            continue
        values = [c["outputs"][arm] for c in record["cases"].values()]
        n = sum(v["obligations"] for v in values)
        hits = sum(len(v["covered"]) for v in values)
        totals[arm] = {
            "covered": hits,
            "obligations": n,
            "micro_recall": hits / n if n else 1,
            "all_critical_tasks": sum(v["all_critical"] for v in values),
            "tasks": len(values),
            "context_tokens": sum(v["context_tokens"] for v in values),
        }
    record["aggregate"] = totals
    record["finished_at_unix"] = time.time()
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
