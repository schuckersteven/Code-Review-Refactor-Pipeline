"""
Command-line workflow for scanning, planning, approving, and applying fixes.

The CLI supports complete repository reviews and unified pull-request diffs.
Generated patches remain inert until a human approves their exact digest, and
the apply command enforces file scope and dependency completion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import asdict
from pathlib import Path

from .agents import analyze, analyze_diff
from .generator import generate_patch
from .models import Finding, RefactorStep, ReviewPlan, Severity
from .planner import build_plan


def load_plan(path: Path) -> ReviewPlan:
    """
    Deserialize a persisted review plan and restore its typed models.
    """

    raw = json.loads(path.read_text())
    findings = [
        Finding(**{**f, "severity": Severity(f["severity"])}) for f in raw["findings"]
    ]
    return ReviewPlan(
        raw["repository"], findings, [RefactorStep(**s) for s in raw["steps"]]
    )


def save(plan: ReviewPlan, path: Path) -> None:
    """
    Serialize a review plan as formatted JSON, creating parent directories.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n")


def repository_path(value: Path) -> Path:
    """
    Resolve and validate a path that must identify a repository directory."""

    root = value.resolve()
    if not root.is_dir():
        raise SystemExit(f"Repository is not a directory: {root}")
    return root


def read_diff(path: Path) -> str:
    """
    Read and minimally validate a unified git diff from disk."""

    if not path.is_file():
        raise SystemExit(f"Diff is not a file: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if "diff --git " not in text:
        raise SystemExit(f"Not a unified git diff: {path}")
    return text


def patch_sha256(patch: str) -> str:
    """
    Return the digest used to bind human approval to exact patch content.
    """

    return hashlib.sha256(patch.encode()).hexdigest()


def validate_patch_paths(
    repository: Path, patch: str, allowed_files: list[str]
) -> None:
    """
    Reject malformed patches or changes outside the planned repository files."""

    headers = re.findall(r"^diff --git a/(.+?) b/(.+?)$", patch, flags=re.MULTILINE)
    if not headers:
        raise SystemExit("Patch has no valid git diff headers.")
    touched = {path for pair in headers for path in pair}
    if any(Path(path).is_absolute() or ".." in Path(path).parts for path in touched):
        raise SystemExit("Patch contains a path outside the repository.")
    unexpected = touched - set(allowed_files)
    if unexpected:
        raise SystemExit(f"Patch changes files outside this step: {sorted(unexpected)}")
    if any(repository not in (repository / path).resolve().parents for path in touched):
        raise SystemExit("Patch contains a path outside the repository.")


def main() -> None:
    """
    Parse command-line arguments and execute the selected review workflow.
    """

    parser = argparse.ArgumentParser(
        description="Human-approved multi-agent code review"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("repository", type=Path)
    scan.add_argument("--diff", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("review")
    review.add_argument("repository", type=Path)
    review.add_argument("--diff", type=Path)
    review.add_argument("--output", type=Path, default=Path("review-plan.json"))
    plan = commands.add_parser("plan")
    plan.add_argument("review", type=Path)
    plan.add_argument("repository", type=Path)
    plan.add_argument("--output", type=Path, required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("plan", type=Path)
    approve.add_argument("step_id")
    generate = commands.add_parser("generate")
    generate.add_argument("plan", type=Path)
    generate.add_argument("step_id")
    apply = commands.add_parser("apply")
    apply.add_argument("plan", type=Path)
    apply.add_argument("step_id")
    args = parser.parse_args()
    if args.command == "scan":
        root = repository_path(args.repository)
        findings = analyze_diff(read_diff(args.diff)) if args.diff else analyze(root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps([asdict(f) for f in findings], indent=2) + "\n"
        )
        print(f"Wrote {len(findings)} findings to {args.output}")
    elif args.command == "review":
        root = repository_path(args.repository)
        findings = analyze_diff(read_diff(args.diff)) if args.diff else analyze(root)
        review_plan = build_plan(root, findings)
        save(review_plan, args.output)
        print(
            f"Wrote {len(findings)} findings and {len(review_plan.steps)} ordered steps to {args.output}"
        )
    elif args.command == "plan":
        raw = json.loads(args.review.read_text())
        findings = [Finding(**{**f, "severity": Severity(f["severity"])}) for f in raw]
        review_plan = build_plan(args.repository.resolve(), findings)
        save(review_plan, args.output)
        print(f"Wrote {len(review_plan.steps)} ordered steps to {args.output}")
    elif args.command == "approve":
        review_plan = load_plan(args.plan)
        step = next((s for s in review_plan.steps if s.id == args.step_id), None)
        if not step:
            raise SystemExit(f"Unknown step: {args.step_id}")
        if not step.patch:
            raise SystemExit("Generate or attach a patch before approving this step.")
        step.approved = True
        step.approved_patch_sha256 = patch_sha256(step.patch)
        save(review_plan, args.plan)
        print(f"Approved {step.id}: {step.title}")
    elif args.command == "generate":
        review_plan = load_plan(args.plan)
        step = next((s for s in review_plan.steps if s.id == args.step_id), None)
        if not step:
            raise SystemExit(f"Unknown step: {args.step_id}")
        step.patch = generate_patch(
            Path(review_plan.repository), step, review_plan.findings
        )
        validate_patch_paths(Path(review_plan.repository), step.patch, step.files)
        step.approved = False
        step.approved_patch_sha256 = None
        save(review_plan, args.plan)
        print(f"Generated a patch for {step.id}; review it, then approve the step.")
    else:
        review_plan = load_plan(args.plan)
        step = next((s for s in review_plan.steps if s.id == args.step_id), None)
        if not step or not step.approved:
            raise SystemExit("This step must exist and be approved before applying it.")
        if not step.patch:
            raise SystemExit("Generate or attach a patch before applying this step.")
        if step.approved_patch_sha256 != patch_sha256(step.patch):
            raise SystemExit(
                "The patch changed after approval; review and approve it again."
            )
        repository = repository_path(Path(review_plan.repository))
        validate_patch_paths(repository, step.patch, step.files)
        completed = {s.id for s in review_plan.steps if s.applied}
        missing = set(step.depends_on) - completed
        if missing:
            raise SystemExit(f"Approve and apply dependencies first: {sorted(missing)}")
        result = subprocess.run(
            ["git", "-C", str(repository), "apply", "--check", "-"],
            input=step.patch,
            text=True,
            capture_output=True,
        )
        if result.returncode:
            raise SystemExit(f"Patch validation failed:\n{result.stderr}")
        subprocess.run(
            ["git", "-C", str(repository), "apply", "-"],
            input=step.patch,
            text=True,
            check=True,
        )
        step.applied = True
        save(review_plan, args.plan)
        print(
            f"Applied {step.id}. Run the repository test suite before approving the next dependent step."
        )


if __name__ == "__main__":
    main()
