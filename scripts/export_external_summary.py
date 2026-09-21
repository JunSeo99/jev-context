"""Export aggregate private evaluation statistics without source text or task names."""

import hashlib
import json
from collections import Counter
from pathlib import Path


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    result = {
        "schema_version": 1,
        "source_sha256": data["source_sha256"],
        "policy": data["policy"],
        "tokenizer": data["tokenizer"],
        "aggregate": data["aggregate"],
        "cases": [],
        "raw_artifact_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "limitations": [
            "Raw private sources, queries, quotes and paths are intentionally omitted.",
            "Evidence selection only; no claims of executed code correctness.",
            "Independent author used historical commit messages and diff statistics for code-task formulation.",
            "Baseline frozen before gold by same independent preparation agent; not an independent second gold rater.",
            "Final label review was interrupted by an account usage limit. Exact quoted evidence was validated locally.",
            "v3 is a post-evaluation repair on these cases, not a fresh held-out performance estimate.",
        ],
    }
    for i, c in enumerate(data["cases"].values(), 1):
        result["cases"].append(
            {
                "id": f"external-{i:02d}",
                "kind": c["kind"],
                "candidate_count": len(c["documents"]),
                "error_counts": dict(Counter(e["kind"] for e in c["errors"])),
                "usage": c["usage"],
                "outputs": {
                    arm: {
                        k: o[k]
                        for k in [
                            "recall",
                            "obligations",
                            "all_critical",
                            "context_tokens",
                            "context_chars",
                        ]
                    }
                    for arm, o in c["outputs"].items()
                },
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("Exported numeric statistics only:", args.output)


if __name__ == "__main__":
    main()
