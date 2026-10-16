# Contributor and agent instructions

Work only on the task authorized by the maintainer. Keep changes focused and
preserve unrelated work. Do not deploy, publish or submit applications without
explicit human authorization.

- Use integer cents for financial amounts. Preserve reconciliation multiplicity,
  idempotency, atomicity and human decisions for ambiguous matches.
- Never commit credentials, private financial records, Gmail bodies, database
  files or bank exports. Generate test workbooks in memory.
- Preserve authentication, CSRF/Origin checks, CSP and four-digit reference limits.
- Add behavior tests for security or financial changes and obtain independent review.
- Validate on Ubuntu/Python 3.12/Node 24. Do not weaken POSIX protections for Windows.
- Run the privacy and architecture checks documented in CONTRIBUTING.md.
- No production access is required for development. Do not request the maintainer's
  private denylist or copy secrets into CI. Third-party notices must be preserved.
