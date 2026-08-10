import time

import httpx

from app.config import settings

FX_URL = "https://api.frankfurter.dev/v1/latest"
_CACHE_TTL_SECONDS = 300

_cache: dict = {"rate": None, "fetched_at": 0.0}


def get_usd_inr_rate() -> float:
    now = time.monotonic()
    if _cache["rate"] is not None and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
        return _cache["rate"]

    try:
        response = httpx.get(FX_URL, params={"from": "USD", "to": "INR"}, timeout=10)
        response.raise_for_status()
        rate = float(response.json()["rates"]["INR"])
        _cache["rate"] = rate
        _cache["fetched_at"] = now
        return rate
    except (httpx.HTTPError, KeyError, ValueError):
        if settings.fx_manual_rate is not None:
            return settings.fx_manual_rate
        raise
