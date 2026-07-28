"""
Generate minimal refactoring patches with an OpenAI-compatible endpoint.

The generator supplies only the files and findings associated with one planned
step. Its output is a review candidate: the CLI separately validates its file
scope and requires explicit human approval before applying it.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from .models import Finding, RefactorStep


def generate_patch(
    repository: Path, step: RefactorStep, findings: list[Finding]
) -> str:
    """
    Generate one reviewable unified diff for a planned refactoring step.

    The endpoint is configured with ``OPENAI_API_KEY`` and may be customized
    through ``OPENAI_MODEL`` and ``OPENAI_BASE_URL``. Only findings referenced
    by ``step`` and existing files listed in ``step.files`` are included in the
    request.

    Args:
        repository: Root directory containing the files to refactor.
        step: Approved-plan step that defines the task and permitted files.
        findings: Full finding collection from which this step's findings are
            selected.

    Returns:
        A git-style unified diff beginning with a ``diff --git`` header.

    Raises:
        RuntimeError: If the API key is missing or the endpoint does not return
            a unified git diff.
        OSError: If a supplied file cannot be read or the HTTP request fails.
    """

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY before generating a patch.")
    selected = [f for f in findings if f.id in step.finding_ids]
    files: dict[str, str] = {}
    for relative in step.files:
        path = repository / relative
        if path.exists() and path.is_file():
            files[relative] = path.read_text(encoding="utf-8", errors="replace")
    prompt = {
        "task": step.title,
        "rationale": step.rationale,
        "findings": [f.__dict__ | {"severity": f.severity.value} for f in selected],
        "files": files,
        "constraints": [
            "Return only a unified diff.",
            "Change only supplied files.",
            "Keep the change minimal and preserve public behavior unless the finding requires a security fix.",
        ],
    }
    payload = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": "You produce safe, minimal source-code patches.",
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
            "temperature": 0,
        }
    ).encode()
    request = urllib.request.Request(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"),
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        body = json.load(response)
    patch = body["choices"][0]["message"]["content"].strip()
    if not patch.startswith("diff --git"):
        raise RuntimeError("Generator returned content that is not a unified git diff.")
    return patch
