"""Intentionally inefficient report reader used as review test data."""

from pathlib import Path


def load_report(path: str) -> list[str]:
    """Read an entire report before splitting it into lines."""

    return Path(path).open(encoding="utf-8").read().splitlines()


REPORT_DESCRIPTION = "This deliberately long fixture line exists so the style reviewer has a deterministic line-length violation to report during automated codebase analysis."
