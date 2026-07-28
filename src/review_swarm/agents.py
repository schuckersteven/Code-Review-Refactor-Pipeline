"""
Parallel rule-based agents for repository and unified-diff review.
Each agent owns one review dimension and emits structured :class:`Finding`
objects. Repository and diff entry points run all agents concurrently and
return one deterministic, severity-ordered result set.
"""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .models import Finding, Severity

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "vendor",
    "__pycache__",
}
TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rb",
    ".php",
    ".cs",
}
SEVERITY_RANK = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


@dataclass(frozen=True)
class ChangedLine:
    """
    An added source line extracted from the new side of a unified diff.
    """

    path: str
    number: int
    text: str


def source_files(root: Path) -> list[Path]:
    """
    Return supported source files while excluding vendor and build trees.
    """

    return [
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in TEXT_EXTENSIONS
        and not any(part in SKIP_DIRS for part in p.parts)
    ]


class RuleAgent:
    """
    Base reviewer that turns regular-expression rule matches into findings.
    """

    dimension = "base"
    rules: tuple[tuple[re.Pattern[str], Severity, str, str], ...] = ()

    def run(self, root: Path, files: list[Path]) -> list[Finding]:
        """
        Review complete source files and return every matching finding.
        """

        findings: list[Finding] = []
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for number, text in enumerate(lines, 1):
                for pattern, severity, title, recommendation in self.rules:
                    if pattern.search(text):
                        relative = path.relative_to(root).as_posix()
                        key = f"{self.dimension}:{relative}:{number}:{title}"
                        findings.append(
                            Finding(
                                hashlib.sha1(key.encode()).hexdigest()[:10],
                                self.dimension,
                                severity,
                                relative,
                                number,
                                title,
                                text.strip()[:240],
                                recommendation,
                            )
                        )
        return findings

    def run_lines(self, lines: list[ChangedLine]) -> list[Finding]:
        """
        Review only the added lines extracted from a pull-request diff."""

        findings: list[Finding] = []
        for line in lines:
            for pattern, severity, title, recommendation in self.rules:
                if pattern.search(line.text):
                    key = f"{self.dimension}:{line.path}:{line.number}:{title}"
                    findings.append(
                        Finding(
                            hashlib.sha1(key.encode()).hexdigest()[:10],
                            self.dimension,
                            severity,
                            line.path,
                            line.number,
                            title,
                            line.text.strip()[:240],
                            recommendation,
                        )
                    )
        return findings


class SecurityAgent(RuleAgent):
    """
    Detect high-risk code execution, credential, and shell usage patterns.
    """

    dimension = "security"
    rules = (
        (
            re.compile(r"\beval\s*\("),
            Severity.HIGH,
            "Dynamic code evaluation",
            "Replace eval with a parser or allowlisted dispatch.",
        ),
        (
            re.compile(r"(password|secret|api[_-]?key)\s*=\s*['\"][^'\"]+", re.I),
            Severity.HIGH,
            "Possible hard-coded credential",
            "Move the value to a secret manager or environment variable.",
        ),
        (
            re.compile(r"subprocess\..*shell\s*=\s*True|os\.system\("),
            Severity.HIGH,
            "Shell command injection risk",
            "Use argument arrays and validate untrusted input.",
        ),
    )


class PerformanceAgent(RuleAgent):
    """
    Flag patterns that may cause excessive CPU, memory, or I/O usage.
    """

    dimension = "performance"
    rules = (
        (
            re.compile(r"for .+ in .+:.*", re.I),
            Severity.LOW,
            "Loop requires performance review",
            "Check for repeated I/O or an avoidable nested traversal.",
        ),
        (
            re.compile(r"\.read\(\)|readFileSync"),
            Severity.MEDIUM,
            "Whole-file read",
            "Prefer streaming or bounded reads for untrusted/large files.",
        ),
    )


class StyleAgent(RuleAgent):
    """
    Report maintainability markers and formatting issues.
    """

    dimension = "style"
    rules = (
        (
            re.compile(r"\bTODO\b|\bFIXME\b", re.I),
            Severity.LOW,
            "Unresolved maintenance marker",
            "Track this work or resolve it before release.",
        ),
        (
            re.compile(r"^.{121,}$"),
            Severity.LOW,
            "Long source line",
            "Wrap the expression to improve readability.",
        ),
    )


class CoverageAgent(RuleAgent):
    """
    Identify missing tests for repositories or production-code changes.
    """

    dimension = "test_coverage"
    rules = ()

    def run(self, root: Path, files: list[Path]) -> list[Finding]:
        """
        Report a repository-level gap when production code has no tests.
        """

        tests = [
            p
            for p in files
            if any(part in {"test", "tests", "__tests__"} for part in p.parts)
            or p.name.startswith("test_")
            or p.name.endswith(".test.js")
        ]
        production = [p for p in files if p not in tests]
        if production and not tests:
            return [
                Finding(
                    "coverage-no-tests",
                    self.dimension,
                    Severity.HIGH,
                    ".",
                    1,
                    "No tests detected",
                    f"Found {len(production)} source files and no test files.",
                    "Add focused unit tests before refactoring.",
                )
            ]
        return []

    def run_lines(self, lines: list[ChangedLine]) -> list[Finding]:
        """
        Report a diff-level gap when production changes omit test changes.
        """

        paths = {line.path for line in lines}
        production = {path for path in paths if not is_test_path(path)}
        tests = {path for path in paths if is_test_path(path)}
        if production and not tests:
            return [
                Finding(
                    "coverage-diff-no-tests",
                    self.dimension,
                    Severity.MEDIUM,
                    ".",
                    1,
                    "Production changes without test changes",
                    f"The diff changes {len(production)} production file(s) and no test files.",
                    "Add or update focused tests for the changed behavior.",
                )
            ]
        return []


def is_test_path(path: str) -> bool:
    """
    Return whether a path follows a recognized test-file convention.
    """

    candidate = Path(path)
    return (
        any(part in {"test", "tests", "__tests__"} for part in candidate.parts)
        or candidate.name.startswith("test_")
        or ".test." in candidate.name
        or ".spec." in candidate.name
    )


def changed_lines(diff: str) -> list[ChangedLine]:
    """
    Return added source lines from a unified git diff with new-file line numbers.
    """

    result: list[ChangedLine] = []
    current_path: str | None = None
    new_line: int | None = None
    for raw in diff.splitlines():
        file_header = re.match(r"^\+\+\+ b/(.+)$", raw)
        if file_header:
            candidate = file_header.group(1)
            current_path = (
                candidate if Path(candidate).suffix.lower() in TEXT_EXTENSIONS else None
            )
            new_line = None
            continue
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if current_path is None or new_line is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            result.append(ChangedLine(current_path, new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            continue
        elif raw.startswith(" "):
            new_line += 1
    return result


def analyze(root: Path) -> list[Finding]:
    """
    Run all review dimensions over a repository and synthesize the results.
    """

    files = source_files(root)
    agents = [SecurityAgent(), PerformanceAgent(), StyleAgent(), CoverageAgent()]
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        batches = list(pool.map(lambda agent: agent.run(root, files), agents))
    return sorted(
        (f for batch in batches for f in batch),
        key=lambda f: (-SEVERITY_RANK[f.severity], f.path, f.line, f.id),
    )


def analyze_diff(diff: str) -> list[Finding]:
    """
    Run all review dimensions over added diff lines and synthesize results."""

    lines = changed_lines(diff)
    agents = [SecurityAgent(), PerformanceAgent(), StyleAgent(), CoverageAgent()]
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        batches = list(pool.map(lambda agent: agent.run_lines(lines), agents))
    return sorted(
        (f for batch in batches for f in batch),
        key=lambda f: (-SEVERITY_RANK[f.severity], f.path, f.line, f.id),
    )
