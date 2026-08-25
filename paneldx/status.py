from collections.abc import Iterable
from typing import Literal

Status = Literal["pass", "warn", "fail", "inconclusive"]

PASS: Status = "pass"
WARN: Status = "warn"
FAIL: Status = "fail"
INCONCLUSIVE: Status = "inconclusive"

PRIORITY = {
    FAIL: 0,
    INCONCLUSIVE: 1,
    WARN: 2,
    PASS: 3,
}


def worst(statuses: Iterable[Status]) -> Status:
    return min(statuses, key=PRIORITY.__getitem__, default=INCONCLUSIVE)
