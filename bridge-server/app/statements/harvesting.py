"""Parses PaytmMoney's "Tax Gain & Loss Harvesting Report" export — legacy
binary .xls (needs xlrd, not openpyxl; confirmed via `file` in task 20).

Real layout verified in task 20: summary figures as (label, ..., 'Realised'|
'Unrealised', amount, explanation) rows in a fixed column arrangement, then
per-holding tables anchored by exact section-label strings. No buy date in
this report (only buy average) — Trade Book covers that gap.
"""

from datetime import datetime
from io import BytesIO

import xlrd

POSITION_HEADER = (
    "Name",
    "",
    "",
    "",
    "ISIN",
    "Quantity",
    "Buy Avg",
    "Buy Value",
    "Closing Price",
    "Present Value",
    "Unrealized P&L",
)

# (sheet name, section label, position "kind")
POSITION_SECTIONS = (
    ("Tax Loss Harvesting", "Short Term Gains Offsetting", "loss_offset_short_term"),
    ("Tax Loss Harvesting", "Long Term Gains Offsetting", "loss_offset_long_term"),
    ("Tax Gain Harvesting", "Long Term Gains Opportunity", "gain_opportunity_long_term"),
)


class HarvestingParseError(ValueError):
    pass


def _parse_as_on_date(raw) -> "datetime.date":
    return datetime.strptime(str(raw).strip(), "%d %b %Y").date()


def _find_value(rows: list[list], label: str, tag: str | None = None) -> float | None:
    """tag=None looks for a bare-labelled amount row (col 0 == label, col 5
    numeric); tag='Realised'/'Unrealised' additionally requires col 4 == tag.
    Distinguishes a summary value row from the identically-worded section
    label row above it, which has no numeric col 5."""
    for row in rows:
        if not row or row[0] != label:
            continue
        if tag is not None and (len(row) <= 4 or row[4] != tag):
            continue
        if len(row) > 5 and isinstance(row[5], (int, float)):
            return float(row[5])
    return None


def _parse_positions(rows: list[list], section_label: str, kind: str) -> list[dict]:
    positions = []
    try:
        label_idx = next(i for i, row in enumerate(rows) if row and row[0] == section_label)
    except StopIteration:
        return positions

    header_idx = next(
        (
            i
            for i in range(label_idx + 1, len(rows))
            if rows[i][: len(POSITION_HEADER)] == list(POSITION_HEADER)
        ),
        None,
    )
    if header_idx is None:
        raise HarvestingParseError(f"Expected a holdings table after {section_label!r}")

    for row in rows[header_idx + 1 :]:
        if not row or not row[0] or str(row[0]).startswith("Important Note"):
            break
        positions.append(
            {
                "kind": kind,
                "scrip_name": str(row[0]),
                "isin": str(row[4]),
                "quantity": float(row[5]),
                "buy_avg": float(row[6]),
                "buy_value": float(row[7]),
                "closing_price": float(row[8]),
                "present_value": float(row[9]),
                "unrealized_pnl": float(row[10]),
            }
        )
    return positions


def parse_harvesting(file_bytes: bytes) -> tuple[dict, list[dict]]:
    """Returns (summary_dict, positions)."""
    try:
        wb = xlrd.open_workbook(file_contents=file_bytes)
    except Exception as e:
        raise HarvestingParseError(f"Not a readable legacy .xls file: {e}") from e

    sheet_rows = {name: [wb.sheet_by_name(name).row_values(r) for r in range(wb.sheet_by_name(name).nrows)] for name in wb.sheet_names()}

    if "Tax Loss Harvesting" not in sheet_rows:
        raise HarvestingParseError("No 'Tax Loss Harvesting' sheet found — unexpected file format")

    loss_rows = sheet_rows["Tax Loss Harvesting"]
    gain_rows = sheet_rows.get("Tax Gain Harvesting", [])

    as_on_date_raw = next(
        (row[2] for row in loss_rows if row and row[0] == "As on Date" and len(row) > 2 and row[2]),
        None,
    )
    financial_year = next(
        (str(row[2]) for row in loss_rows if row and row[0] == "Financial Year" and len(row) > 2 and row[2]),
        None,
    )
    if not as_on_date_raw or not financial_year:
        raise HarvestingParseError("Could not find 'As on Date' / 'Financial Year' — unexpected file format")

    summary = {
        "as_on_date": _parse_as_on_date(as_on_date_raw),
        "financial_year": financial_year,
        "stcg_realized": _find_value(loss_rows, "Short Term Capital Gains - STCG", "Realised") or 0.0,
        "stcl_unrealized": _find_value(loss_rows, "Short Term Capital Losses - STCL", "Unrealised") or 0.0,
        "ltcg_realized": _find_value(loss_rows, "Long Term Capital Gains - LTCG", "Realised") or 0.0,
        "ltcl_unrealized": _find_value(loss_rows, "Long Term Capital Losses - LTCL", "Unrealised") or 0.0,
        "st_harvest_opportunity": _find_value(loss_rows, "Short term tax-loss harvesting opportunity") or 0.0,
        "lt_harvest_opportunity": _find_value(loss_rows, "Long term tax-loss harvesting opportunity") or 0.0,
        "lt_gain_harvest_opportunity": _find_value(gain_rows, "Tax Gain Harvesting Opportunity") or 0.0,
    }

    positions: list[dict] = []
    for sheet_name, section_label, kind in POSITION_SECTIONS:
        positions.extend(_parse_positions(sheet_rows.get(sheet_name, []), section_label, kind))

    return summary, positions
