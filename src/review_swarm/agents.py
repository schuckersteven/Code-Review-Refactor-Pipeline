from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .models import Finding, Severity

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "vendor", "__pycache__"}
TEXT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".php", ".cs"}


def source_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS and not any(part in SKIP_DIRS for part in p.parts)]


class RuleAgent:
    dimension = "base"
    rules: tuple[tuple[re.Pattern[str], Severity, str, str], ...] = ()

    def run(self, root: Path, files: list[Path]) -> list[Finding]:
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
                        findings.append(Finding(hashlib.sha1(key.encode()).hexdigest()[:10], self.dimension, severity, relative, number, title, text.strip()[:240], recommendation))
        return findings


class SecurityAgent(RuleAgent):
    dimension = "security"
    rules = (
        (re.compile(r"\beval\s*\("), Severity.HIGH, "Dynamic code evaluation", "Replace eval with a parser or allowlisted dispatch."),
        (re.compile(r"(password|secret|api[_-]?key)\s*=\s*['\"][^'\"]+", re.I), Severity.HIGH, "Possible hard-coded credential", "Move the value to a secret manager or environment variable."),
        (re.compile(r"subprocess\..*shell\s*=\s*True|os\.system\("), Severity.HIGH, "Shell command injection risk", "Use argument arrays and validate untrusted input."),
    )


class PerformanceAgent(RuleAgent):
    dimension = "performance"
    rules = (
        (re.compile(r"for .+ in .+:.*", re.I), Severity.LOW, "Loop requires performance review", "Check for repeated I/O or an avoidable nested traversal."),
        (re.compile(r"\.read\(\)|readFileSync"), Severity.MEDIUM, "Whole-file read", "Prefer streaming or bounded reads for untrusted/large files."),
    )


class StyleAgent(RuleAgent):
    dimension = "style"
    rules = (
        (re.compile(r"\bTODO\b|\bFIXME\b", re.I), Severity.LOW, "Unresolved maintenance marker", "Track this work or resolve it before release."),
        (re.compile(r"^.{121,}$"), Severity.LOW, "Long source line", "Wrap the expression to improve readability."),
    )


class CoverageAgent(RuleAgent):
    dimension = "test_coverage"
    rules = ()

    def run(self, root: Path, files: list[Path]) -> list[Finding]:
        tests = [p for p in files if any(part in {"test", "tests", "__tests__"} for part in p.parts) or p.name.startswith("test_") or p.name.endswith(".test.js")]
        production = [p for p in files if p not in tests]
        if production and not tests:
            return [Finding("coverage-no-tests", self.dimension, Severity.HIGH, ".", 1, "No tests detected", f"Found {len(production)} source files and no test files.", "Add focused unit tests before refactoring.")]
        return []


def analyze(root: Path) -> list[Finding]:
    files = source_files(root)
    agents = [SecurityAgent(), PerformanceAgent(), StyleAgent(), CoverageAgent()]
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        batches = list(pool.map(lambda agent: agent.run(root, files), agents))
    return sorted((f for batch in batches for f in batch), key=lambda f: (f.severity, f.path, f.line), reverse=True)

