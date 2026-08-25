"""Render a standalone HTML audit report."""

from __future__ import annotations

import math
from collections.abc import Iterable
from html import escape

from .audit import AuditResult
from .keys import KeyReport

_CSS = """
:root {
  --bg: #ffffff; --panel: #f7f8fa; --border: #e3e6ea;
  --fg: #14171a; --muted: #5b6570;
  --fail: #c0392b; --warn: #a86612; --pass: #1f7a4d; --inconclusive: #44559e;
  --fail-bg: #fdeceb; --warn-bg: #fdf4e3; --pass-bg: #e9f6ef;
  --inconclusive-bg: #eceffb;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171a; --panel: #1c2024; --border: #2b3138;
    --fg: #e8eaed; --muted: #99a2ad;
    --fail: #ff8a80; --warn: #ffc46b; --pass: #78d9a6; --inconclusive: #9fb1f5;
    --fail-bg: #2e1b1a; --warn-bg: #2d2416; --pass-bg: #14291f;
    --inconclusive-bg: #1b2138;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2.5rem 1.5rem; background: var(--bg); color: var(--fg);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 860px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; letter-spacing: -.01em; }
h2 { font-size: 1rem; margin: 2.5rem 0 .75rem; text-transform: uppercase;
     letter-spacing: .06em; color: var(--muted); font-weight: 600; }
.sub { color: var(--muted); margin: 0 0 2rem; font-size: .9rem; }
.sub code { font-family: var(--mono); font-size: .85em; }

.banner { border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 2rem;
          border: 1px solid; font-weight: 600; }
.banner.fail { background: var(--fail-bg); border-color: var(--fail); color: var(--fail); }
.banner.warn { background: var(--warn-bg); border-color: var(--warn); color: var(--warn); }
.banner.pass { background: var(--pass-bg); border-color: var(--pass); color: var(--pass); }
.banner.inconclusive { background: var(--inconclusive-bg);
                       border-color: var(--inconclusive); color: var(--inconclusive); }

.finding { display: flex; gap: .9rem; padding: .9rem 0; border-top: 1px solid var(--border); }
.finding:last-child { border-bottom: 1px solid var(--border); }
.chip { flex: none; font-size: .7rem; font-weight: 700; letter-spacing: .06em;
        padding: .18rem .5rem; border-radius: 4px; height: fit-content; margin-top: .15rem; }
.chip.fail { background: var(--fail-bg); color: var(--fail); }
.chip.warn { background: var(--warn-bg); color: var(--warn); }
.chip.pass { background: var(--pass-bg); color: var(--pass); }
.chip.inconclusive { background: var(--inconclusive-bg); color: var(--inconclusive); }
.finding-head { font-weight: 600; }
.finding-detail { color: var(--muted); font-size: .9rem; margin-top: .15rem; }

.card { background: var(--panel); border: 1px solid var(--border);
        border-radius: 10px; padding: 1.1rem 1.25rem; margin-bottom: .9rem; }
.card h3 { margin: 0 0 .75rem; font-size: .95rem; font-family: var(--mono); }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
td, th { padding: .3rem 0; vertical-align: top; }
th { color: var(--muted); width: 45%; padding-right: 1rem;
     text-align: left; font-weight: 400; }
td.num { font-family: var(--mono); }
.cols { font-family: var(--mono); font-size: .82rem; color: var(--muted);
        word-break: break-word; }
.scroll { overflow-x: auto; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
         color: var(--muted); font-size: .82rem; }
"""

_LABEL = {"fail": "FAIL", "warn": "WARN", "pass": "PASS", "inconclusive": "INCONCLUSIVE"}
_BANNER = {
    "fail": "The audit found at least one failure.",
    "warn": "The audit found conditions requiring review.",
    "pass": "All completed checks passed.",
    "inconclusive": "At least one required check was inconclusive.",
}


def _num(value: float, digits: int = 3) -> str:
    """Format a finite measurement."""
    return f"{value:.{digits}f}" if math.isfinite(value) else "not available"


def _rows(pairs: Iterable[tuple[str, str]]) -> str:
    return "".join(
        f"<tr><th scope='row'>{escape(k)}</th><td class='num'>{escape(str(v))}</td></tr>"
        for k, v in pairs
    )


def _key_card(rep: KeyReport, *, primary: bool) -> str:
    title = " + ".join(rep.key)
    pairs = [
        ("verdict", rep.verdict),
        (
            "columns explained",
            f"{rep.evidence:.0f} of {rep.n_usable_cols} ({rep.evidence_frac:.0%})",
        ),
        ("entities", f"{rep.n_entities:,}"),
        ("row coverage", f"{rep.coverage:.1%}"),
        ("duplicate cells", f"{rep.duplicate_rate:.2%}"),
        (
            "invariance breach",
            f"{_num(rep.invariance_violation)} (shuffled {_num(rep.null_invariance_violation)})",
        ),
        (
            "monotonicity breach",
            f"{_num(rep.monotonicity_violation)} "
            f"(shuffled {_num(rep.null_monotonicity_violation)})",
        ),
    ]
    extra = ""
    if primary:
        if rep.invariant_cols:
            extra += (
                f"<p class='cols'><strong>invariants:</strong> "
                f"{escape(', '.join(rep.invariant_cols))}</p>"
            )
        if rep.monotone_cols:
            extra += (
                f"<p class='cols'><strong>counters:</strong> "
                f"{escape(', '.join(rep.monotone_cols))}</p>"
            )
    return (
        f"<div class='card'><h3>{escape(title)}</h3>"
        f"<div class='scroll'><table>{_rows(pairs)}</table></div>{extra}</div>"
    )


def to_html(result: AuditResult, *, title: str = "paneldx audit") -> str:
    """Build a self-contained HTML page for `result`."""
    src = result.source or "dataframe"
    sub = (
        f"<code>{escape(src)}</code> &middot; {result.n_rows:,} rows &times; "
        f"{result.n_columns} columns &middot; {result.n_periods} periods "
        f"of <code>{escape(result.time_col)}</code>"
    )
    if result.target:
        sub += f" &middot; target <code>{escape(result.target)}</code>"

    findings = "".join(
        f"<div class='finding'><span class='chip {f.status}'>{_LABEL[f.status]}</span>"
        f"<div><div class='finding-head'>{escape(f.headline)}</div>"
        f"<div class='finding-detail'>{escape(f.detail)}</div></div></div>"
        for f in result.findings
    )

    body = [
        f"<h1>{escape(title)}</h1>",
        f"<p class='sub'>{sub}</p>",
        f"<div class='banner {result.worst}'>{escape(_BANNER[result.worst])}</div>",
        "<h2>Findings</h2>",
        findings or "<p class='sub'>Nothing to report.</p>",
    ]

    if result.key_reports:
        heading = "Entity key" if result.key_was_supplied else "Entity key candidates"
        body.append(f"<h2>{escape(heading)}</h2>")
        for i, rep in enumerate(result.key_reports):
            body.append(_key_card(rep, primary=(i == 0)))

    if result.counters and result.counters.counters:
        body.append("<h2>Cumulative counters</h2>")
        pairs = [
            (
                c,
                "lag-1 autocorrelation "
                + _num(result.counters.autocorrelation.get(c, float("nan")), 4),
            )
            for c in result.counters.counters
        ]
        body.append(
            "<div class='card'><div class='scroll'><table>"
            + _rows(pairs)
            + "</table></div><p class='cols'>These columns rarely decrease "
            "within an entity. Use per-period changes when the modelling "
            "question concerns new activity.</p></div>"
        )

    if result.leakage is not None:
        lk = result.leakage
        pairs = [
            ("held-out R²", _num(lk.r2, 4)),
            ("numeric features tested", str(lk.n_features)),
            ("verdict", lk.verdict),
        ]
        if lk.top_contributors:
            pairs.append(
                (
                    "largest standardised coefficients",
                    ", ".join(f"{n} ({w:+.2f})" for n, w in lk.top_contributors),
                )
            )
        body.append("<h2>Target leakage</h2>")
        body.append(
            f"<div class='card'><div class='scroll'><table>{_rows(pairs)}</table></div></div>"
        )

    if result.baseline is not None:
        bl = result.baseline
        pairs = [
            ("period step", bl.period_step or "not declared"),
            ("adjacent pairs", f"{bl.n_pairs:,}"),
            ("gapped pairs excluded", f"{bl.n_gapped_pairs:,}"),
            ("duplicate entity-period cells", f"{bl.n_duplicate_cells:,}"),
            ("target lag-1 autocorrelation", _num(bl.target_autocorrelation, 4)),
            ("carry-forward MAE", _num(bl.persistence_mae, 4)),
            ("carry-forward R²", _num(bl.persistence_r2, 4)),
            ("verdict", bl.verdict),
        ]
        body.append("<h2>Persistence baseline</h2>")
        body.append(
            f"<div class='card'><div class='scroll'><table>{_rows(pairs)}"
            "</table></div><p class='cols'>Report every model on this target "
            "against these numbers.</p></div>"
        )

    body.append(
        "<footer>Generated by "
        "<a href='https://github.com/stemmatics/paneldx'>paneldx</a>. "
        "A supported key remains subject to domain validation."
        "</footer>"
    )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{_CSS}</style></head>"
        f"<body><div class='wrap'>{''.join(body)}</div></body></html>"
    )
