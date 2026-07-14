"""ORM-модели базы данных.

Структура:
- Check      — одна проверка пакета документов (одна загрузка).
- Document   — один файл внутри пакета (имя, тип, размер, путь на диске).
- Issue      — одна проблема, найденная при проверке (error / warning).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _new_uuid() -> str:
    """Строковый UUID для использования в качестве первичного ключа."""
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ProgramType(str, enum.Enum):
    """Тип программы льготного кредитования."""

    federal = "federal"
    regional = "regional"


class CheckStatus(str, enum.Enum):
    """Итоговый статус проверки пакета документов."""

    approved = "approved"
    rejected = "rejected"
    check_in_progress = "check_in_progress"


class IssueLevel(str, enum.Enum):
    """Уровень проблемы: error блокирует aprov, warning — только информирует."""

    error = "error"
    warning = "warning"


class Check(Base):
    """Запись о проверке пакета документов."""

    __tablename__ = "checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    program: Mapped[ProgramType] = mapped_column(Enum(ProgramType), nullable=False)
    status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus), nullable=False)
    status_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extracted: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    documents: Mapped[list[Document]] = relationship(
        back_populates="check", cascade="all, delete-orphan", lazy="selectin"
    )
    issues: Mapped[list[Issue]] = relationship(
        back_populates="check", cascade="all, delete-orphan", lazy="selectin"
    )


class Document(Base):
    """Один файл внутри пакета документов."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    check_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("checks.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    detected_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    check: Mapped[Check] = relationship(back_populates="documents")


class Issue(Base):
    """Одна проблема, обнаруженная при проверке."""

    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    check_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("checks.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[IssueLevel] = mapped_column(Enum(IssueLevel), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    check: Mapped[Check] = relationship(back_populates="issues")
