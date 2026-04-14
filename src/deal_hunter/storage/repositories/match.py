"""Match review + decision repositories — offer→product matching queue and audit log."""

from datetime import datetime

from sqlalchemy.orm import Session

from deal_hunter.storage.models import MatchDecision, MatchReview


class MatchReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        offer_id: str,
        candidate_product_id: str | None = None,
        suggested_products: list | None = None,
        best_confidence: float | None = None,
        reason: str | None = None,
        priority: int = 0,
    ) -> MatchReview:
        review = MatchReview(
            offer_id=offer_id,
            candidate_product_id=candidate_product_id,
            suggested_products=suggested_products,
            best_confidence=best_confidence,
            reason=reason,
            priority=priority,
            status="pending",
            created_at=datetime.now().isoformat(),
        )
        self.session.add(review)
        return review


class MatchDecisionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        decision_type: str,
        actor: str,
        offer_id: str | None = None,
        product_id: str | None = None,
        confidence: float | None = None,
        signals: dict | None = None,
        undo_snapshot: dict | None = None,
    ) -> MatchDecision:
        decision = MatchDecision(
            offer_id=offer_id,
            product_id=product_id,
            decision_type=decision_type,
            confidence=confidence,
            signals=signals,
            actor=actor,
            created_at=datetime.now().isoformat(),
            undo_snapshot=undo_snapshot,
        )
        self.session.add(decision)
        return decision
