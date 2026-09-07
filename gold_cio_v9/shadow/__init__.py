"""Prospective shadow-only signal collection for Gold CIO."""

from .engine import ShadowCandidate, ShadowDecision, ShadowFeed, decide_shadow
from .ledger import HashChainLedger

__all__ = ["HashChainLedger", "ShadowCandidate", "ShadowDecision", "ShadowFeed", "decide_shadow"]
