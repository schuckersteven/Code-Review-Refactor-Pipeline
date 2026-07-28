"""
Tests for extracting and reviewing added lines from unified PR diffs.
"""

from review_swarm.agents import analyze_diff, changed_lines

# A production-only change containing two intentionally unsafe added lines.
DIFF = """diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -8,2 +8,3 @@
 context = True
-safe_call()
+password = "secret"
+eval(user_input)
"""


def test_changed_lines_preserve_new_file_numbers():
    """
    Added lines retain their paths and line numbers from the new file.
    """

    lines = changed_lines(DIFF)
    assert [(line.path, line.number) for line in lines] == [
        ("app.py", 9),
        ("app.py", 10),
    ]


def test_diff_agents_review_only_added_lines():
    """
    Parallel agents flag added risks and the absence of accompanying tests.
    """

    findings = analyze_diff(DIFF)
    security = [finding for finding in findings if finding.dimension == "security"]
    assert {finding.line for finding in security} == {9, 10}
    assert any(finding.id == "coverage-diff-no-tests" for finding in findings)
