# Demo Guide

This walkthrough demonstrates deterministic repository review, finding
synthesis, dependency-aware planning, and the optional human-approved patch
workflow. It uses the fixtures included with the project and does not require
an API key until patch generation.

## Prerequisites

- Python 3.11 or newer
- Git
- PowerShell
- An OpenAI-compatible API key only for the optional generation phase

From the project root, install the package:

```powershell
python -m pip install -e .
```

## 1. Review the problematic fixture

Run analysis and planning together:

```powershell
python -m review_swarm review `
  data\codebases\problematic_app `
  --output demo-plan.json
```

Expected summary:

```text
Wrote 8 findings and 3 ordered steps to demo-plan.json
```

The eight findings cover every built-in review dimension:

| Dimension | Findings | Examples |
| --- | ---: | --- |
| Security | 3 | Hard-coded credential, dynamic evaluation, shell execution |
| Performance | 2 | Whole-file read, loop requiring review |
| Style | 2 | Maintenance marker, long line |
| Test coverage | 1 | Production source without tests |

Open `demo-plan.json` to inspect the complete evidence, recommendations, and
ordered refactoring steps. To print a compact summary in PowerShell:

```powershell
$plan = Get-Content demo-plan.json | ConvertFrom-Json

$plan.findings |
  Select-Object severity, dimension, path, line, title |
  Format-Table

$plan.steps |
  Select-Object id, title, files, depends_on |
  Format-Table
```

Stable finding IDs are derived from the rule and source location. Findings are
sorted by severity, path, line, and ID, so concurrent agent execution does not
make the output order unpredictable.

## 2. Compare the clean fixture

```powershell
python -m review_swarm review `
  data\codebases\clean_app `
  --output clean-demo-plan.json
```

Expected summary:

```text
Wrote 0 findings and 0 ordered steps to clean-demo-plan.json
```

This demonstrates the baseline behavior for a repository with focused tests
and none of the patterns targeted by the built-in rules.

## 3. Run analysis and planning separately

The same pipeline can be split across sessions or CI stages:

```powershell
python -m review_swarm scan `
  data\codebases\problematic_app `
  --output demo-findings.json

python -m review_swarm plan `
  demo-findings.json `
  data\codebases\problematic_app `
  --output demo-plan.json
```

`scan` writes findings only. `plan` groups them by path, derives local import
dependencies, and writes the ordered workflow state.

## 4. Demonstrate the approval gate

Trying to apply an unapproved step is rejected:

```powershell
python -m review_swarm apply demo-plan.json STEP-001
```

Expected result:

```text
This step must exist and be approved before applying it.
```

This failure is intentional: planning alone never authorizes a repository
change.

## 5. Generate and review a patch (optional)

Patch generation sends the selected step's findings and allowlisted file
contents to the configured OpenAI-compatible endpoint. Use a disposable copy
of the fixture if you intend to apply the result:

```powershell
$demoTarget = Join-Path $env:TEMP ("review-swarm-demo-" + [guid]::NewGuid())
Copy-Item data\codebases\problematic_app $demoTarget -Recurse

python -m review_swarm review $demoTarget --output generated-demo-plan.json

$env:OPENAI_API_KEY = "your-api-key"
# Optional:
# $env:OPENAI_MODEL = "your-model"
# $env:OPENAI_BASE_URL = "https://your-endpoint/v1/chat/completions"

python -m review_swarm generate generated-demo-plan.json STEP-001
```

The generated diff is stored in the plan but remains unapproved. Inspect it:

```powershell
$generatedPlan = Get-Content generated-demo-plan.json | ConvertFrom-Json
$generatedPlan.steps |
  Where-Object id -eq "STEP-001" |
  Select-Object -ExpandProperty patch
```

Only after reviewing the exact patch should a human approve it:

```powershell
python -m review_swarm approve generated-demo-plan.json STEP-001
```

Approval stores the patch's SHA-256 digest. Editing or regenerating the patch
invalidates that approval.

## 6. Apply the approved patch (optional)

```powershell
python -m review_swarm apply generated-demo-plan.json STEP-001
```

Before changing the disposable repository, the executor verifies:

1. The step is approved and its patch digest is unchanged.
2. The patch touches only files allowlisted for the step.
3. All paths remain inside the target repository.
4. All prerequisite steps have already been applied.
5. `git apply --check` succeeds.

Run the target repository's tests after each applied step. Test execution is
kept explicit because commands and environments vary between repositories.

## Cleanup

The generated JSON files are demo artifacts and can be removed after the
walkthrough. The optional target is created under the system temporary
directory; its exact path is stored in `$demoTarget` for the current
PowerShell session.
