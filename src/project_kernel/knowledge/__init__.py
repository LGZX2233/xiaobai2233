"""Project context and dynamic memory (P08).

Implements versioned sources, token budgets and real feedback for the optional
knowledge capability. Pure domain logic lives in `resolver` and `scoring`;
persistence goes through the P01 Store/UoW generic revision ledger (never DDL,
never a second SQL writer). ContextResolver produces a frozen ContextManifest;
KnowledgeService records use/injection/adoption and outcome feedback idempotently
and scores them with duplicate suppression and traceable rollback/correction.
"""
from .models import (
    ContextExclusion,
    ContextManifest,
    ContextRequest,
    ContextSelection,
    KnowledgeRevision,
    OutcomeEvent,
    PromotionTask,
    ScoreDelta,
    ScoreRecord,
    SourceMaterial,
    UseEvent,
)
from .token_meter import DeterministicTokenMeter, TokenMeterPort
from .resolver import ContextResolver, RequiredFactError
from .scoring import ScoreEngine, ScoringConfig
from .service import FeedbackConsumer, KnowledgeService

__all__ = [
    "ContextExclusion",
    "ContextManifest",
    "ContextRequest",
    "ContextSelection",
    "ContextResolver",
    "DeterministicTokenMeter",
    "FeedbackConsumer",
    "KnowledgeRevision",
    "KnowledgeService",
    "OutcomeEvent",
    "PromotionTask",
    "RequiredFactError",
    "ScoreDelta",
    "ScoreEngine",
    "ScoreRecord",
    "ScoringConfig",
    "SourceMaterial",
    "TokenMeterPort",
    "UseEvent",
]
