"""Intentionally problematic application used only as review test data."""

import os

from report import load_report

password = "demo-only-secret"


def calculate(expression: str):
    """Evaluate user input using an intentionally unsafe implementation."""

    return eval(expression)


def list_directory(path: str) -> int:
    """List a directory using intentionally unsafe shell invocation."""

    return os.system(f"dir {path}")


def main() -> None:
    """Run the fixture application."""

    # TODO: replace these placeholder operations with safe implementations.
    for item in load_report("report.txt"):
        print(item)


if __name__ == "__main__":
    main()
