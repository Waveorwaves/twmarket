from pathlib import Path

from twmarket.revenue import parse_bulk_file

FIXTURE = Path(__file__).parent / "fixtures" / "t21sc03_114_6_0.html"


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
