# Validation

Everything behind the claims in `docs/limitations.md`: what was promised, which
data may be used for what, the harness that produces the evidence, and the
evidence itself.

None of this ships in the wheel.

```text
protocol/    the frozen protocol, its machine-readable copy, the calibration grid
manifests/   one entry per dataset: source, licence, key, checksum, split, family
harness/     corruption procedures, metrics, the runner, calibration, comparison
results/     what the harness produced, versioned by release
```

## Reading it

Start with [`protocol/protocol.md`](protocol/protocol.md). It states the
validation question, the dataset splits and their rules, what counts as a
known-correct key, the corruption tests, the metrics, and the rule that the
family is the statistical unit. `protocol/protocol.json` is the machine-readable counterpart.
`python -m scripts.check_validation_setup` checks their version, status, freeze
date and baseline, together with the manifest and dataset checksums.

[`manifests/datasets.json`](manifests/datasets.json) records every dataset:
where it came from, its citation, reviewed licensing information, its entity
and time columns, its sha256, its documented shape, its family, its split, and
how its correct key is known independently of `paneldx`.

## Running it

```bash
python3.12 -m venv .venv-validation
.venv-validation/bin/pip install -r validation/requirements.txt
.venv-validation/bin/pip install --no-deps -e .
.venv-validation/bin/python -m scripts.fetch_validation_data
.venv-validation/bin/python -m scripts.check_validation_setup
.venv-validation/bin/python -m validation.harness.cases --profile development
.venv-validation/bin/python -m validation.harness.comparison
```

Profiles: `smoke` for CI, `development` for the full run, `publication` at 200
shuffles for a final evaluation that has not happened.

## Two rules the code enforces

**The held-out split is registered and not evaluated.** Its files were
downloaded once and their shape and checksum recorded; `paneldx` has not been
run on any of them. No profile can select the split, and the downloader refuses
it without `--include-held-out`.

**Related datasets share a split.** Every dataset carries a `family_id`, and a
family may not span two splits: two panels from one survey are not independent,
so calibrating on one would leak into a held-out result from the other. The
manifest check rejects a manifest that breaks this.

## Results

`results/development/v0.4.0/` and `results/development/v0.5.0/` hold the same
3,480 cases under each release, with `comparison.md` between them.
`results/calibration/v0.5.0/` holds the threshold search. Directories are
versioned so a later release adds to the record rather than overwriting it.

`failures.json` lists every false rejection, every accepted broken key and
every case excluded for changing nothing.
