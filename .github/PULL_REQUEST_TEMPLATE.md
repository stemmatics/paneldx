## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- What was wrong, or what could not be done before. -->

## Checklist

- [ ] `pytest` passes
- [ ] `ruff check .` is clean
- [ ] New behaviour is covered by a test against a panel with a known answer
- [ ] No new runtime dependency (numpy and pandas only), or discussed in an issue
- [ ] README updated if a user would notice the change
- [ ] CHANGELOG entry added under Unreleased

## For a new or changed check

- [ ] It compares against a null, so it cannot fire on the shape of the table
- [ ] Its verdict tells the reader what to do next
- [ ] New or changed thresholds are in a policy object
- [ ] The reason for each threshold is documented
- [ ] A sensitivity check is included
