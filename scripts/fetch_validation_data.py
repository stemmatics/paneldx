"""Download the public panels listed in tests/validation/panels.json.

The files are not committed; run this once before `pytest tests/validation`.
"""

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests" / "validation"


def main() -> int:
    cases = json.loads((ROOT / "panels.json").read_text())
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    for case in cases:
        target = data / case["file"]
        if target.exists():
            print(f"have    {target.name}")
            continue
        print(f"fetch   {case['source_url']}")
        urllib.request.urlretrieve(case["source_url"], target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
