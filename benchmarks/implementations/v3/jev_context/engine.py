from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from .models import Advice, Document, Excerpt, Judgment, Task
from .provider import Batch, Judge, ProviderError
from .sources import read_document, source_lines, verify_excerpt


@dataclass(frozen=True)
class Policy:
    evidence_threshold: float = 0.45
    constraint_threshold: float = 0.30
    conflict_threshold: float = 0.65
    max_context_chars: int = 24_000
    block_chars: int = 2400
    workers: int = 4
    short_source_chars: int = 1600
    max_extra_chars: int = 4000

    def __post_init__(self):
        if self.max_context_chars < 1024 or self.block_chars < 100 or self.workers < 1:
            raise ValueError("Invalid context budget, block size or worker count")
        if any(
            not 0 <= p <= 1
            for p in (self.evidence_threshold, self.constraint_threshold, self.conflict_threshold)
        ):
            raise ValueError("Thresholds must be in [0,1]")


class Advisor:
    def __init__(self, root: Path, judge: Judge, policy: Policy | None = None):
        self.root, self.judge, self.policy = Path(root), judge, policy or Policy()

    def score(self, task: Task, candidates: list[str]):
        """One candidate document per worker. No agent picks or gold labels enter inference."""
        started = time.perf_counter()
        before = self.judge.stats() if hasattr(self.judge, "stats") else None
        docs: dict[str, Document] = {}
        errors = []
        for path in dict.fromkeys(candidates):
            try:
                docs[path] = read_document(self.root, path, block_chars=self.policy.block_chars)
            except ValueError as e:
                errors.append({"path": path, "kind": str(e)})

        def run(doc):
            try:
                return self.judge.evaluate(task, doc), None
            except Exception as e:
                safe_codes = {
                    "block_too_large",
                    "request_too_large",
                    "invalid_probabilities",
                    "install_live_extra",
                    "client_configuration",
                }
                code = str(e)
                safe = isinstance(e, ProviderError) and (
                    code in safe_codes or re.fullmatch(r"api_(?:\d{3}|failure)", code)
                )
                return Batch([]), {"path": doc.path, "kind": code if safe else type(e).__name__}

        batches = []
        with ThreadPoolExecutor(max_workers=self.policy.workers) as pool:
            for batch, error in pool.map(run, docs.values()):
                batches.append(batch)
                if error:
                    errors.append(error)
        judgments = [j for b in batches for j in b.judgments]
        usage = {
            "input_tokens": sum(b.input_tokens for b in batches),
            "requests": sum(b.requests for b in batches),
            "cache_hits": sum(b.cache_hits for b in batches),
            "models": sorted({b.model for b in batches if b.model}),
            "seconds": round(time.perf_counter() - started, 3),
        }
        if before is not None:
            after = self.judge.stats()
            usage.update({k: after[k] - before[k] for k in before})
        return docs, judgments, errors, usage

    def select(
        self,
        task: Task,
        docs: dict[str, Document],
        judgments: list[Judgment],
        *,
        agent_picks: list[str] | None = None,
        errors=None,
        usage=None,
        mode: str = "combined",
        original_ranges: list[Excerpt] | None = None,
    ) -> Advice:
        if mode == "advisory":
            return self._advisory(
                task, docs, judgments, agent_picks or [], original_ranges, errors or [], usage or {}
            )
        if mode not in {"combined", "ranges", "supplement"}:
            raise ValueError("mode must be advisory, combined, ranges or supplement")
        picks = list(dict.fromkeys(agent_picks or []))
        errors = list(errors or [])
        for path in picks:
            if path not in docs and not any(e["path"] == path for e in errors):
                errors.append({"path": path, "kind": "not_in_candidates"})
        p = self.policy
        options = []
        for j in judgments:
            if mode == "ranges" and j.path not in picks:
                continue
            if j.path not in docs:
                raise ValueError("Judgment refers to an unknown document")
            doc = docs[j.path]
            block = next((b for b in doc.blocks if b.id == j.block_id), None)
            if block is None or set(j.answers) != {q.id for q in task.questions}:
                raise ValueError("Judgment has an unknown block or missing questions")
            hits = tuple(q for q, v in j.answers.items() if v >= p.evidence_threshold)
            reasons = []
            if hits:
                reasons.append("evidence")
            if j.constraint >= p.constraint_threshold:
                reasons.append("constraint")
            if j.conflict >= p.conflict_threshold:
                reasons.append("conflict")
            if reasons:
                options.append(
                    Excerpt(
                        j.path,
                        doc.digest,
                        block.start,
                        block.end,
                        block.text,
                        hits,
                        tuple(reasons),
                        max(*j.answers.values(), j.constraint, j.conflict),
                    )
                )

        # Short sources often split a rule, its qualifier, and a current status into
        # separate paragraphs. Keep the complete small source once any span qualifies.
        # Merge adjacent longer spans to avoid repeated source-header overhead.
        coalesced = []
        for path in sorted({e.path for e in options}):
            group = sorted((e for e in options if e.path == path), key=lambda e: e.start)
            doc = docs[path]
            if len(doc.text) <= p.short_source_chars:
                coalesced.append(
                    Excerpt(
                        path,
                        doc.digest,
                        1,
                        len(source_lines(doc.text)),
                        doc.text,
                        tuple(sorted({q for e in group for q in e.questions})),
                        tuple(sorted({r for e in group for r in e.reasons} | {"short_source"})),
                        max(e.score for e in group),
                    )
                )
                continue
            merged = []
            for item in group:
                if merged and item.start <= merged[-1].end + 1:
                    previous = merged.pop()
                    end = max(previous.end, item.end)
                    merged.append(
                        Excerpt(
                            path,
                            doc.digest,
                            previous.start,
                            end,
                            "".join(source_lines(doc.text)[previous.start - 1 : end]),
                            tuple(sorted(set(previous.questions) | set(item.questions))),
                            tuple(sorted(set(previous.reasons) | set(item.reasons))),
                            max(previous.score, item.score),
                        )
                    )
                else:
                    merged.append(item)
            coalesced.extend(merged)
        options = coalesced

        # Preserve original reads when the scoring service fails or finds no span.
        for path in picks:
            if path in docs and (mode == "supplement" or not any(e.path == path for e in options)):
                doc = docs[path]
                options = [e for e in options if e.path != path]
                options.append(
                    Excerpt(
                        path,
                        doc.digest,
                        1,
                        len(source_lines(doc.text)),
                        doc.text,
                        (),
                        ("original_read",),
                        1.0,
                    )
                )

        advice = Advice(
            [], picks, [q.id for q in task.questions], errors, [], usage or {}, len(docs)
        )
        if len(advice.render()) > p.max_context_chars:
            raise ValueError(
                "Budget cannot hold advice metadata; reduce candidates or increase budget"
            )
        covered = set()
        remaining = options[:]
        while remaining:
            remaining.sort(
                key=lambda e: (
                    -(
                        len(set(e.questions) - covered) * 2
                        + ("conflict" in e.reasons)
                        + ("constraint" in e.reasons)
                        + ("original_read" in e.reasons)
                    ),
                    -e.score,
                    len(e.text),
                    e.path,
                    e.start,
                )
            )
            item = remaining.pop(0)
            trial_covered = covered | set(item.questions)
            trial = replace(
                advice,
                excerpts=advice.excerpts + [item],
                unresolved=[q.id for q in task.questions if q.id not in trial_covered],
            )
            if len(trial.render()) <= p.max_context_chars:
                advice, covered = trial, trial_covered
            else:
                advice.deferred = sorted(set(advice.deferred) | {item.path})
        # Reserve the warning text too; a deferred list may have grown afterwards.
        while advice.excerpts and len(advice.render()) > p.max_context_chars:
            removed = advice.excerpts.pop()
            advice.deferred = sorted(set(advice.deferred) | {removed.path})
        covered = {q for e in advice.excerpts for q in e.questions}
        advice.unresolved = [q.id for q in task.questions if q.id not in covered]
        if len(advice.render()) > p.max_context_chars:
            raise ValueError("Budget cannot hold explicit unresolved/deferred metadata")
        return advice

    def _advisory(self, task, docs, judgments, picks, original_ranges, errors, usage):
        """Protected baseline plus a bounded supplement. Never shrink a caller's plan."""
        original = list(original_ranges or [])
        if original_ranges is None:
            for path in dict.fromkeys(picks):
                if path in docs:
                    d = docs[path]
                    original.append(
                        Excerpt(
                            path,
                            d.digest,
                            1,
                            len(source_lines(d.text)),
                            d.text,
                            reasons=("original_read",),
                        )
                    )
        for e in original:
            d = docs.get(e.path)
            if d is None or d.digest != e.digest:
                raise ValueError("Original range source is unavailable or changed")
            if not 1 <= e.start <= e.end <= len(source_lines(d.text)) or e.text != "".join(
                source_lines(d.text)[e.start - 1 : e.end]
            ):
                raise ValueError("Original range does not match source")

        def merge(items):
            out = []
            for e in sorted(items, key=lambda x: (x.path, x.start)):
                if out and out[-1].path == e.path and e.start <= out[-1].end + 1:
                    a = out.pop()
                    end = max(a.end, e.end)
                    out.append(
                        Excerpt(
                            e.path,
                            e.digest,
                            a.start,
                            end,
                            "".join(source_lines(docs[e.path].text)[a.start - 1 : end]),
                            tuple(sorted(set(a.questions) | set(e.questions))),
                            tuple(sorted(set(a.reasons) | set(e.reasons))),
                            max(a.score, e.score),
                        )
                    )
                else:
                    out.append(e)
            return out

        original = merge(original)
        picks = list(dict.fromkeys([*picks, *(e.path for e in original)]))
        errors = list(errors)
        for path in picks:
            if path not in docs and not any(e["path"] == path for e in errors):
                errors.append({"path": path, "kind": "not_in_candidates"})
        advice = Advice(
            original, picks, [q.id for q in task.questions], errors, [], usage, len(docs)
        )
        baseline_size = len(advice.render())
        if baseline_size > self.policy.max_context_chars:
            raise ValueError(
                "Protected original ranges exceed budget; increase it or revise the plan explicitly"
            )
        candidates = []
        covered = set()
        for j in judgments:
            d = docs.get(j.path)
            if d is None or set(j.answers) != {q.id for q in task.questions}:
                raise ValueError("Invalid judgment source or questions")
            b = next((b for b in d.blocks if b.id == j.block_id), None)
            if b is None:
                raise ValueError("Invalid judgment block")
            hits = tuple(q for q, v in j.answers.items() if v >= self.policy.evidence_threshold)
            if any(e.path == j.path and e.start <= b.start and e.end >= b.end for e in original):
                covered.update(hits)
                continue
            reasons = ["evidence"] if hits else []
            if j.constraint >= self.policy.constraint_threshold:
                reasons.append("constraint")
            if j.conflict >= self.policy.conflict_threshold:
                reasons.append("conflict")
            if reasons:
                candidates.append(
                    Excerpt(
                        j.path,
                        d.digest,
                        b.start,
                        b.end,
                        b.text,
                        hits,
                        tuple(reasons),
                        max(*j.answers.values(), j.constraint, j.conflict),
                    )
                )
        # Marginal ranges, not whole-file replacements. Exact overlaps merge in the
        # packet; original ranges remain a subset under every threshold and budget.
        limit = min(self.policy.max_context_chars, baseline_size + self.policy.max_extra_chars)
        deferred = set()
        while candidates:
            candidates.sort(
                key=lambda e: (
                    -(
                        len(set(e.questions) - covered)
                        + 0.5 * ("conflict" in e.reasons)
                        + 0.25 * ("constraint" in e.reasons)
                        + e.score
                    )
                    / (max(len(e.text), 100) ** 0.5),
                    e.path,
                    e.start,
                )
            )
            item = candidates.pop(0)
            trial_covered = covered | set(item.questions)
            trial = replace(
                advice,
                excerpts=merge(advice.excerpts + [item]),
                unresolved=[q.id for q in task.questions if q.id not in trial_covered],
            )
            # Reserve a bounded deferred-warning line, avoiding removal of originals.
            if len(trial.render()) + 96 <= limit:
                advice, covered = trial, trial_covered
            else:
                deferred.add(item.path)
        if deferred:
            advice.deferred = [
                f"{len(deferred)} source(s); inspect structured scores or expand budget"
            ]
        advice.unresolved = [q.id for q in task.questions if q.id not in covered]
        if len(advice.render()) > limit:
            # Only possible when even warning metadata does not fit: no silent drop.
            raise ValueError("Budget cannot hold protected ranges and explicit warnings")
        return advice

    def advise(
        self,
        task: Task,
        candidates: list[str],
        *,
        agent_picks=None,
        mode="advisory",
        original_ranges=None,
    ):
        docs, judgments, errors, usage = self.score(task, candidates)
        advice = self.select(
            task,
            docs,
            judgments,
            agent_picks=agent_picks,
            errors=errors,
            usage=usage,
            mode=mode,
            original_ranges=original_ranges,
        )
        # Detect edits during inference before returning the excerpts.
        valid = []
        for e in advice.excerpts:
            try:
                verify_excerpt(self.root, e)
                valid.append(e)
            except ValueError:
                advice.errors.append({"path": e.path, "kind": "source_changed"})
        advice.excerpts = valid
        covered = {q for e in valid for q in e.questions}
        advice.unresolved = [q.id for q in task.questions if q.id not in covered]
        return advice
