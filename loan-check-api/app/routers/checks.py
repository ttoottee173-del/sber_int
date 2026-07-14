"""Эндпоинты API проверки пакетов документов.

Эндпоинты (пункты 1-3 ТЗ):
    POST /api/checks          — загрузить пакет и запустить проверку
    GET  /api/checks          — список всех проверок (краткая форма)
    GET  /api/checks/{check_id} — полный результат конкретной проверки
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Check, ProgramType
from app.schemas import (
    CheckCreateResponse,
    CheckDetailResponse,
    CheckListItem,
    DocumentOut,
    ExtractedData,
    IssueOut,
)
from app.services.check_service import (
    CheckResult,
    run_check,
    save_check_to_db,
    to_response,
)
from app.services.file_storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["checks"])


# ---------- Зависимости ----------


def _validate_program(program: str) -> ProgramType:
    """Преобразовать строку программы в ProgramType.

    Возвращает 422 Unprocessable Entity, если значение не входит в {federal, regional}.
    """
    try:
        return ProgramType(program)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Поле 'program' должно быть одним из: "
                f"{[p.value for p in ProgramType]}. Получено: '{program}'."
            ),
        ) from None


# ---------- POST /api/checks ----------


@router.post(
    "/checks",
    response_model=CheckCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить пакет документов и запустить проверку",
)
def create_check(
    program: Annotated[str, Form(description="Программа: federal | regional")],
    files: Annotated[
        list[UploadFile],
        File(description="Файлы пакета (PDF, DOCX, JPG, PNG)"),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> CheckCreateResponse:
    """Принять multipart/form-data с файлами и названием программы,
    запустить проверку, сохранить результат в БД и вернуть его.
    """
    program_enum = _validate_program(program)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не передано ни одного файла. Поле 'files' обязательно.",
        )

    check_id = str(uuid.uuid4())

    # Готовим список (filename, size, content_stream) для сервиса проверки.
    prepared_files: list[tuple[str, int, object]] = []
    for upload in files:
        # UploadFile.file — это SpooledTemporaryFile, читается как бинарный поток.
        prepared_files.append((upload.filename or "unnamed", upload.size or 0, upload.file))

    try:
        result: CheckResult = run_check(
            files=prepared_files,
            program=program_enum,
            check_id=check_id,
            storage=storage,
        )
        check = save_check_to_db(db, check_id, program_enum, result)
    except SQLAlchemyError as exc:
        logger.exception("DB error while saving check %s", check_id)
        # Чистим файлы, чтобы не оставлять мусор.
        storage.cleanup_check(check_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка сохранения результата проверки в БД.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during check %s", check_id)
        storage.cleanup_check(check_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера при проверке пакета.",
        ) from exc

    return to_response(check)


# ---------- GET /api/checks — список ----------


@router.get(
    "/checks",
    response_model=list[CheckListItem],
    summary="Список всех проверок",
)
def list_checks(
    db: Annotated[Session, Depends(get_db)],
) -> list[CheckListItem]:
    """Вернуть краткий список всех проверок:
    id, дата, программа, статус, количество документов.
    """
    checks = db.query(Check).order_by(Check.checked_at.desc()).all()
    return [
        CheckListItem(
            id=c.id,
            checked_at=c.checked_at,
            program=c.program,
            status=c.status,
            documents_count=len(c.documents),
        )
        for c in checks
    ]


# ---------- GET /api/checks/{check_id} — детали ----------


@router.get(
    "/checks/{check_id}",
    response_model=CheckDetailResponse,
    summary="Полный результат конкретной проверки",
    responses={
        404: {"description": "Проверка с указанным id не найдена"},
    },
)
def get_check(
    check_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CheckDetailResponse:
    """Вернуть полный результат проверки по id."""
    check = db.get(Check, check_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Проверка с id '{check_id}' не найдена.",
        )

    return CheckDetailResponse(
        check_id=check.id,
        status=check.status,
        status_label=check.status_label,
        reason=check.reason,
        issues=[IssueOut(level=i.level, message=i.message) for i in check.issues],
        documents=[
            DocumentOut(name=d.name, detected_type=d.detected_type, size_kb=d.size_kb)
            for d in check.documents
        ],
        extracted=ExtractedData(**(check.extracted or {})),
        checked_at=check.checked_at,
    )
