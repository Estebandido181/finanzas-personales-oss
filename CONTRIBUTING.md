# Contributing

This project is in early beta. Small, reproducible fixes are welcome.

## Before opening an issue

Describe the supported input format, expected result and actual result. Reduce
banking examples to synthetic text or a workbook generated in memory. Do not
attach real exports, email bodies/headers, account numbers, tokens or screenshots
of personal financial information. Report security issues privately (SECURITY.md).

## Development

Use Ubuntu, Python 3.12 and Node 24. From the repository root:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -c backend/constraints-linux-py312.txt -r backend/requirements-dev.txt -e .
python scripts/revisar_fronteras.py
pytest -q
cd frontend
npm ci --ignore-scripts
npm run tipos
# Generated types must not change unless the OpenAPI contract changed.
git diff --exit-code -- src/api/esquema.d.ts
npm run build
npm test
npx playwright install --with-deps --only-shell chromium
PYTHON=../.venv/bin/python npm run e2e
```

For the last command use an absolute PYTHON path if your environment does not
resolve the relative path from frontend/. Browser tests use a temporary database
and fake Gmail. The manual demonstration server has development-only routes and
must remain on loopback; never use it for real data or production.

## Privacy and pull requests

Before committing, stage only intended files and run:

```bash
python scripts/revisar_datos.py --todo
python scripts/revisar_datos.py --base origin/main
```

The public CI applies generic checks without secrets, including on forks. It does
not certify anonymity: split/encoded data and images may escape the scanner.
Review your diff and any images manually. A private personal denylist may be
used locally with --lista, but it must stay outside Git and untrusted PR jobs.

Explain the bug, change, tests and limitations. Financial and security changes
require independent review. Do not relax tests to obtain a passing result.
There is no guaranteed response time or support SLA during this beta.
