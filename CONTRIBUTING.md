# Contributing

Install `.[live,eval,dev]` in a virtual environment. Offline tests must not require credentials or call TypeSafe. Run `pytest -q`, `ruff check src scripts tests`, `ruff format --check src scripts tests`, and `python -m build` before submitting a change.

Keep source parsing and policy separate from model calls. Every excerpt must retain a source hash and exact editor-style LF line coordinates. Do not silently truncate, convert API failures into zero scores, or put source bodies into error logs.

For an experiment, author task requirements and exact supporting quotes before seeing model output. Include alternate sufficient sources and multi-source requirements. Freeze tasks, corpus, labels and baseline with hashes. Tune on development data; report subsequent evaluation separately. Never relabel a miss as irrelevant just because the system omitted it.

The current benchmark measures evidence selection, not completed software changes. A new downstream evaluation should run the task using only each condition's packet and independently assess the resulting answer or implementation. Do not call lexical retrieval an agent baseline.

Use original or appropriately licensed fixtures. Do not contribute organization documents, API keys, raw private traces, or personal data. All code and original benchmark fixtures in this repository are offered under the MIT license.

