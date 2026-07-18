from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from .models import Finding, RefactorStep


def generate_patch(repository: Path, step: RefactorStep, findings: list[Finding]) -> str:
    """Ask an OpenAI-compatible Chat Completions endpoint for one reviewable diff."""
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
        "constraints": ["Return only a unified diff.", "Change only supplied files.", "Keep the change minimal and preserve public behavior unless the finding requires a security fix."],
    }
    payload = json.dumps({"model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"), "messages": [{"role": "system", "content": "You produce safe, minimal source-code patches."}, {"role": "user", "content": json.dumps(prompt)}], "temperature": 0}).encode()
    request = urllib.request.Request(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"), data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=90) as response:
        body = json.load(response)
    patch = body["choices"][0]["message"]["content"].strip()
    if not patch.startswith("diff --git"):
        raise RuntimeError("Generator returned content that is not a unified git diff.")
    return patch

