from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Question:
    id: str
    text: str


@dataclass(frozen=True)
class Task:
    request: str
    scope: str | dict[str, Any] | list[str]
    next_action: str
    questions: tuple[Question, ...]
    hypotheses: tuple[str, ...] = ()
    known_facts: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.request, str) or not self.request.strip() or not self.questions:
            raise ValueError("A request and at least one evidence question are required")
        if not isinstance(self.next_action, str) or not isinstance(self.scope, (str, dict, list)):
            raise ValueError("Invalid task action or scope")
        if any(
            not isinstance(q, Question) or not isinstance(q.id, str) or not isinstance(q.text, str)
            for q in self.questions
        ):
            raise ValueError("Questions must have string IDs and text")
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)) or any(not x or ":" in x for x in ids):
            raise ValueError("Question IDs must be unique, nonempty and contain no colon")
        if any(not q.text.strip() for q in self.questions):
            raise ValueError("Evidence questions must have text")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Task:
        return cls(
            request=value["request"],
            scope=value.get("scope", ""),
            next_action=value.get("next_action", value["request"]),
            questions=tuple(Question(**q) for q in value["questions"]),
            hypotheses=tuple(value.get("hypotheses", [])),
            known_facts=tuple(value.get("known_facts", [])),
        )

    def state(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Block:
    id: str
    start: int
    end: int
    text: str
    heading: str = ""


@dataclass(frozen=True)
class Document:
    path: str
    digest: str
    text: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Judgment:
    path: str
    block_id: str
    answers: dict[str, float]
    constraint: float = 0.0
    conflict: float = 0.0

    def __post_init__(self):
        for value in [*self.answers.values(), self.constraint, self.conflict]:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("Judgments must be finite probabilities in [0, 1]")


@dataclass(frozen=True)
class Excerpt:
    path: str
    digest: str
    start: int
    end: int
    text: str
    questions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    score: float = 0.0


@dataclass
class Advice:
    excerpts: list[Excerpt]
    original_reads: list[str]
    unresolved: list[str]
    errors: list[dict[str, str]]
    deferred: list[str]
    usage: dict[str, Any] = field(default_factory=dict)
    candidate_count: int = 0

    def render(self) -> str:
        """The complete agent-visible packet; budgets include its metadata."""
        lines = ["Context advice (verify sources; original reads remain available)."]
        if self.original_reads:
            lines.append("Original reads: " + ", ".join(self.original_reads))
        if self.unresolved:
            lines.append("Unresolved evidence questions: " + ", ".join(self.unresolved))
        if self.errors:
            lines.append(
                "Unscored sources: " + "; ".join(f"{e['path']} ({e['kind']})" for e in self.errors)
            )
        if self.deferred:
            lines.append("Deferred sources (budget): " + ", ".join(self.deferred))
        for e in self.excerpts:
            lines.append(
                f"\n--- {e.path}:{e.start}-{e.end} sha256={e.digest} "
                f"questions={','.join(e.questions)} reasons={','.join(e.reasons)} ---\n{e.text}"
            )
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
