"""Enforce the god_function thresholds declared in .slopconfig.yaml.

    python -m scripts.check_complexity

Reports every function in paneldx/, scripts/ and validation/ above the
configured complexity or line limits, excluding the reviewed suppressions the
config lists. Exits non-zero on anything unsuppressed, so a new violation fails
CI while the reviewed ones do not.

This is a deterministic subset of the project's AI/code-quality scan, not a
replacement for it: it enforces one rule the config states, with no dependency
beyond the standard library.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".slopconfig.yaml"
SCOPES = ("paneldx", "scripts", "validation")

# Nodes that add a branch to a function's cyclomatic complexity.
BRANCHING = (
    ast.If,
    ast.For,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.Assert,
    ast.With,
    ast.comprehension,
)


def read_config(path: Path = CONFIG) -> tuple[int, int, set[str]]:
    """Thresholds and suppressions, read without a YAML dependency.

    The file is small and its shape is fixed by this project, so a couple of
    regexes are cheaper than adding PyYAML to the lint environment.
    """
    text = path.read_text()
    complexity = re.search(r"complexity_threshold:\s*(\d+)", text)
    lines = re.search(r"lines_threshold:\s*(\d+)", text)
    if not complexity or not lines:
        raise SystemExit(f"{path.name} declares no god_function thresholds")

    suppressions = set()
    block = re.search(r"god_function_suppressions:\n((?:\s*-\s*\S+\n?)+)", text)
    if block:
        suppressions = set(re.findall(r"-\s*(\S+)", block.group(1)))
    return int(complexity.group(1)), int(lines.group(1)), suppressions


def complexity_of(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, BRANCHING):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
    return score


def violations(max_complexity: int, max_lines: int) -> list[tuple[str, int, int]]:
    found = []
    for scope in SCOPES:
        for path in sorted((ROOT / scope).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                score = complexity_of(node)
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                if score > max_complexity or length > max_lines:
                    name = f"{path.relative_to(ROOT)}::{node.name}"
                    found.append((name, score, length))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args(argv)

    max_complexity, max_lines, suppressed = read_config(args.config)
    found = violations(max_complexity, max_lines)
    unsuppressed = [v for v in found if v[0] not in suppressed]

    print(f"thresholds: complexity <= {max_complexity}, lines <= {max_lines}")
    for name, score, length in sorted(found, key=lambda v: -v[1]):
        mark = "suppressed" if name in suppressed else "FAIL      "
        print(f"  {mark}  {name:44} complexity={score:2} lines={length:3}")

    stale = sorted(suppressed - {name for name, _, _ in found})
    for name in stale:
        print(f"  stale suppression, no longer over threshold: {name}")

    if unsuppressed:
        print(f"\n{len(unsuppressed)} unsuppressed violation(s)")
        return 1
    print(f"\nno unsuppressed violations ({len(found)} reviewed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
