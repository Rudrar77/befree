"""Statement management service."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple
import sqlalchemy as sa
from app.errors import NotFoundError
from app.extensions import db
from app.models.statement import ProcessingStatus, Statement
from app.models.unresolved_row import UnresolvedRow


def check_and_mark_stale_jobs(stale_minutes: int = 15) -> int:
    """Mark jobs as failed if they have been processing without update for stale_minutes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    stale_stmts = (
        db.session.query(Statement)
        .filter(
            Statement.processing_status.in_([ProcessingStatus.PROCESSING.value, ProcessingStatus.QUEUED.value]),
            Statement.updated_at < cutoff,
        )
        .all()
    )
    for s in stale_stmts:
        s.processing_status = ProcessingStatus.FAILED.value
        s.error_message = f"Job timed out: no heartbeat received for >{stale_minutes} minutes."
        s.updated_at = datetime.now(timezone.utc)

    if stale_stmts:
        db.session.commit()
    return len(stale_stmts)


def list_statements(
    page: int = 1,
    page_size: int = 50,
    processing_status: Optional[str] = None,
) -> Tuple[List[Statement], int]:
    """Retrieve paginated list of statements."""
    check_and_mark_stale_jobs()

    query = db.session.query(Statement)
    if processing_status:
        query = query.filter(Statement.processing_status == processing_status)

    total = query.count()
    items = (
        query.order_by(Statement.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_statement_by_id(statement_id: str) -> Statement:
    """Retrieve statement by UUID or raise NotFoundError."""
    stmt = db.session.get(Statement, statement_id)
    if not stmt:
        raise NotFoundError(message=f"Statement with ID '{statement_id}' not found.")
    return stmt


def get_unresolved_rows(statement_id: str) -> List[UnresolvedRow]:
    """Retrieve all unresolved rows for a statement."""
    # Ensure statement exists
    get_statement_by_id(statement_id)
    return (
        db.session.query(UnresolvedRow)
        .filter_by(statement_id=statement_id)
        .filter(UnresolvedRow.raw_text != "")
        .order_by(UnresolvedRow.source_page.asc())
        .all()
    )


def delete_statement(statement_id: str) -> None:
    """Delete statement from database and remove stored PDF from disk."""
    stmt = get_statement_by_id(statement_id)
    file_path = stmt.file_path

    # Delete from DB (cascades to transactions, validation_results, etc.)
    db.session.delete(stmt)
    db.session.commit()

    # Remove stored PDF from disk safely
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
