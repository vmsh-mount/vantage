"""Parses PaytmMoney's "Trade Book" export (.xlsx). Verified against a real
download (task 21 / planning-phase2.md task 20): a metadata block, a blank
row, then one header row, then data rows. Script is PaytmMoney's internal
numeric security code, not a ticker — join to Holding/Threshold via ISIN."""

from datetime import datetime
from io import BytesIO

import openpyxl

HEADER = (
    "Date",
    "Script",
    "ISIN",
    "Exchange",
    "Product Type",
    "Type",
    "Quantity",
    "Price",
    "Brokerage",
    "ETT",
    "GST",
    "STT",
    "SEBI",
    "Stamp Duty",
    "Order Number",
    "Trade Number",
    "Trade Time",
)


class TradebookParseError(ValueError):
    pass


def _parse_date(raw) -> "datetime.date":
    if isinstance(raw, datetime):
        return raw.date()
    return datetime.strptime(str(raw).strip(), "%d-%m-%Y").date()


def parse_tradebook(file_bytes: bytes) -> list[dict]:
    try:
        wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise TradebookParseError(f"Not a readable .xlsx file: {e}") from e
    ws = wb.worksheets[0]

    rows = list(ws.iter_rows(values_only=True))
    header_idx = next(
        (i for i, row in enumerate(rows) if row[: len(HEADER)] == HEADER),
        None,
    )
    if header_idx is None:
        raise TradebookParseError("Could not find the Trade Book header row — unexpected file format")

    trades = []
    for row_number, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if not row or row[0] is None:
            continue
        (
            date_raw,
            script,
            isin,
            exchange,
            product_type,
            txn_type,
            quantity,
            price,
            brokerage,
            ett,
            gst,
            stt,
            sebi,
            stamp_duty,
            order_number,
            trade_number,
            trade_time,
        ) = row[: len(HEADER)]
        trades.append(
            {
                "row_number": row_number,
                "trade_date": _parse_date(date_raw),
                "script_code": str(script),
                "isin": str(isin),
                "exchange": str(exchange),
                "product_type": str(product_type),
                "txn_type": str(txn_type),
                "quantity": float(quantity),
                "price": float(price),
                "brokerage": float(brokerage or 0),
                "ett": float(ett or 0),
                "gst": float(gst or 0),
                "stt": float(stt or 0),
                "sebi": float(sebi or 0),
                "stamp_duty": float(stamp_duty or 0),
                "order_number": str(order_number),
                "trade_number": str(trade_number),
                "trade_time": str(trade_time) if trade_time else None,
            }
        )
    return trades
