# Contributing

Bug reports, new checks and better heuristics are all welcome.

## Setup

```bash
git clone https://github.com/stemmatics/paneldx.git
cd paneldx
python3 -m pip install -e ".[dev,excel,parquet]"
python3 -m pre_commit install --install-hooks
python3 -m pre_commit run --all-files
```

The hooks are not optional infrastructure: a clone without them has no local
gate at all. `pre-commit install` reads `default_install_hook_types` and wires
both stages in one command. To confirm:

```bash
ls -l .git/hooks/pre-commit .git/hooks/pre-push
```

Commit is kept fast: whitespace, YAML/TOML, private-key detection, Ruff lint
and format. Push runs the local quality gate: validation-data checksums,
`pytest` with branch coverage, `mypy`, a wheel and sdist build with `twine
check`, and `pip-audit`. CI additionally runs the Python-version matrix,
dependency-floor checks, CodeQL, secret scanning and scheduled dependency
auditing. Expect the first push after a clone to take a minute. To run the
local gate by hand:

```bash
python3 -m pre_commit run --hook-stage pre-push --all-files
```

`pip-audit` needs network access. It audits PanelDX's runtime dependency
closure, including the optional Excel and Parquet extras, rather than unrelated
development tools installed on your machine.

Python 3.9+. Runtime dependencies are `numpy` and `pandas` only, and that is
deliberate: this is a tool people run *before* choosing a modelling stack, so it
should never drag one in. Please do not add runtime dependencies without opening
an issue first.

## Tests

Unit and regression tests use synthetic data with known results. Validation
tests may use public datasets downloaded by
`scripts/fetch_validation_data.py`.

Do not add private, identifiable or restricted data to the tests. The PopNet
workbook is not included in this repository. The case-study script accepts a
path to an authorised local copy.

If you add a detector, add a panel that provably triggers it and one that
provably does not.

## What makes a good check

Checks here answer a question about the data, not about a model:

- **Cheap.** It runs before training, so it cannot cost more than training.
- **Falsifiable.** Compare against a null. `paneldx` shuffles entity labels
  within each period; if your check cannot beat its own null, it is measuring
  the shape of the table rather than a defect.
- **Actionable.** A verdict should tell someone what to do next.

## Reporting a bug

Include the shape of the frame, the column dtypes and a minimal reproduction. A
synthetic frame that triggers the problem is worth more than a description of a
private one.

False positives are bugs. If `paneldx` rejects a key you know is correct, that is
worth an issue, and the panel that produced it (synthetic or anonymised) is the
most useful thing you can attach.

## Pull requests

- One change per PR.
- `pytest` green, and CI covers 3.9 / 3.11 / 3.13.
- Update the README if you change behaviour a user would notice.
- Add new thresholds to the relevant policy object.
- Explain why the threshold is needed and include a sensitivity check.
