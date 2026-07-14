"""Pydantic-схемы для входных и выходных данных API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import CheckStatus, IssueLevel, ProgramType


# ---------- Выходные схемы ----------


class IssueOut(BaseModel):
    """Одна проблема, найденная при проверке."""

    level: IssueLevel
    message: str


class DocumentOut(BaseModel):
    """Один файл пакета с определённым типом."""

    name: str
    detected_type: str
    size_kb: int


class ExtractedData(BaseModel):
    """Извлечённые из документов данные.

    В рамках тестового задания извлечение НЕ реализовано (см. README — раздел
    «Известные ограничения»). Схема оставлена для совместимости с форматом ответа
    из ТЗ, всегда возвращается с пустыми полями.
    """

    contractor: str | None = None
    amount: str | None = None
    date: str | None = None
    subject: str | None = None


class CheckCreateResponse(BaseModel):
    """Полный ответ POST /api/checks — результат проверки пакета."""

    model_config = ConfigDict(from_attributes=True)

    check_id: str
    status: CheckStatus
    status_label: str
    reason: str
    issues: list[IssueOut] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    extracted: ExtractedData = Field(default_factory=ExtractedData)
    checked_at: datetime


class CheckListItem(BaseModel):
    """Краткая запись в списке GET /api/checks."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    checked_at: datetime
    program: ProgramType
    status: CheckStatus
    documents_count: int


class CheckDetailResponse(BaseModel):
    """Полная запись проверки для GET /api/checks/{id}.

    Совпадает по структуре с ответом POST /api/checks, но поле id названо
    так же, как в БД (для совместимости со списком).
    """

    model_config = ConfigDict(from_attributes=True)

    check_id: str
    status: CheckStatus
    status_label: str
    reason: str
    issues: list[IssueOut] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    extracted: ExtractedData = Field(default_factory=ExtractedData)
    checked_at: datetime


# ---------- Вспомогательные ----------


class ErrorResponse(BaseModel):
    """Унифицированный формат ошибки."""

    detail: str | dict
