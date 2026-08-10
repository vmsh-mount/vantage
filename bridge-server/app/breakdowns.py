from app.models import Holding
from app.regions import region_for_exchange


def compute_net_worth_inr(holdings: list[Holding]) -> float:
    return sum(h.market_value_inr for h in holdings)


def compute_breakdown_sums(holdings: list[Holding]) -> dict[str, dict[str, float]]:
    by_broker: dict[str, float] = {}
    by_asset_class: dict[str, float] = {}
    by_sector: dict[str, float] = {}
    by_region: dict[str, float] = {}
    for h in holdings:
        by_broker[h.broker] = by_broker.get(h.broker, 0) + h.market_value_inr
        by_asset_class[h.asset_class] = by_asset_class.get(h.asset_class, 0) + h.market_value_inr
        sector = h.sector or "Unknown"
        by_sector[sector] = by_sector.get(sector, 0) + h.market_value_inr
        region = region_for_exchange(h.exchange)
        by_region[region] = by_region.get(region, 0) + h.market_value_inr
    return {
        "by_broker": by_broker,
        "by_asset_class": by_asset_class,
        "by_sector": by_sector,
        "by_region": by_region,
    }
