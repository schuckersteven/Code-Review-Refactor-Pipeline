# Codebase Review Swarm

A small, runnable multi-agent system for reviewing a codebase and carrying out approved refactorings. It intentionally keeps execution deterministic: analysis agents run in parallel, a planner produces a dependency-aware DAG, and no patch is applied until a human approves that exact step.

It performs automated review across four dimensions:

- **Security vulnerabilities** — detects dangerous dynamic evaluation, possible hard-coded credentials, and shell-command injection risks.
- **Performance** — identifies potentially expensive loops and unbounded whole-file reads.
- **Style** — reports unresolved maintenance markers and excessively long source lines.
- **Test coverage gaps** — detects repositories without tests and PRs that change production code without corresponding test changes.
- **Multi-dimensional parallel analysis with synthesis** — runs specialized reviewers concurrently, then combines and prioritizes their findings in a unified refactoring plan.
- **Dependency-aware planning and ordering** — schedules prerequisite refactorings before dependent changes to reduce the risk of breaking the codebase.
- **HITL approval workflows** — requires a human to review and approve the exact generated patch for every refactoring step before execution.

It also proposes refactoring plans with dependency-aware ordering and generates the refactored code for human review. The planner groups related findings into reviewable steps, orders dependencies before their consumers, and blocks a step until its prerequisites are applied. Code generation produces a minimal unified diff for each step; the exact patch must be reviewed and explicitly approved before the system can apply it.

The planning layer determines refactoring order to avoid breaking changes. Human-in-the-loop (HITL) approval is required for each refactoring step before execution.

## Quick start

```powershell
cd Code-Review-Refactor-Pipeline
python -m review_swarm review C:\path\to\repository --output plan.json
python -m review_swarm review C:\path\to\repository --diff pr.diff --output pr-plan.json

# Or run the phases separately:
python -m review_swarm scan C:\path\to\repository --output review.json
python -m review_swarm plan review.json C:\path\to\repository --output plan.json
python -m review_swarm generate plan.json STEP-001  # requires OPENAI_API_KEY
python -m review_swarm approve plan.json STEP-001
python -m review_swarm apply plan.json STEP-001
```

`review` scans and plans in one command. With `--diff`, reviewers inspect only added source lines in a unified PR diff, preserve new-file line numbers, and flag production changes without test changes. `scan` emits findings without a plan. `plan` assigns a safe ordering using file-import dependencies. `generate` creates a minimal unified diff. `approve` binds approval to the exact patch digest; `apply` rejects changed, unapproved, or out-of-scope patches.

For a complete walkthrough using the included fixtures, see the
[demo guide](docs/demo.md).

## Tests

From the project directory, install the package and test runner, then run the complete suite:

```powershell
python -m pip install -e . pytest
python -m pytest
```

Run either test module independently:

```powershell
python -m pytest tests/test_planner.py
python -m pytest tests/test_diff_review.py
```

Use `-q` for concise output or `-v` to display each test name:

```powershell
python -m pytest -q
python -m pytest -v
```

## Architecture

```
Repository -> [security | performance | style | coverage] agents (parallel)
           -> synthesizer -> dependency-aware planner -> human approval -> patch executor
```

The included rule agents are dependency-free and useful in CI or a demo. Add an LLM adapter at the `CodeGenerator` protocol boundary for semantic findings and generated patches; generated output must still go through the same approval gate.

## Safety model

- Files outside the requested repository and binary/vendor folders are excluded.
- Findings include a stable ID, location, severity, and suggested remediation.
- Steps are topologically sorted; cycles are surfaced rather than silently ordered, and dependent steps require their prerequisites to be applied.
- Applying a step requires an explicit persisted approval and a patch constrained to the repository root.
