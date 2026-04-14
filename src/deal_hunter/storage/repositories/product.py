"""Product + ProductAlias repositories — canonical product catalog and identifier lookups."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Product, ProductAlias


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        id: str,  # noqa: A002
        canonical_title: str,
        category: str,
        attributes: dict,
        brand: str | None = None,
        model: str | None = None,
        review_status: str = "auto",
        confidence_score: float | None = None,
    ) -> Product:
        now = datetime.now().isoformat()
        p = Product(
            id=id,
            canonical_title=canonical_title,
            category=category,
            attributes=attributes,
            brand=brand,
            model=model,
            review_status=review_status,
            confidence_score=confidence_score,
            created_at=now,
            updated_at=now,
        )
        self.session.add(p)
        return p

    def get(self, product_id: str) -> Product | None:
        result: Product | None = self.session.get(Product, product_id)
        return result


class ProductAliasRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        product_id: str,
        identifier_type: str,
        identifier_value: str,
        confidence: float,
        source: str | None = None,
        created_by: str = "auto",
    ) -> ProductAlias:
        now = datetime.now().isoformat()
        alias = ProductAlias(
            product_id=product_id,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            source=source,
            confidence=confidence,
            created_by=created_by,
            created_at=now,
        )
        self.session.add(alias)
        return alias

    def find(
        self,
        *,
        identifier_type: str,
        identifier_value: str,
        source: str | None = None,
    ) -> ProductAlias | None:
        q = select(ProductAlias).where(
            ProductAlias.identifier_type == identifier_type,
            ProductAlias.identifier_value == identifier_value,
        )
        if source is not None:
            q = q.where(ProductAlias.source == source)
        else:
            q = q.where(ProductAlias.source.is_(None))
        result: ProductAlias | None = self.session.execute(q).scalars().first()
        return result
