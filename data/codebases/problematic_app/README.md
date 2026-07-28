# Problematic App Fixture

This intentionally unsafe codebase is test data for the review swarm. Do not
reuse its credential, dynamic evaluation, or shell-execution patterns in
production code.

Expected review dimensions:

- Security: hard-coded credential, `eval`, and shell execution
- Performance: whole-file read and loops requiring review
- Style: `TODO` marker and a long source line
- Test coverage: production files with no tests
