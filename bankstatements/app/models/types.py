"""Money TypeDecorator for storing monetary values as integer paise."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy import TypeDecorator


class Money(TypeDecorator):
    """SQLAlchemy TypeDecorator that stores Decimal money values as integer paise.

    On bind (Python → DB): Converts Decimal to int paise (value * 100).
    On result (DB → Python): Converts int paise back to Decimal with 2 decimal places.
    """

    impl = sa.BigInteger
    cache_ok = True

    def process_bind_param(self, value: Decimal | int | float | None, dialect: sa.Dialect) -> int | None:
        """Convert Decimal to integer paise for storage.

        Args:
            value: The Decimal monetary value.
            dialect: The SQLAlchemy dialect.

        Returns:
            Integer paise value, or None if value is None.
        """
        if value is None:
            return None
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        # Multiply by 100 and round to get paise
        paise = value * Decimal("100")
        return int(paise.to_integral_value(rounding=ROUND_HALF_UP))

    def process_result_value(self, value: int | None, dialect: sa.Dialect) -> Decimal | None:
        """Convert integer paise back to Decimal with 2 decimal places.

        Args:
            value: The integer paise value from the database.
            dialect: The SQLAlchemy dialect.

        Returns:
            Decimal monetary value with 2 decimal places, or None if value is None.
        """
        if value is None:
            return None
        return (Decimal(value) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

