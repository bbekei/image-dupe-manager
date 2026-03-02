"""
ui/workflow.py — Workflow phase enum for DejaView.

Tracks which phase of the user workflow is active.
"""

from enum import Enum, auto


class WorkflowPhase(Enum):
    DASHBOARD = auto()         # Home view with status cards
    DISCOVERY = auto()         # Scan running or complete, browsing results
    PLANNING = auto()          # User marking items with actions
    PLAN_REVIEW = auto()       # Review all planned actions before commit
    EXECUTION = auto()         # Automation carrying out actions
    FAMILY_DISCOVERY = auto()  # Browse family treasures, request photos
    REVIEW = auto()            # Post-execution review
