"""Build dependency-aware refactoring plans from synthesized findings.

The planner groups findings by file, derives ordering constraints from local
source imports, and topologically sorts the resulting steps so dependencies
can be changed before their consumers.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .models import Finding, RefactorStep, ReviewPlan


def imports_for(path: Path, root: Path) -> set[str]:
    """Return repository-relative files imported by a source file.

    The lightweight resolver recognizes common Python and JavaScript import
    forms and limits resolved targets to files beneath ``root``.

    Args:
        path: Source file whose imports should be inspected.
        root: Repository root used for path containment and relativization.

    Returns:
        Repository-relative POSIX paths for imports that resolve locally.
    """

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
    """
    Convert findings into grouped, dependency-ordered refactoring steps.

    Findings for the same path become one human-reviewable step. When two
    affected files have an import relationship, the imported file's step is
    recorded as a prerequisite of the importing file's step.

    Args:
        root: Root directory of the reviewed repository.
        findings: Synthesized findings from all review dimensions.

    Returns:
        A review plan containing the original findings and ordered steps.

    Raises:
        ValueError: If the derived refactoring dependencies contain a cycle.
    """

    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        groups[finding.path].append(finding)
    steps = []
    for index, (path, group) in enumerate(sorted(groups.items()), 1):
        primary = group[0]
        steps.append(
            RefactorStep(
                f"STEP-{index:03}",
                f"Address findings in {path}",
                primary.recommendation,
                [f.id for f in group],
                [path],
            )
        )
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
    """
    Order refactoring steps so every prerequisite precedes its consumers.

    Steps that are simultaneously ready are ordered by ID for deterministic
    plans.

    Args:
        steps: Refactoring steps with dependencies expressed as step IDs.

    Returns:
        A new list in valid dependency order.

    Raises:
        ValueError: If no step can be scheduled because a cycle exists.
    """

    by_id = {s.id: s for s in steps}
    pending = {s.id: set(s.depends_on) for s in steps}
    ordered: list[RefactorStep] = []
    while pending:
        ready = sorted(
            step_id for step_id, dependencies in pending.items() if not dependencies
        )
        if not ready:
            raise ValueError(f"Refactoring dependency cycle: {sorted(pending)}")
        for step_id in ready:
            ordered.append(by_id[step_id])
            del pending[step_id]
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return ordered
