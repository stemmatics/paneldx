# Security Policy

## Supported versions

`paneldx` is pre-1.0. Fixes land on the latest minor release only.

| Version | Supported |
|---------|-----------|
| 0.4.x   | yes       |
| <= 0.3  | no        |

## Reporting a vulnerability

Report privately through GitHub's
[security advisory form](https://github.com/stemmatics/paneldx/security/advisories/new).
Please do not open a public issue for a security problem.

You should get an acknowledgement within 7 days and an assessment within 30.
If a fix is warranted it ships in the next patch release, and you will be
credited in the advisory unless you ask otherwise.

## Threat model

`paneldx` reads data files and writes an HTML report. It executes no user code
and makes no network calls. The realistic risks are:

- **Untrusted input files.** Parsing is delegated to `pandas`. A malicious
  Parquet, Excel or pickle-backed file is a `pandas` or `pyarrow` concern, but
  report it here too and it will be forwarded upstream.
- **HTML report injection.** Column names and values from the input reach the
  rendered page. Everything is escaped through `html.escape`, and a test asserts
  that a column named with a script tag cannot execute. A bypass is a
  vulnerability, so please report it.
- **Path handling.** `--html` writes wherever it is told. Do not pass an
  attacker-controlled path.

Out of scope: a wrong verdict on a valid key. That is a correctness bug and
belongs in the issue tracker.
