from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Finding:
    id: str
    dimension: str
    severity: Severity
    path: str
    line: int
    title: str
    evidence: str
    recommendation: str


@dataclass
class RefactorStep:
    id: str
    title: str
    rationale: str
    finding_ids: list[str]
    files: list[str]
    depends_on: list[str] = field(default_factory=list)
    approved: bool = False
    applied: bool = False
    patch: str | None = None


@dataclass
class ReviewPlan:
    repository: str
    findings: list[Finding]
    steps: list[RefactorStep]

    def to_dict(self) -> dict:
        return {"repository": self.repository, "findings": [asdict(f) for f in self.findings], "steps": [asdict(s) for s in self.steps]}
