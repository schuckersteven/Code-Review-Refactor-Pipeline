from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .models import Finding, RefactorStep, ReviewPlan


def imports_for(path: Path, root: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    names = set(re.findall(r"(?:from\s+|import\s+|require\(['\"])([\w./-]+)", text))
    resolved: set[str] = set()
    for name in names:
        candidate = (path.parent / name).resolve()
        for suffix in (".py", ".js", ".ts", "/__init__.py"):
            target = Path(str(candidate) + suffix)
            if target.exists() and root in target.parents:
                resolved.add(target.relative_to(root).as_posix())
    return resolved


def build_plan(root: Path, findings: list[Finding]) -> ReviewPlan:
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        groups[finding.path].append(finding)
    steps = []
    for index, (path, group) in enumerate(sorted(groups.items()), 1):
        primary = group[0]
        steps.append(RefactorStep(f"STEP-{index:03}", f"Address findings in {path}", primary.recommendation, [f.id for f in group], [path]))
    by_file = {step.files[0]: step for step in steps if step.files[0] != "."}
    for path, step in by_file.items():
        target = root / path
        if target.exists():
            # Change a dependency before a dependent, so consumers can be adapted afterward.
            for imported in imports_for(target, root):
                if imported in by_file:
                    step.depends_on.append(by_file[imported].id)
    ordered = topological_sort(steps)
    return ReviewPlan(str(root.resolve()), findings, ordered)


def topological_sort(steps: list[RefactorStep]) -> list[RefactorStep]:
    by_id = {s.id: s for s in steps}
    pending = {s.id: set(s.depends_on) for s in steps}
    ordered: list[RefactorStep] = []
    while pending:
        ready = sorted(step_id for step_id, dependencies in pending.items() if not dependencies)
        if not ready:
            raise ValueError(f"Refactoring dependency cycle: {sorted(pending)}")
        for step_id in ready:
            ordered.append(by_id[step_id])
            del pending[step_id]
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return ordered

