from app.models import Holding
from app.regions import region_for_exchange


def compute_net_worth_inr(holdings: list[Holding]) -> float:
    return sum(h.market_value_inr for h in holdings)


def compute_total_pnl(holdings: list[Holding]) -> tuple[float, float]:
    """(total_pnl_abs_inr, total_pnl_pct). pnl_abs is stored per-holding in
    native currency — normalized to INR with the same
    market_value_inr/market_value ratio used for today's-move, never a
    naive cross-currency sum. total_pnl_pct is then derived from the
    implied "before" cost basis (net worth minus the pnl total), not
    averaged from each holding's own pnl_pct, which would over-weight
    small positions. Shared by the dashboard endpoint
    (app/routers/dashboard.py) and the daily PortfolioSnapshot write
    (app/scheduler.py, for Milestone's pnl_pct metric type) so the two
    can't silently drift into two different formulas."""
    total_pnl_abs_inr = 0.0
    for h in holdings:
        pnl_fx_factor = (h.market_value_inr / h.market_value) if h.market_value else 1.0
        total_pnl_abs_inr += h.pnl_abs * pnl_fx_factor
    net_worth_inr = compute_net_worth_inr(holdings)
    total_cost_basis_inr = net_worth_inr - total_pnl_abs_inr
    total_pnl_pct = (total_pnl_abs_inr / total_cost_basis_inr * 100) if total_cost_basis_inr else 0.0
    return total_pnl_abs_inr, total_pnl_pct


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
