from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.tax_suggestion import TaxSuggestion, TaxSuggestionsOut
from app.tax.suggestions import get_tax_suggestions

router = APIRouter()


@router.get("/api/tax/suggestions", response_model=TaxSuggestionsOut)
def list_tax_suggestions(db: Session = Depends(get_db)) -> TaxSuggestionsOut:
    suggestions = get_tax_suggestions(db)
    return TaxSuggestionsOut(suggestions=[TaxSuggestion(**s) for s in suggestions])
