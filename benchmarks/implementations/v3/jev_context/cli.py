from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import Advisor, Policy
from .models import Excerpt, Task
from .provider import JevJudge
from .sources import read_document


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Suggest verifiable source ranges before an agent reads"
    )
    parser.add_argument("task", type=Path, help="Task JSON with request, questions and candidates")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--agent-picks", type=Path, help="JSON list of original read paths")
    parser.add_argument(
        "--agent-ranges", type=Path, help="JSON list of planned {path,start,end} ranges"
    )
    parser.add_argument("--model", default="jev-1.13.0")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--max-chars", type=int, default=24000)
    parser.add_argument(
        "--mode", choices=["advisory", "combined", "ranges", "supplement"], default="advisory"
    )
    parser.add_argument(
        "--json", action="store_true", help="Structured advice instead of a text packet"
    )
    parser.add_argument(
        "--inspect", action="store_true", help="List local candidate ranges; make no API calls"
    )
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.task.read_text())
        task = Task.from_dict(data)
        if args.inspect:
            rows = []
            for path in data["candidates"]:
                doc = read_document(args.root, path)
                rows.append(
                    {
                        "path": path,
                        "sha256": doc.digest,
                        "chars": len(doc.text),
                        "blocks": [
                            {"id": b.id, "start": b.start, "end": b.end} for b in doc.blocks
                        ],
                    }
                )
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        picks = json.loads(args.agent_picks.read_text()) if args.agent_picks else []
        planned = None
        if args.agent_ranges:
            from .sources import source_lines

            planned = []
            for item in json.loads(args.agent_ranges.read_text()):
                d = read_document(args.root, item["path"])
                start, end = item["start"], item["end"]
                if not 1 <= start <= end <= len(source_lines(d.text)):
                    raise ValueError("Invalid planned range")
                planned.append(
                    Excerpt(
                        d.path,
                        d.digest,
                        start,
                        end,
                        "".join(source_lines(d.text)[start - 1 : end]),
                        reasons=("original_read",),
                    )
                )
        with JevJudge(model=args.model, cache=args.cache) as judge:
            advice = Advisor(args.root, judge, Policy(max_context_chars=args.max_chars)).advise(
                task, data["candidates"], agent_picks=picks, mode=args.mode, original_ranges=planned
            )
        print(
            json.dumps(advice.to_dict(), ensure_ascii=False, indent=2)
            if args.json
            else advice.render(),
            end="\n",
        )
        return 2 if advice.errors else 0
    except (ValueError, KeyError, OSError) as e:
        print(f"Invalid input or budget: {type(e).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
