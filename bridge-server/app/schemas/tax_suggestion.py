from pydantic import BaseModel


class TaxSuggestion(BaseModel):
    kind: str  # "harvest_loss" | "harvest_gain" | "ltcg_crossing_soon"
    isin: str
    scrip_name: str
    headline: str
    amount_inr: float | None = None


class TaxSuggestionsOut(BaseModel):
    suggestions: list[TaxSuggestion]
