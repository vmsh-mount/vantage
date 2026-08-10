from datetime import datetime, timedelta, timezone
from statistics import pstdev

from sqlalchemy.orm import Session

from app.models import Holding, HoldingSnapshot
from app.schemas.trajectory import TrajectoryOut

MIN_DAYS_FOR_STATS = 5
Z_UNUSUAL_THRESHOLD = 1.5
STREAK_THRESHOLD = 3
NEAR_EXTREME_FRACTION = 0.005  # 0.5%


def _today_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _snapshot_delta_move(
    db: Session, broker: str, symbol: str, today_start: datetime
) -> tuple[float | None, float | None]:
    # Fallback for when a broker doesn't supply close_price (see architecture.md's
    # Data Model note). "Today" is bucketed in UTC rather than IST market hours —
    # currently harmless by coincidence, not by design: NSE's full session
    # (3:45-10:00 UTC) sits inside one UTC day, and manual (US) holdings never
    # reach this path at all (pricing="static"). Would need revisiting if a
    # non-India live broker with different market hours were ever added.
    snapshots = (
        db.query(HoldingSnapshot)
        .filter(
            HoldingSnapshot.broker == broker,
            HoldingSnapshot.symbol == symbol,
            HoldingSnapshot.captured_at >= today_start,
        )
        .order_by(HoldingSnapshot.captured_at)
        .all()
    )
    if len(snapshots) < 2 or snapshots[0].market_value_inr == 0:
        return None, None
    first, latest = snapshots[0], snapshots[-1]
    abs_move = latest.market_value_inr - first.market_value_inr
    pct_move = abs_move / first.market_value_inr * 100
    return abs_move, pct_move


def compute_today_move(db: Session, h: Holding) -> tuple[float | None, float | None, str]:
    """Shared by the Dashboard's per-holding move and Trajectory's z-score
    baseline, and by Alerts (task 8) — one definition of "today's move", not
    several that could quietly disagree."""
    if h.source == "manual":
        return None, None, "static"

    if h.close_price is not None and h.close_price != 0:
        # Scale the native-currency move by the same INR-per-unit rate already
        # implied by market_value_inr/market_value, so this works whether the
        # holding is INR (factor 1.0) or a future USD broker holding, without a
        # separate FX lookup here.
        fx_factor = (h.market_value_inr / h.market_value) if h.market_value else 1.0
        abs_move = h.quantity * (h.ltp - h.close_price) * fx_factor
        pct_move = (h.ltp - h.close_price) / h.close_price * 100
        return abs_move, pct_move, "live"

    abs_move, pct_move = _snapshot_delta_move(db, h.broker, h.symbol, _today_start())
    return abs_move, pct_move, "live"


def _daily_closes(db: Session, broker: str, symbol: str, today_start: datetime) -> list[float]:
    """One closing ltp per calendar day (last snapshot of that day), trailing
    30 days, excluding today (today's value comes from the live Holding.ltp,
    appended separately by the caller)."""
    window_start = today_start - timedelta(days=30)
    rows = (
        db.query(HoldingSnapshot)
        .filter(
            HoldingSnapshot.broker == broker,
            HoldingSnapshot.symbol == symbol,
            HoldingSnapshot.captured_at >= window_start,
            HoldingSnapshot.captured_at < today_start,
        )
        .order_by(HoldingSnapshot.captured_at)
        .all()
    )
    by_day: dict = {}
    for row in rows:
        by_day[row.captured_at.date()] = row.ltp  # last write per day wins (ascending order)
    return [by_day[d] for d in sorted(by_day.keys())]


def compute_trajectory(db: Session, h: Holding, today_move_pct: float | None) -> TrajectoryOut:
    if h.source == "manual":
        return TrajectoryOut(static=True)

    historical = _daily_closes(db, h.broker, h.symbol, _today_start())
    n = len(historical)
    days_available = n + 1  # +1 for today

    if n < MIN_DAYS_FOR_STATS:
        return TrajectoryOut(cold_start=True, days_available=days_available)

    historical_returns = [
        (historical[i] - historical[i - 1]) / historical[i - 1] * 100
        for i in range(1, n)
        if historical[i - 1] != 0
    ]

    recent_days = min(7, n)
    recent_anchor = historical[n - recent_days]
    recent_return_pct = (h.ltp - recent_anchor) / recent_anchor * 100 if recent_anchor else None

    # Same mislabeling risk as recent_return_pct: historical[0] is only genuinely
    # "30 days ago" once n >= 30. Below that (true for every holding's first
    # ~25 days), it's whatever the earliest available snapshot is — so this
    # gets its own day-count field too, same fix as recent_days, rather than
    # silently implying a 30-day span that isn't there yet.
    thirty_day_days = n
    oldest = historical[0]
    thirty_day_return_pct = (h.ltp - oldest) / oldest * 100 if oldest else None

    flag_kind: str | None = None
    flag_text: str | None = None

    if historical_returns and today_move_pct is not None:
        stdev = pstdev(historical_returns)
        if stdev > 0:
            z = today_move_pct / stdev
            if abs(z) >= Z_UNUSUAL_THRESHOLD:
                flag_kind = "unusual"
                flag_text = f"Unusual — {abs(z):.1f}× typical daily swing"

    if flag_kind is None:
        all_returns = historical_returns + ([today_move_pct] if today_move_pct is not None else [])
        streak = 0
        direction = None
        for r in reversed(all_returns):
            d = 1 if r >= 0 else -1
            if direction is None:
                direction = d
                streak = 1
            elif d == direction:
                streak += 1
            else:
                break
        if streak >= STREAK_THRESHOLD:
            flag_kind = "streak"
            flag_text = f"{streak} straight {'up' if direction > 0 else 'down'} days"
        else:
            full_series = historical + [h.ltp]
            window_max = max(full_series)
            window_min = min(full_series)
            if window_max and (window_max - h.ltp) / window_max <= NEAR_EXTREME_FRACTION:
                flag_kind = "near_high"
                flag_text = "Near 30-day high"
            elif window_min and (h.ltp - window_min) / window_min <= NEAR_EXTREME_FRACTION:
                flag_kind = "near_low"
                flag_text = "Near 30-day low"

    return TrajectoryOut(
        cold_start=False,
        static=False,
        days_available=days_available,
        recent_days=recent_days,
        recent_return_pct=recent_return_pct,
        thirty_day_days=thirty_day_days,
        thirty_day_return_pct=thirty_day_return_pct,
        flag_kind=flag_kind,
        flag_text=flag_text,
    )
