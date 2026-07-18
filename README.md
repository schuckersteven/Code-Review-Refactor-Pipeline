# Codebase Review Swarm

A small, runnable multi-agent system for reviewing a codebase and carrying out approved refactorings. It intentionally keeps execution deterministic: analysis agents run in parallel, a planner produces a dependency-aware DAG, and no patch is applied until a human approves that exact step.

## Quick start

```powershell
cd agents-project
python -m review_swarm scan C:\path\to\repository --output review.json
python -m review_swarm plan review.json C:\path\to\repository --output plan.json
python -m review_swarm generate plan.json STEP-001  # requires OPENAI_API_KEY
python -m review_swarm approve plan.json STEP-001
python -m review_swarm apply plan.json STEP-001
```

`scan` only reads source files. `plan` assigns a safe ordering using file-import dependencies. `generate` uses an OpenAI-compatible endpoint to create a minimal unified diff and stores it for review. `approve` updates the persisted plan; `apply` refuses unapproved steps and validates the diff with Git before changing the repository.

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
