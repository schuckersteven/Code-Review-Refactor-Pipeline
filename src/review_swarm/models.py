"""
Shared data models for findings, refactoring steps, and review plans.

These models form the persisted contract between analysis, planning, code
generation, human approval, and patch execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """
    Risk level used to prioritize synthesized review findings.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Finding:
    """
    An immutable issue reported by one specialized review agent.

    Attributes:
        id: Stable identifier derived from the issue location and rule.
        dimension: Review category such as security, performance, or style.
        severity: Risk level used for ordering and prioritization.
        path: Repository-relative source path, or ``"."`` for a global issue.
        line: One-based source line associated with the issue.
        title: Concise description of the detected issue.
        evidence: Bounded source excerpt or summary supporting the finding.
        recommendation: Suggested remediation for the issue.
    """

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
    """
    One dependency-aware, human-approved unit of refactoring work.

    ``depends_on`` lists steps that must be applied first. ``approved`` is
    bound to the exact generated ``patch`` through ``approved_patch_sha256``;
    regenerating or editing a patch therefore requires renewed approval.
    """

    id: str
    title: str
    rationale: str
    finding_ids: list[str]
    files: list[str]
    depends_on: list[str] = field(default_factory=list)
    approved: bool = False
    applied: bool = False
    patch: str | None = None
    approved_patch_sha256: str | None = None


@dataclass
class ReviewPlan:
    """
    A repository review containing synthesized findings and ordered steps.
    """

    repository: str
    findings: list[Finding]
    steps: list[RefactorStep]

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of the complete plan."""

        return {
            "repository": self.repository,
            "findings": [asdict(f) for f in self.findings],
            "steps": [asdict(s) for s in self.steps],
        }
