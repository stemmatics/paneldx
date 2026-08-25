"""Command line entry point.

    paneldx audit data.csv --time quarter
    paneldx audit panel.xlsx --time t --key patient_id --target risk --html out.html

Exits 1 when the audit finds a defect that invalidates within-entity analysis,
and 2 when the evidence was insufficient to reach any verdict at all.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from .audit import audit
from .report import to_html
from .status import FAIL, INCONCLUSIVE, PASS, WARN

_LOADERS: dict[str, Callable[[Path], pd.DataFrame]] = {
    ".csv": pd.read_csv,
    ".tsv": lambda p: pd.read_csv(p, sep="\t"),
    ".parquet": pd.read_parquet,
    ".feather": pd.read_feather,
    ".json": pd.read_json,
}
_EXCEL = {".xlsx"}

# Exhaustive on purpose: an unknown status must crash in development, not
# silently exit 0 from a gate.
_EXIT = {PASS: 0, WARN: 0, FAIL: 1, INCONCLUSIVE: 2}


def _sheet(value: str) -> str | int:
    """`--sheet 0` means the first sheet, not a sheet named "0"."""
    try:
        return int(value)
    except ValueError:
        return value


def _period_step(value: str) -> int | float | str:
    """`--period-step 3` is a numeric step; `--period-step QS` is a frequency."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _load(path: Path, sheet: str | int | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in _EXCEL:
        return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
    loader = _LOADERS.get(suffix)
    if loader is None:
        raise SystemExit(
            f"paneldx: don't know how to read {suffix or 'a file with no extension'!r}. "
            f"Supported: {', '.join(sorted(set(_LOADERS) | _EXCEL))}"
        )
    return loader(path)


def _add_audit_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("data", type=Path, help="CSV, TSV, Excel, Parquet, Feather or JSON")
    p.add_argument("--time", required=True, metavar="COL", help="column holding the period")
    p.add_argument(
        "--key", nargs="+", metavar="COL", help="entity key to validate (omit to search for one)"
    )
    p.add_argument(
        "--target", metavar="COL", help="target column, to test for leakage and persistence"
    )
    p.add_argument(
        "--html", type=Path, metavar="PATH", help="also write a standalone HTML report here"
    )
    p.add_argument(
        "--sheet", type=_sheet, default=None, help="Excel sheet name or zero-based index"
    )
    p.add_argument(
        "--max-columns",
        type=int,
        default=2,
        metavar="N",
        help="largest key combination to search (default 2)",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=3,
        metavar="N",
        help="how many key candidates to report (default 3)",
    )
    p.add_argument(
        "--period-step",
        type=_period_step,
        default=None,
        metavar="STEP",
        help="cadence of the period column for the persistence "
        "baseline: a number for numeric periods (default 1) or "
        "a pandas frequency such as QS, MS or 7D for dates",
    )
    p.add_argument(
        "--allow-weak-key",
        action="store_true",
        help="run counter and persistence checks under a weakly "
        "supported key as well as a supported one",
    )
    p.add_argument("--quiet", action="store_true", help="print findings only")


def _run_audit(args: argparse.Namespace) -> int:
    if not args.data.exists():
        raise SystemExit(f"paneldx: no such file: {args.data}")

    try:
        df = _load(args.data, args.sheet)
    except SystemExit:
        raise
    except ImportError as exc:
        raise SystemExit(
            f"paneldx: reading {args.data.suffix!r} files needs an optional "
            f"dependency that is not installed ({exc.name})"
        ) from exc
    except Exception as exc:
        raise SystemExit(f"paneldx: could not read {args.data.name}: {exc}") from exc

    try:
        result = audit(
            df,
            args.time,
            key=args.key,
            target=args.target,
            max_columns=args.max_columns,
            top_k=args.top_k,
            period_step=args.period_step,
            allow_weak_key=args.allow_weak_key,
            source=args.data.name,
        )
    except (KeyError, TypeError, ValueError) as exc:
        # Expected input errors become one clear CLI line, not a traceback.
        msg = exc.args[0] if exc.args else exc
        raise SystemExit(f"paneldx: {msg}") from exc

    print(
        f"\n{args.data.name}: {result.n_rows:,} rows x {result.n_columns} columns, "
        f"{result.n_periods} periods of '{result.time_col}'\n"
    )

    for f in result.findings:
        print(f"  [{f.status.upper()}]  {f.headline}")
        print(f"          {f.detail}\n")

    if not args.quiet:
        if result.chosen is not None:
            print("-" * 62)
            print(result.chosen)
        if result.counters is not None and result.counters.counters:
            print("\n" + "-" * 62)
            print(result.counters)
        if result.leakage is not None:
            print("\n" + "-" * 62)
            print(result.leakage)
        if result.baseline is not None:
            print("\n" + "-" * 62)
            print(result.baseline)

    if args.html:
        try:
            args.html.write_text(
                to_html(result, title=f"paneldx: {args.data.name}"), encoding="utf-8"
            )
        except OSError as exc:
            raise SystemExit(f"paneldx: could not write report: {exc}") from exc
        print(f"\nreport written to {args.html}")

    return _EXIT[result.worst]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="paneldx",
        description="Check that a longitudinal dataset is what it claims to be.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _add_audit_args(sub.add_parser("audit", help="run every check over a panel"))

    args = parser.parse_args(argv)
    if args.command == "audit":
        return _run_audit(args)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
