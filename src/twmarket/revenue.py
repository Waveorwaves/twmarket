"""MOPS monthly revenue: bulk-file parsing and (later) point-in-time queries."""

from __future__ import annotations

import re

import pandas as pd

# Data rows are <tr align=right> with 11 <td> cells; industry-total (合計) rows use
# <th> cells inside the same <tr> pattern and are skipped by requiring an all-<td> row.
_ROW_RE = re.compile(r"<tr align=right>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(cell: str) -> str:
    return _TAG_RE.sub("", cell).replace("&nbsp;", " ").strip()


def _num(text: str) -> float | None:
    text = text.replace(",", "").strip()
    if text in ("", "-"):
        return None
    return float(text)


def parse_bulk_file(content: bytes, period: str) -> pd.DataFrame:
    """Parse one MOPS t21sc03 bulk file (raw Big5 bytes) into a DataFrame.

    Columns: ticker, name, period, revenue_twd (source is thousand NTD; converted
    to NTD here), yoy_pct, mom_pct. Industry 合計 (total) rows are excluded.
    """
    text = content.decode("big5", errors="replace")
    records = []
    for row in _ROW_RE.findall(text):
        if "合計" in row:
            continue
        cells = [_clean(c) for c in _CELL_RE.findall(row)]
        if len(cells) != 11 or not re.fullmatch(r"\d{4,6}", cells[0]):
            continue
        revenue = _num(cells[2])
        records.append(
            {
                "ticker": cells[0],
                "name": cells[1],
                "period": period,
                "revenue_twd": None if revenue is None else int(revenue * 1000),
                "mom_pct": _num(cells[5]),
                "yoy_pct": _num(cells[6]),
            }
        )
    df = pd.DataFrame.from_records(
        records, columns=["ticker", "name", "period", "revenue_twd", "mom_pct", "yoy_pct"]
    )
    df["revenue_twd"] = df["revenue_twd"].astype("Int64")
    return df
