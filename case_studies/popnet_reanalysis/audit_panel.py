"""Audit the physician panel under the positional key and the candidate key.

    python case_studies/popnet_reanalysis/audit_panel.py --data /path/to/workbook.xlsx

The dataset is not distributed. It holds attributes inferred from photographs
of identifiable physicians and is sensitive personal information under PIPL
and GDPR Article 9. Point this script at an authorised copy.

Results are compared with expected_results.json, which records summary values
from a post-publication audit. They are not corrected PopNet results.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from paneldx import discover_keys, persistence_baseline, target_leakage, validate_key

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from prepare_data import add_positional_id  # noqa: E402

EXPECTED = json.loads((HERE / "expected_results.json").read_text())


def audit(df, time_col, target=None, period_step=1):
    recovered = EXPECTED["recovered_key"]["columns"]
    out = {
        "positional_key": validate_key(df, "positional_id", time_col),
        "recovered_key": validate_key(df, recovered, time_col),
        "discovered": discover_keys(df, time_col, max_columns=2, top_k=3),
    }
    if target:
        out["leakage"] = target_leakage(df, target)
        out["persistence"] = {
            "positional": persistence_baseline(
                df, "positional_id", time_col, target, period_step=period_step
            ),
            "recovered": persistence_baseline(
                df, recovered, time_col, target, period_step=period_step
            ),
        }
    return out


def compare(results):
    rows = []
    for name in ("positional_key", "recovered_key"):
        rep, exp = results[name], EXPECTED[name]
        rows.append((f"{name} status", exp["status"], rep.status))
        rows.append(
            (f"{name} evidence fraction", exp["evidence_fraction"], round(rep.evidence_frac, 3))
        )
    if "leakage" in results:
        rows.append(
            (
                "target reconstruction R2",
                EXPECTED["target_reconstruction_r2"],
                round(results["leakage"].r2, 3),
            )
        )
        for which, rep in results["persistence"].items():
            exp = EXPECTED["persistence"][which]
            rows.append((f"{which} persistence MAE", exp["mae"], round(rep.persistence_mae, 4)))
            rows.append((f"{which} persistence R2", exp["r2"], round(rep.persistence_r2, 3)))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--time-col", default="time")
    ap.add_argument("--serial-col", default="Serial number")
    ap.add_argument("--target")
    ap.add_argument("--write", help="write observed values to this JSON file")
    args = ap.parse_args()

    df = add_positional_id(
        pd.read_excel(args.data, sheet_name=args.sheet), args.time_col, args.serial_col
    )
    results = audit(df, args.time_col, args.target)

    print(f"{'measure':34} {'expected':>10} {'observed':>10}")
    for label, expected, observed in compare(results):
        print(f"{label:34} {expected!s:>10} {observed!s:>10}")
    print("\ndiscovered keys:")
    for rep in results["discovered"]:
        print(f"  {' + '.join(rep.key):30} {rep.status:12} explains {rep.evidence_frac:.0%}")

    if args.write:
        observed = {label: observed for label, _, observed in compare(results)}
        Path(args.write).write_text(json.dumps(observed, indent=2))
        print(f"\nwrote {args.write}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
