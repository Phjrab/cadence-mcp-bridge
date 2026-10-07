# Contributing

The public verification stack is Windows 2022, Python 3.12.10 and locked uv
0.12.6 dependencies. It runs without Cadence, PDK files, operator credentials,
license endpoints or a laboratory VM. Linux native qualification is separate.

Run these commands from the repository root:

~~~powershell
uv sync --locked --all-groups --python 3.12.10
.venv/Scripts/python.exe -m ruff check src scripts tests
.venv/Scripts/python.exe -m mypy src
.venv/Scripts/python.exe -m pytest tests/unit -q
./scripts/verify-security.ps1
.venv/Scripts/python.exe -I -X utf8 scripts/verify-release-readiness.py
./scripts/verify-package.ps1
~~~

Keep feature changes on a branch and open a PR. Include the concrete problem,
resulting behavior, relevant test evidence and remaining qualification limits.
Review AI-generated changes and verify them with the same standards as other
contributions. Green synthetic CI does not establish native Cadence support.
Never bypass repository checks, force-push protected branches or publish a release
as part of routine contribution work.

Use fictional minimal reproductions. Do not attach proprietary netlists, OA/ADE,
PDK/model data, raw PSF, credentials, private paths, unrestricted logs or license
values. Before submitting, inspect staged files and built artifacts. Report a
security issue privately as described in SECURITY.md; do not post an exploit
with private project material in a public issue.

Contributions use the existing Apache-2.0 inbound conditions. No additional CLA,
copyright transfer or license conversion is introduced. Imported planning material
with uncertain redistribution rights remains outside curated packages and requires
separate legal review.
