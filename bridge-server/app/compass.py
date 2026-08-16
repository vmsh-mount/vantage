"""Compass (docs/compass-prd.md §10, §11): the whole-feature summary,
composing across the three target shapes (Goal, AllocationTarget,
Milestone) — used by the MCP bundling tool (get_compass_summary, mirrors
get_behavioral_patterns' one-call-bundles-several-computations pattern),
the REST summary endpoint, and the digest's one summary line."""

from sqlalchemy.orm import Session

from app.allocation_targets import SUPPORTED_DIMENSIONS, compute_allocation_progress
from app.goals import compute_goal_progress, list_goals
from app.milestones import compute_milestone_progress, list_milestones


def compute_compass_summary(db: Session) -> dict:
    goals_progress = [compute_goal_progress(db, g) for g in list_goals(db)]
    goals_met = sum(1 for g in goals_progress if g["status"] == "met")

    allocation_items = [
        item for dimension in SUPPORTED_DIMENSIONS for item in compute_allocation_progress(db, dimension)
    ]
    allocation_on_target = sum(1 for a in allocation_items if a["status"] == "on_target")

    milestones_progress = [compute_milestone_progress(db, m) for m in list_milestones(db)]
    milestones_on_pace = sum(1 for m in milestones_progress if m["status"] in ("met", "on_pace"))

    return {
        "goals": {"total": len(goals_progress), "met": goals_met},
        "allocation_targets": {"total": len(allocation_items), "on_target": allocation_on_target},
        "milestones": {"total": len(milestones_progress), "on_pace": milestones_on_pace},
    }
