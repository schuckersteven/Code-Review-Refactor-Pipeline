"""
Tests for finding grouping and dependency-aware refactoring order.
"""

from pathlib import Path

from review_swarm.models import Finding, Severity
from review_swarm.planner import build_plan, topological_sort


def test_topological_sort_orders_dependencies():
    """
    A prerequisite step is scheduled before the step that depends on it.
    """

    from review_swarm.models import RefactorStep

    ordered = topological_sort(
        [RefactorStep("B", "b", "", [], [], ["A"]), RefactorStep("A", "a", "", [], [])]
    )
    assert [step.id for step in ordered] == ["A", "B"]


def test_plan_groups_findings(tmp_path: Path):
    """
    A finding is retained in the refactoring step for its source file.
    """

    finding = Finding(
        "one", "security", Severity.HIGH, "app.py", 1, "title", "x", "fix"
    )
    plan = build_plan(tmp_path, [finding])
    assert plan.steps[0].finding_ids == ["one"]
