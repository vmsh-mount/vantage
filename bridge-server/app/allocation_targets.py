"""Compass (docs/compass-prd.md §6.2, §9): composition targets — a target %
per bucket within a dimension, checked against a real, already-computed
breakdown (app/breakdowns.py — the same grouping the dashboard's own
breakdown charts use, not re-derived here).

Supported dimensions: "sector", "asset_class", "region". See
app/models/allocation_target.py's own docstring for why "market_cap" isn't
wired up yet (it needs a live per-holding INDmoney lookup, not a free local
aggregation like these three)."""

from sqlalchemy.orm import Session

from app.breakdowns import compute_breakdown_sums, compute_net_worth_inr
from app.models import AllocationTarget, Holding

SUPPORTED_DIMENSIONS = ("sector", "asset_class", "region")

_BREAKDOWN_KEY_BY_DIMENSION = {
    "sector": "by_sector",
    "asset_class": "by_asset_class",
    "region": "by_region",
}


def upsert_allocation_target(
    db: Session,
    dimension: str,
    bucket: str,
    target_pct: float,
    tolerance_pct: float = 5.0,
    rationale: str | None = None,
) -> AllocationTarget:
    if dimension not in SUPPORTED_DIMENSIONS:
        raise ValueError(f"Unsupported dimension {dimension!r}; must be one of {SUPPORTED_DIMENSIONS}")
    existing = db.query(AllocationTarget).filter_by(dimension=dimension, bucket=bucket).one_or_none()
    if existing is None:
        existing = AllocationTarget(dimension=dimension, bucket=bucket)
        db.add(existing)
    existing.target_pct = target_pct
    existing.tolerance_pct = tolerance_pct
    existing.rationale = rationale
    existing.active = True
    db.commit()
    db.refresh(existing)
    return existing


def list_allocation_targets(db: Session, dimension: str | None = None) -> list[AllocationTarget]:
    query = db.query(AllocationTarget).filter_by(active=True)
    if dimension is not None:
        query = query.filter_by(dimension=dimension)
    return query.order_by(AllocationTarget.dimension, AllocationTarget.bucket).all()


def deactivate_allocation_target(db: Session, target_id: int) -> AllocationTarget | None:
    target = db.get(AllocationTarget, target_id)
    if target is None:
        return None
    target.active = False
    db.commit()
    db.refresh(target)
    return target


def compute_dimension_breakdown(db: Session, dimension: str) -> list[dict]:
    """Real current allocation for every bucket actually held in this
    dimension, independent of whether a target has been configured for it
    yet — powers the "current: X%" hint the add-target form shows once you
    type/pick a bucket, so a target gets set relative to where you
    actually are rather than typed blind. Deliberately not exposed as its
    own MCP tool: get_dashboard's own breakdowns field already carries the
    same numbers for every dimension in one call, so a second tool here
    would just be a redundant, UI-only convenience wrapper."""
    if dimension not in SUPPORTED_DIMENSIONS:
        raise ValueError(f"Unsupported dimension {dimension!r}; must be one of {SUPPORTED_DIMENSIONS}")
    holdings = db.query(Holding).all()
    bucket_sums = compute_breakdown_sums(holdings)[_BREAKDOWN_KEY_BY_DIMENSION[dimension]]
    total_inr = compute_net_worth_inr(holdings)
    return [
        {
            "bucket": bucket,
            "actual_pct": round(value_inr / total_inr * 100, 2) if total_inr else 0.0,
            "actual_value_inr": round(value_inr, 2),
        }
        for bucket, value_inr in sorted(bucket_sums.items(), key=lambda kv: -kv[1])
    ]


def split_bucket_names(bucket: str) -> list[str]:
    """A bucket can name more than one real sector/asset-class/region,
    comma-separated (e.g. "Steel, Non Ferrous Metals, Entertainment" for
    four small holdings that don't individually deserve a target) — the
    match/sum logic below always operates on this list, so a plain
    single-name bucket is just the n=1 case, not a special case."""
    return [name.strip() for name in bucket.split(",") if name.strip()]


def compute_allocation_progress(db: Session, dimension: str) -> list[dict]:
    """Real decision (docs/compass-prd.md §9): every bucket that has a
    target is reported, including one at real 0% actual — that's the
    whole point (a named gap, not a missing checkmark). A bucket with real
    actual allocation but no configured target is not reported here; it's
    not a gap against anything the user declared.

    Real bug found live (user's own manual reconciliation against the
    Dashboard caught this): the match against bucket_sums is an exact
    string comparison, and a typo/label mismatch (e.g. "QSR" typed when
    the broker's real sector string is "Quick Service Restaurant")
    produces exactly 0 — indistinguishable from a genuine "you hold
    nothing in this real sector yet" gap. Both are real 0s to the naive
    lookup; only one of them is honest. unmatched_bucket_names names
    exactly which comma-part(s) of the bucket don't correspond to any
    sector/asset-class/region actually present in current holdings, so
    the frontend can show an explicit "this doesn't match anything you
    currently hold" warning distinct from the verified-real-zero case —
    on every read, not just at creation time, so a target that drifts out
    of sync later (the broker renames a sector) doesn't go unnoticed
    either. Honest limit, stated plainly rather than glossed over: this
    can only verify against sectors of holdings you currently own — there
    is no external sector-taxonomy oracle here (the same reason
    "market_cap" isn't wired up as a dimension at all — see this file's
    own module docstring), so a genuinely new, never-yet-held category
    (e.g. "Healthcare" with zero holdings ever) is reported unmatched too
    — correctly, since nothing here can confirm that string is real
    either. The honest answer in both cases is "doesn't match anything I
    can currently see," never a fabricated confirmation."""
    if dimension not in SUPPORTED_DIMENSIONS:
        raise ValueError(f"Unsupported dimension {dimension!r}; must be one of {SUPPORTED_DIMENSIONS}")

    targets = list_allocation_targets(db, dimension=dimension)
    if not targets:
        return []

    holdings = db.query(Holding).all()
    sums = compute_breakdown_sums(holdings)
    bucket_sums = sums[_BREAKDOWN_KEY_BY_DIMENSION[dimension]]
    total_inr = compute_net_worth_inr(holdings)

    results = []
    for target in targets:
        bucket_names = split_bucket_names(target.bucket)
        unmatched = [name for name in bucket_names if name not in bucket_sums]
        actual_value_inr = sum(bucket_sums.get(name, 0.0) for name in bucket_names)
        actual_pct = (actual_value_inr / total_inr * 100) if total_inr else 0.0
        lower = target.target_pct - target.tolerance_pct
        upper = target.target_pct + target.tolerance_pct
        if actual_pct < lower:
            status = "underweight"
        elif actual_pct > upper:
            status = "overweight"
        else:
            status = "on_target"
        results.append(
            {
                "id": target.id,
                "dimension": dimension,
                "bucket": target.bucket,
                "target_pct": target.target_pct,
                "tolerance_pct": target.tolerance_pct,
                "rationale": target.rationale,
                "actual_pct": round(actual_pct, 2),
                "actual_value_inr": round(actual_value_inr, 2),
                "status": status,
                "gap_pct": round(target.target_pct - actual_pct, 2),
                "unmatched_bucket_names": unmatched,
            }
        )
    return results
