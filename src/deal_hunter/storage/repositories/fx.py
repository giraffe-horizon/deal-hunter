"""FX rate repository — currency conversion rates for non-PLN offers."""

from sqlalchemy.orm import Session

from deal_hunter.storage.models import FxRate


class FxRateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, currency: str) -> FxRate | None:
        result: FxRate | None = self.session.get(FxRate, currency)
        return result

    def upsert(
        self,
        *,
        currency: str,
        rate_to_pln: float,
        fetched_at: str,
        table_no: str | None = None,
    ) -> FxRate:
        existing: FxRate | None = self.session.get(FxRate, currency)
        if existing:
            existing.rate_to_pln = rate_to_pln
            existing.fetched_at = fetched_at
            existing.table_no = table_no
            return existing
        row = FxRate(
            currency=currency,
            rate_to_pln=rate_to_pln,
            fetched_at=fetched_at,
            table_no=table_no,
        )
        self.session.add(row)
        return row
