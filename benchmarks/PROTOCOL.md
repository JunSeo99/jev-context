# Evaluation protocol and provenance

Eight original development fixtures (five code, three document; English and Korean) were authored by an agent that was not shown the implementation or previous Jev outputs. It prepared `author_corpus.py` before any calls. Its usage limit interrupted the planned extra fixtures and final review. The implementation agent materialized the eight completed fixtures, validated every exact quote, and froze `freeze.json` before inference. No gold was revised to match output.

Public baseline: deterministic BM25 on request plus caller-supplied questions, selecting three files and two highest-scoring blocks per file. This is a lexical baseline, not a frontier-agent baseline. `baseline_full` reads the same three selected files in full. File selection is identical between those conditions.

The task questions are authored fixture inputs. This evaluates context advice given a decomposition; it does not test whether an agent autonomously discovers the correct questions. Golden obligations never enter inference. Each obligation has alternative sufficient evidence sets; every quote within a set is required. Coverage is exact-source-span coverage, not just a matching filename or one matching keyword. A full critical-task success requires every critical obligation.

Private external evaluation: eight independently prepared real-world tasks (five historical code changes from one repository, three document tasks from a bounded 170-document corpus). The preparation agent froze a filename/grep/snippet baseline before authoring labels. It saw commit motivations and diff statistics when formulating code requests. This is stronger than the public lexical baseline but is not a perfect simulation of a time-blind historical agent. Raw material remains outside this repository; exported summaries contain only numbers and anonymous task IDs.

v1 used thresholds 0.60/0.70 and independent selected blocks. Its missing development evidence informed v2: 0.45/0.30 thresholds, short-source retention, and adjacent-range merging. v2 was frozen before external inference. External failure then informed v3's protected original ranges and bounded supplement. Therefore v3 external results are regression results on observed cases, not an untouched test estimate.

`context_tokens` counts the whole rendered packet with `cl100k_base`. This is a fixed comparison tokenizer, not the frontier agent's or Jev's exact tokenizer. Jev's own `usage.input_tokens` is measured separately. Reported source-scoring times are elapsed case times, not p95 production latency. Replay reuses recorded judgments and must not be counted as new billed inference.

`all_sources` is a coverage ceiling, not a realistic operational baseline. In private code snapshots it includes large lockfiles, which make apparent savings against this condition misleading. Do not headline those savings.

Frozen artifacts are not rewritten when the implementation changes. The initial source snapshot is reconstructed and hash-verified against the recorded v1 fingerprint. Later source snapshots and report artifacts preserve the same distinction between recorded inference and replayed policy selection.

Optional downstream decision QA uses isolated Claude CLI processes, customization disabled, no tools, fresh sessions and an empty working directory. Each answering process receives only one task and one packet, not gold or other conditions. A separate grading call sees anonymized answers and the frozen expected concepts. Model-graded decision answers are not executed code tests and have their own grading uncertainty.
