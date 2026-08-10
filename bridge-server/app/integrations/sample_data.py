from app.integrations.base import NormalizedHolding

PAYTMMONEY_HOLDINGS: list[NormalizedHolding] = [
    NormalizedHolding(
        broker="paytmmoney", symbol="RELIANCE", exchange="NSE", isin="INE002A01018",
        quantity=50, avg_cost=2350, ltp=2480, close_price=2470,
        currency="INR", market_value=124000, pnl_abs=6500, pnl_pct=5.53,
        sector="Energy", asset_class="india_equity",
    ),
    NormalizedHolding(
        broker="paytmmoney", symbol="INFY", exchange="NSE", isin="INE009A01021",
        quantity=95, avg_cost=1550, ltp=1423, close_price=1440,
        currency="INR", market_value=135185, pnl_abs=-12065, pnl_pct=-8.19,
        sector="Technology", asset_class="india_equity",
    ),
    NormalizedHolding(
        broker="paytmmoney", symbol="TCS", exchange="NSE", isin="INE467B01029",
        quantity=40, avg_cost=3550, ltp=3820, close_price=3600,
        currency="INR", market_value=152800, pnl_abs=10800, pnl_pct=7.61,
        sector="Technology", asset_class="india_equity",
    ),
    NormalizedHolding(
        broker="paytmmoney", symbol="HDFCBANK", exchange="NSE", isin="INE040A01034",
        quantity=60, avg_cost=1650, ltp=1690, close_price=1685,
        currency="INR", market_value=101400, pnl_abs=2400, pnl_pct=2.42,
        sector="Financials", asset_class="india_equity",
    ),
]

INDMONEY_HOLDINGS: list[NormalizedHolding] = [
    NormalizedHolding(
        broker="indmoney", symbol="ICICIBANK", exchange="NSE", isin="INE090A01021",
        quantity=70, avg_cost=1100, ltp=1145, close_price=1140,
        currency="INR", market_value=80150, pnl_abs=3150, pnl_pct=4.09,
        sector="Financials", asset_class="india_equity",
    ),
]
