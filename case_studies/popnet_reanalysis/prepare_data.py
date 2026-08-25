"""Reconstruct the positional identifier used by the original pipeline.

The original preprocessing sorted each quarter by platform rank and then
assigned an identifier from the row's serial number:

    positional_id = ((serial_number - 1) % rows_per_quarter) + 1

Position i therefore named a different physician in every quarter.
"""

import argparse
import sys

import pandas as pd


def add_positional_id(df, time_col="time", serial_col="Serial number"):
    rows_per_period = len(df) // df[time_col].nunique()
    out = df.copy()
    out["positional_id"] = ((out[serial_col] - 1) % rows_per_period) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="authorised copy of the physician workbook")
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--time-col", default="time")
    ap.add_argument("--serial-col", default="Serial number")
    ap.add_argument("--out", required=True, help="CSV to write with positional_id added")
    args = ap.parse_args()

    df = pd.read_excel(args.data, sheet_name=args.sheet)
    add_positional_id(df, args.time_col, args.serial_col).to_csv(args.out, index=False)
    print(f"wrote {args.out}: {len(df):,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
