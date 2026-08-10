from pydantic import BaseModel


class TradebookSkippedRow(BaseModel):
    row_number: int
    reason: str


class TradebookImportOut(BaseModel):
    imported: int
    duplicates_skipped: int
    skipped: list[TradebookSkippedRow]


class TaxPnlImportOut(BaseModel):
    financial_year: str
    lots_imported: int
    previous_lots_replaced: int


class HarvestingImportOut(BaseModel):
    as_on_date: str
    positions_imported: int
    previous_positions_replaced: int
