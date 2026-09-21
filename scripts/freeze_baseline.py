"""Fixed BM25 baseline from request/questions and source text, never gold labels."""

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from jev_context.sources import read_document

ROOT = Path(__file__).resolve().parents[1] / "benchmarks"


def terms(text):
    words = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*|[가-힣]+", text.lower())
    # Korean spacing is not a morphological tokenizer; character bigrams improve recall.
    return [
        part
        for word in words
        for part in (
            [word] + [word[i : i + 2] for i in range(len(word) - 1)]
            if re.search("[가-힣]", word)
            else [word]
        )
    ]


def main():
    for p in sorted(ROOT.glob("cases/*/task.json")):
        case = p.parent
        output = case / "baseline.json"
        if output.exists():
            continue
        task = json.loads(p.read_text())
        query = set(terms(task["request"] + " " + " ".join(q["text"] for q in task["questions"])))
        blocks = [
            (doc.path, b)
            for path in task["candidates"]
            for doc in [read_document(case / "corpus", path)]
            for b in doc.blocks
        ]
        counts = [Counter(terms(b.text)) for _, b in blocks]
        lengths = [sum(c.values()) for c in counts]
        average = sum(lengths) / len(lengths)
        dfs = Counter(t for c in counts for t in c)
        scores = []
        for (path, block), c, length in zip(blocks, counts, lengths):
            score = sum(
                math.log(1 + (len(blocks) - dfs[t] + 0.5) / (dfs[t] + 0.5))
                * c[t]
                * 2.2
                / (c[t] + 1.2 * (0.25 + 0.75 * length / average))
                for t in query
                if c[t]
            )
            scores.append((score, path, block))
        scores.sort(key=lambda x: (-x[0], x[1], x[2].start))
        # Three file shortlist, two best matching blocks from each selected file.
        paths = list(dict.fromkeys(path for _, path, _ in scores))[:3]
        selected = []
        for path in paths:
            for score, _, b in [s for s in scores if s[1] == path][:2]:
                selected.append(
                    {
                        "path": path,
                        "start_line": b.start,
                        "end_line": b.end,
                        "reason": "fixed BM25 top blocks",
                        "score": score,
                    }
                )
        value = {
            "method": "BM25, k1=1.2, b=0.75, three files/two blocks each; not an agent baseline",
            "task_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "paths": paths,
            "selected": selected,
        }
        output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print("Fixed baseline written without consulting gold")


if __name__ == "__main__":
    main()
