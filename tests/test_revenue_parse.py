from pathlib import Path

import pytest

from twmarket.revenue import parse_bulk_file

FIXTURE = Path(__file__).parent / "fixtures" / "t21sc03_114_6_0.html"
UNPUBLISHED = Path(__file__).parent / "fixtures" / "t21sc03_115_9_0_unpublished.html"
JAN_2013 = Path(__file__).parent / "fixtures" / "t21sc03_102_1_0_head.html"


def _parse():
    return parse_bulk_file(FIXTURE.read_bytes(), "2025-06")


def test_parses_all_companies_no_totals():
    df = _parse()
    assert len(df) > 900  # ~all TWSE-listed companies
    assert (df["name"] != "合計").all()
    assert df["ticker"].str.fullmatch(r"\d{4,6}").all()
    assert not df["ticker"].duplicated().any()


def test_tsmc_row_matches_fixture():
    df = _parse()
    row = df[df["ticker"] == "2330"].iloc[0]
    assert row["name"] == "台積電"
    # Fixture shows 263,708,978 thousand NTD for 2330 in 114/6
    assert row["revenue_twd"] == 263_708_978_000
    assert row["mom_pct"] == -17.72
    assert row["yoy_pct"] == 26.86
    assert row["period"] == "2025-06"


def test_first_company_1101():
    df = _parse()
    row = df[df["ticker"] == "1101"].iloc[0]
    assert row["name"] == "台泥"
    assert row["revenue_twd"] == 10_107_877_000


def test_columns_and_dtypes():
    df = _parse()
    assert list(df.columns) == ["ticker", "name", "period", "revenue_twd", "mom_pct", "yoy_pct"]
    assert str(df["revenue_twd"].dtype) == "Int64"
    assert df["yoy_pct"].dtype == "float64"


def test_unpublished_month_parses_to_empty():
    # A month nobody has filed yet is not an HTTP error: MOPS answers 200 with a
    # short 查無資料 ("no data found") page. Recorded for 115/9 on 2026-09-28.
    df = parse_bulk_file(UNPUBLISHED.read_bytes(), "2026-09")
    assert df.empty
    assert list(df.columns) == ["ticker", "name", "period", "revenue_twd", "mom_pct", "yoy_pct"]


def test_zero_rows_without_the_no_data_page_raises():
    # The first 2 KB of a real file: the page header, no data rows, no 查無資料.
    # That is what a MOPS layout change looks like, and it must not pass as an
    # empty month — an empty month is stored as settled and never re-fetched.
    with pytest.raises(ValueError, match="layout"):
        parse_bulk_file(FIXTURE.read_bytes()[:2000], "2025-06")


def test_empty_response_raises():
    with pytest.raises(ValueError, match="layout"):
        parse_bulk_file(b"", "2025-06")


def test_not_applicable_cells_parse_as_missing():
    # January 2013 was the first month of IFRS consolidated reporting, so there is
    # no prior month to compare with: MOPS prints 不適用 ("not applicable") there.
    # Fixture: the first 40 rows of the real 102/1 file, recorded 2026-10-01.
    df = parse_bulk_file(JAN_2013.read_bytes(), "2013-01")
    row = df[df["ticker"] == "1101"].iloc[0]
    assert row["revenue_twd"] > 0
    assert df["mom_pct"].isna().all()
    assert df["yoy_pct"].notna().any()
