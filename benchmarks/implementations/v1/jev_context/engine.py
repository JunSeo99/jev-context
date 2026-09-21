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
    evidence_threshold: float = 0.60
    constraint_threshold: float = 0.70
    conflict_threshold: float = 0.65
    max_context_chars: int = 24_000
    block_chars: int = 2400
    workers: int = 4

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
    ) -> Advice:
        if mode not in {"combined", "ranges", "supplement"}:
            raise ValueError("mode must be combined, ranges or supplement")
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

    def advise(self, task: Task, candidates: list[str], *, agent_picks=None, mode="combined"):
        docs, judgments, errors, usage = self.score(task, candidates)
        advice = self.select(
            task, docs, judgments, agent_picks=agent_picks, errors=errors, usage=usage, mode=mode
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
