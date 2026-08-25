from factories import make_panel

from paneldx import audit, to_html


def test_html_is_self_contained():
    html = to_html(audit(make_panel(), "period", key="uid"))
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "<style>" in html
    assert "<script" not in html
    assert "<link" not in html
    assert "src=" not in html


def test_html_escapes_column_names():
    df = make_panel()
    df["<script>alert(1)</script>"] = df["birth_year"]
    res = audit(df, "period", key="uid")
    assert "<script>alert(1)</script>" in res.chosen.invariant_cols

    html = to_html(res)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
