from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from .agents import analyze
from .generator import generate_patch
from .models import Finding, RefactorStep, ReviewPlan, Severity
from .planner import build_plan


def load_plan(path: Path) -> ReviewPlan:
    raw = json.loads(path.read_text())
    findings = [Finding(**{**f, "severity": Severity(f["severity"])}) for f in raw["findings"]]
    return ReviewPlan(raw["repository"], findings, [RefactorStep(**s) for s in raw["steps"]])


def save(plan: ReviewPlan, path: Path) -> None:
    path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Human-approved multi-agent code review")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan"); scan.add_argument("repository", type=Path); scan.add_argument("--output", type=Path, required=True)
    plan = commands.add_parser("plan"); plan.add_argument("review", type=Path); plan.add_argument("repository", type=Path); plan.add_argument("--output", type=Path, required=True)
    approve = commands.add_parser("approve"); approve.add_argument("plan", type=Path); approve.add_argument("step_id")
    generate = commands.add_parser("generate"); generate.add_argument("plan", type=Path); generate.add_argument("step_id")
    apply = commands.add_parser("apply"); apply.add_argument("plan", type=Path); apply.add_argument("step_id")
    args = parser.parse_args()
    if args.command == "scan":
        findings = analyze(args.repository.resolve())
        args.output.write_text(json.dumps([asdict(f) for f in findings], indent=2) + "\n")
        print(f"Wrote {len(findings)} findings to {args.output}")
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
        step.approved = True
        save(review_plan, args.plan)
        print(f"Approved {step.id}: {step.title}")
    elif args.command == "generate":
        review_plan = load_plan(args.plan)
        step = next((s for s in review_plan.steps if s.id == args.step_id), None)
        if not step:
            raise SystemExit(f"Unknown step: {args.step_id}")
        step.patch = generate_patch(Path(review_plan.repository), step, review_plan.findings)
        save(review_plan, args.plan)
        print(f"Generated a patch for {step.id}; review it, then approve the step.")
    else:
        review_plan = load_plan(args.plan)
        step = next((s for s in review_plan.steps if s.id == args.step_id), None)
        if not step or not step.approved:
            raise SystemExit("This step must exist and be approved before applying it.")
        if not step.patch:
            raise SystemExit("Generate or attach a patch before applying this step.")
        completed = {s.id for s in review_plan.steps if s.applied}
        missing = set(step.depends_on) - completed
        if missing:
            raise SystemExit(f"Approve and apply dependencies first: {sorted(missing)}")
        result = subprocess.run(["git", "-C", review_plan.repository, "apply", "--check", "-"], input=step.patch, text=True, capture_output=True)
        if result.returncode:
            raise SystemExit(f"Patch validation failed:\n{result.stderr}")
        subprocess.run(["git", "-C", review_plan.repository, "apply", "-"], input=step.patch, text=True, check=True)
        step.applied = True
        save(review_plan, args.plan)
        print(f"Applied {step.id}. Run the repository test suite before approving the next dependent step.")


if __name__ == "__main__":
    main()
