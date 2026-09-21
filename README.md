# jev-context

Source-grounded context advice for coding and document agents, using [TypeSafe Jev](https://docs.typesafe.ai/concepts/system-one).

Jev reads candidate sources outside the agent's conversation. This package returns exact source ranges, potential constraints, contrary evidence, and questions without matching evidence. The calling agent decides what to read. Source hashes make excerpts verifiable.

**Experimental, advisory API.** In the real-world evaluation, automatic range replacement lost evidence. The default now preserves the caller's planned ranges and bounds supplementary context. It preserved baseline recall but did not improve it on those eight tasks. Do not enable automatic context replacement on the strength of the synthetic results. This is an independent project, not an official TypeSafe SDK. It does not generate summaries, discover all necessary files, or guarantee sufficient context. The repository is prepared under MIT; a private GitHub repository is not a public release.

## Install and try

Python 3.10 or later. Clone this repository, then:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[live,eval,dev]'

# Inspect local ranges without sending anything to an API.
jev-context benchmarks/cases/case-001/task.json \
  --root benchmarks/cases/case-001/corpus --inspect

# Supply your TypeSafe key through the environment, then run live inference.
export TYPESAFE_API_KEY='<your-key>'
jev-context benchmarks/cases/case-001/task.json \
  --root benchmarks/cases/case-001/corpus --cache .cache/jev
```

The core has no third-party dependencies. The `live` extra installs the official SDK; `eval` installs the comparison tokenizer. Installing the core alone supports source parsing, custom providers, selection and offline use.

## Supply a task

```json
{
  "request": "Add attachment uploads to the workspace editor",
  "scope": "Workspace attachment upload endpoint",
  "next_action": "Implement validation before accepting the request body",
  "questions": [
    {"id": "access", "text": "Who is allowed to upload?"},
    {"id": "limits", "text": "Which size and file-type limits apply?"}
  ],
  "hypotheses": ["All authenticated workspace members may upload"],
  "known_facts": [],
  "candidates": ["docs/uploads.md", "src/uploads.py", "config/uploads.yaml"]
}
```

Questions are supplied by the caller, not automatically generated. Keep the original request, confirmed facts and hypotheses separate. Candidates come from existing grep, search, imports or project rules. A source outside that set cannot be recovered by this tool.

An optional `--agent-picks picks.json` accepts a JSON array of original read paths. These choices do not enter Jev's scoring prompt. They are compared afterward in Python.

For precise plans, use `--agent-ranges ranges.json` with `[{"path":"src/uploads.py","start":12,"end":48}]`. Coordinates are inclusive and one-based. These exact original ranges are protected in the default mode. An impossible budget raises an explicit error instead of dropping a protected range.

| Mode | What the proposed packet contains |
|---|---|
| `advisory` (default) | Original planned ranges plus at most 4,000 extra characters; no original evidence is removed |
| `combined` | Qualified ranges across candidates; selected short sources are kept whole |
| `ranges` | Qualified ranges from the original read paths only |
| `supplement` | Whole original read sources plus qualified extra sources |

`combined`, `ranges` and `supplement` are retained for research reproduction; they can lose original evidence and are not the recommended integration. Their hard budget can defer an original read. The default `advisory` mode does not do this: reduce the caller's plan explicitly or increase the budget. Calling systems still decide how to handle unscored files, missing evidence and optional supplements.

## Use as a library

```python
from pathlib import Path
from jev_context import Advisor, Policy, Task
from jev_context.provider import JevJudge
from jev_context.sources import verify_excerpt

task = Task.from_dict(task_json)
with JevJudge(model="jev-1.13.0", cache=Path(".cache/jev")) as judge:
    advice = Advisor(Path("project"), judge, Policy()).advise(
        task, candidates, agent_picks=["src/uploads.py"]
    )

packet = advice.render()
for excerpt in advice.excerpts:
    verify_excerpt(Path("project"), excerpt)  # Repeat immediately before later reads.
```

Only `Advice.render()` is the bounded agent-visible packet. `--json` exposes structured diagnostics and is not constrained to the same serialized size. Budgets are **characters**, including source headers and warning metadata; they are not advertised as exact model tokens. The benchmark measures full packets using `cl100k_base` as a fixed comparison tokenizer, not Jev's tokenizer.

## Behavior and limits

- A request evaluates one candidate document, or contiguous windows when necessary, with independent questions for each block. No golden labels or original read decisions enter inference.
- Multiple evidence blocks can survive for the same question. Adjacent ranges merge. Research replacement modes keep selected sources up to 1,600 characters whole; the default preserves the original plan and adds bounded ranges instead.
- Default evidence/constraint/conflict thresholds are 0.45/0.30/0.65. The first two were selected on the included development fixtures, then frozen before external validation. These are routing settings, not universal confidence guarantees.
- `unresolved` means no retained range crossed the evidence threshold for that question. Absence from this list does **not** prove complete answer coverage or truth. Some questions require several pieces of evidence.
- File read failures, excluded sources, API errors and deferred ranges remain explicit. An oversized indivisible line or task is unscored rather than silently truncated. SDK retries cover transient service errors; the adapter splits multi-block requests on length failures.
- Paths must remain within the supplied root. Symlinks, common credential paths, binary and non-UTF-8 files are rejected. Explicit `.env.example` and `.env.sample` candidates are allowed as configuration templates; make sure they contain no real credentials. These exclusions are practical defaults, not comprehensive secret detection or a hostile-filesystem sandbox.
- API inference sends candidate source text to TypeSafe. Its [current data-handling terms](https://docs.typesafe.ai/models#data-handling) apply. Local response caches store numeric judgments and hashes, not source bodies or API keys.
- Cached scores include the complete task, question definition, source hash, model and prompt version in the cache key. Versioned models are required for caching. Returned source hashes are rechecked after inference.
- No MCP server or editor hook is included. This release tests the evidence-selection boundary before integrating it into an agent runtime.

## Reproduce the experiments

Read [the experiment report](docs/experiments.md) before interpreting the numbers. The public fixtures are synthetic and have authored task decompositions. Private real-world source material is not included.

```sh
# Development baseline and original Jev judgments are included; no API required.
PYTHONPATH=src python scripts/evaluate.py --suite benchmarks --split dev \
  --output /tmp/jev-replay.json --cache .cache/jev \
  --replay benchmarks/results/v1-dev.json

# Fresh inference; charged by TypeSafe.
PYTHONPATH=src python scripts/evaluate.py --suite benchmarks --split dev \
  --output /tmp/jev-live.json --cache .cache/jev-live

pytest -q
ruff check src scripts tests
python -m build
```

The `benchmarks/implementations/v1` snapshot is byte-for-byte verified against the source fingerprint recorded in the first run. Use it as `PYTHONPATH` to reproduce v1 selection. Compare stored original judgments with replayed selection separately from fresh model calls; thresholds and selection policy can change without repeating inference.

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md). New failure cases with source quotes are particularly useful. Preserve frozen labels and report unsuccessful cases alongside successful ones.
