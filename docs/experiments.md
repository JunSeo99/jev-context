# Experiments: what worked and what failed

Date: 2026-09-21. Jev model: `jev-1.13.0`. This is an experimental evidence-advice library. **The experiments do not establish that it improves a strong coding agent or safely compresses its context.**

## Evaluation

Eight original synthetic development tasks and eight private real-world tasks were evaluated. Labels specify facts/constraints and exact supporting quotes, with alternative sufficient sources and conjunctive multi-source requirements. Labels were frozen before Jev outputs. See [protocol and limitations](../benchmarks/PROTOCOL.md).

The public baseline is fixed BM25 retrieval, not an agent. The private baseline was prepared with ordinary filename, grep and numbered-snippet reading by an agent independent of the implementation. That agent formulated code tasks from historical commit motivations and diff statistics. It then froze baseline choices before writing gold. It was not a separate blind gold reviewer; its final review was interrupted by an account usage limit. The parent checked quote validity but did not rewrite labels to favor output.

All packet sizes below use `cl100k_base`, a comparison tokenizer. They include source headers and diagnostics. Source coverage is not final implementation correctness, and finding one candidate answer does not mean a question is completely resolved.

## Development results

| Condition | Required evidence covered | Complete critical tasks | Packet tokens, total |
|---|---:|---:|---:|
| BM25 snippets | 15/41 | 0/8 | 6,940 |
| v1 replacement | 37/41 | 4/8 | 10,849 |
| v2 replacement | 41/41 | 8/8 | 12,074 |
| v3 protected advisory | 41/41 | 8/8 | 10,872 |
| All sources, coverage ceiling | 41/41 | 8/8 | 13,104 |

v1 missed configuration state, broadly applicable access rules, and a current-state note split from a policy. v2 lowered the evidence/constraint thresholds from 0.60/0.70 to 0.45/0.30, kept selected small sources whole, and merged adjacent spans. Those changes recovered the development facts, but they were tuned on these tasks. They are not a fresh test result.

v3 needs 17.0% fewer packet tokens than reading this entire small synthetic corpus. It needs 56.7% more than the incomplete BM25 snippets. Neither comparison proves an improvement over a frontier agent.

## External result: replacement failed

| Condition | Required evidence covered | Complete critical tasks | Packet tokens, total |
|---|---:|---:|---:|
| Independent agent snippets | 51/56 | 4/8 | 31,814 |
| Same selected files in full | 52/56 | 5/8 | 55,162 |
| v2 replacement | 37/56 | 1/8 | 68,337 |
| v3 protected advisory | 51/56 | 4/8 | 45,546 |

v2 lost code dependencies and qualifications while adding many broadly related documents. It failed both desired directions against the strong snippet baseline: lower evidence recall and larger packets. Its development success did not transfer.

v3 repairs the destructive behavior by preserving every original planned source range. Supplements receive a separate 4,000-character budget. Original ranges are never evicted to fit a supplement; an impossible base budget is rejected explicitly. Overlapping spans merge without duplicating their text.

This repair preserved the baseline's 51/56 coverage but **recovered none of the five remaining obligations**, while adding 43.2% packet tokens. Therefore the current external results do not justify automatic supplementation either. The tool should remain an explicitly invoked research/advice component. v3 was designed after observing the v2 failures and its external numbers are regression results, not held-out validation.

The remaining misses concern a multi-part discovery/archive contract, an upstream paragraph splitter's unbounded-token edge case, an amendment that retained an older publication control, and a newer consent implementation plus its conflicting preference rule. Some relevant blocks scored highly but lost under the supplement budget; other dependencies scored low. Raising thresholds alone does not solve either problem.

The entire private candidate set contains very large lockfiles. Comparing with that multi-million-token ceiling would exaggerate savings, so it is not used as an operational baseline here. Private raw queries, documents, paths, quotes and traces are omitted from this repository. Anonymous numerical exports are included.

## Engineering failures repaired

- Malformed cache entries could crash inference, and invalid live probabilities could poison cache. Container shape, exact question keys, finite probabilities and pinned model are now checked before reuse/write.
- Markdown fence parsing accepted the wrong fence character/length. Fence type and minimum closing length are tracked.
- Python `splitlines()` treated Unicode separators inside source literals as editor newlines. Source coordinates now use LF lines while preserving CRLF bytes.
- Automatic replacement could delete original evidence. The default `advisory` path protects original ranges and bounds additions; failed research modes are explicit opt-ins.
- Small-source fragmentation lost qualifications and repeated headers could cost more than the source. Research modes preserve short sources and adjacent ranges coalesce.
- Configuration examples were excluded with live environment files, making one legitimate planned range unavailable. Explicit `.env.example`/`.env.sample` candidates are supported, while real environment files remain excluded.
- Sources can change during inference. Hashes and exact ranges are verified; stale excerpts are removed and surfaced as errors. Callers can verify again immediately before later consumption.
- API failure and unreadable/oversized sources stay unscored and explicit. No tail truncation or conversion of failures to a low relevance score occurs.

Offline regression tests cover these behaviors, exact multi-source evidence scoring, path containment, source freshness and protected-range budgets. The first independent review supplied 30 tests plus subcases; subsequent protected-range and evaluator tests extend them.

## Inference accounting

The first development inference used 130,860 input tokens over 56 successful requests. The external inference used 6,613,861 input tokens over 1,003 successful requests. Supporting configuration examples added 14,568 tokens in five requests; the remaining 1,003 were cache hits during the repair run.

At the documented $0.042/M input-token price, those measured Jev calls total approximately **$0.284**. This excludes independent generative-answer/grading calls. The sum of external case scoring times was 139.9 seconds; this is not a p95 latency benchmark. A large scan's throughput and request count remain real constraints even when its dollar cost is small. [TypeSafe model specification](https://docs.typesafe.ai/models).

## Downstream decision QA

The public development packets are also evaluated by fresh, tool-free Claude CLI sessions. Each answering session receives one request and one packet, with no gold labels or other conditions. A separate call grades anonymized answers against frozen concepts and the full source corpus. Full-corpus access is necessary for the grader: rubric quotes alone are insufficient to judge whether extra claims are unsupported.

| Condition | Expected answer concepts covered |
|---|---:|
| BM25 snippet answers | 13/37 |
| Protected advisory answers | 36/37 |

The observed CLI usage records name `claude-fable-5-1` and `claude-opus-5[1m]`; no model override was supplied. The kept answer/grading calls report approximately $2.70 in usage. Exploratory discarded grading and a timed-out review are additional, so this is not the total account bill.

Unsupported-claim counts are deliberately not used as hallucination rates. On inspection, the grader sometimes mislabeled honest statements about missing *provided* evidence when the answer existed elsewhere in the full corpus. The concept-coverage metric gives missing concepts no credit without calling those abstentions fabricated. Raw grading explanations remain inspectable; a single model grader is not ground truth.

Raw sanitized responses, observed model IDs, costs, grading explanations and the aggregate are in [downstream results](../benchmarks/results/downstream/). The grader is a model, the answering/grading services are not an independent human panel, and this is the same synthetic development set. These checks measure grounded decision answers, not execution of code changes or production task success.

## Reproduction and next research question

The original recorded Jev judgments are shipped with the public fixtures. Replay changes selection policy without another API call. Hash-verified v1/v2/v3 implementation snapshots preserve historical behavior. Fresh calls are opt-in and may vary with service behavior.

The next performance question is whether task-specific dependency expansion and explicit novelty checks can recover evidence missed by a strong agent without adding low-value material. That needs newly frozen tasks and an end-to-end agent benchmark. This release does not claim that unresolved research problem is solved.
