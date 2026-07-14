"""Логика проверки пакета документов.

Шаги:
1. Сохранить файлы на диск и собрать список DetectedFile.
2. Для каждого файла:
   - проверить формат (расширение),
   - проверить размер,
   - определить тип документа.
3. Проверить комплектность пакета по программе (federal/regional).
4. Сформировать итоговый статус и человекочитаемый reason.
5. Сохранить результат в БД.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Check, CheckStatus, Document, Issue, IssueLevel, ProgramType
from app.schemas import (
    CheckCreateResponse,
    DocumentOut,
    ExtractedData,
    IssueOut,
)
from app.services.document_detector import (
    TYPE_LABELS_RU,
    DocumentType,
    REQUIRED_BY_PROGRAM,
    detect_document_type,
)
from app.services.file_storage import FileStorage

logger = logging.getLogger(__name__)


@dataclass
class DetectedFile:
    """Информация об одном файле после анализа."""

    name: str
    detected_type: str
    size_kb: int
    storage_path: str
    extension: str
    is_format_valid: bool
    is_size_valid: bool


@dataclass
class CheckResult:
    """Полный результат проверки пакета."""

    status: CheckStatus
    status_label: str
    reason: str
    issues: list[tuple[IssueLevel, str]] = field(default_factory=list)
    documents: list[DetectedFile] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------- Лейблы статусов ----------

STATUS_LABELS: dict[CheckStatus, str] = {
    CheckStatus.approved: "Можно заявлять в банк",
    CheckStatus.rejected: "Нельзя заявлять в банк",
    CheckStatus.check_in_progress: "Проверка выполняется",
}


def _get_extension(filename: str) -> str:
    """Расширение без точки в нижнем регистре."""
    _, ext = os.path.splitext(filename)
    return ext.lstrip(".").lower()


def _kb(size_bytes: int) -> int:
    """Округлённый размер в КБ (минимум 1)."""
    return max(1, (size_bytes + 1023) // 1024)


# ---------- Проверка отдельного файла ----------


def _check_file(
    filename: str,
    size_bytes: int,
    content: BinaryIO,
    check_id: str,
    storage: FileStorage,
) -> DetectedFile:
    """Сохранить файл на диск и собрать DetectedFile.

    Замечания (формат, размер, неизвестный тип) добавляются на уровне
    check_service — здесь только сохраняем файл и определяем тип.
    """
    extension = _get_extension(filename)
    is_format_valid = extension in settings.allowed_ext_list
    is_size_valid = size_bytes <= settings.max_file_size_mb * 1024 * 1024

    # Сохраняем файл всегда — даже если он невалиден. Так у пользователя
    # останется доказательство, что загрузка прошла, а в issues будет понятно,
    # почему пакет rejected. При желании можно удалять — но тогда не получится
    # потом проанализировать, что именно было загружено.
    storage_path = storage.save_file(check_id, filename, content)

    detected_type = detect_document_type(filename)

    return DetectedFile(
        name=filename,
        detected_type=detected_type,
        size_kb=_kb(size_bytes),
        storage_path=str(storage_path),
        extension=extension,
        is_format_valid=is_format_valid,
        is_size_valid=is_size_valid,
    )


# ---------- Комплектность пакета ----------


def _check_completeness(
    documents: list[DetectedFile], program: ProgramType
) -> list[tuple[IssueLevel, str]]:
    """Проверить, что все обязательные типы документов присутствуют.

    Один тип считается присутствующим, если есть хотя бы один файл с этим
    detected_type. Количество обязательных файлов каждого типа = 1
    (в ТЗ не сказано иного).
    """
    issues: list[tuple[IssueLevel, str]] = []
    required = REQUIRED_BY_PROGRAM[program.value]

    present_types = {
        d.detected_type for d in documents if d.detected_type != DocumentType.UNKNOWN
    }

    for req_type in required:
        if req_type not in present_types:
            label = TYPE_LABELS_RU.get(req_type, req_type)
            issues.append(
                (
                    IssueLevel.error,
                    f"Отсутствует обязательный документ: {label}",
                )
            )

    return issues


# ---------- Формирование итогового статуса ----------


def build_status(
    issues: list[tuple[IssueLevel, str]],
) -> tuple[CheckStatus, str, str]:
    """Сформировать итоговый статус, label и reason.

    - Если есть хотя бы одна ошибка уровня error → rejected.
    - Иначе (только warnings или пусто) → approved.

    reason — человекочитаемое описание первой ошибки (или сообщение об успехе).
    """
    errors = [msg for level, msg in issues if level == IssueLevel.error]

    if errors:
        status = CheckStatus.rejected
        status_label = STATUS_LABELS[CheckStatus.rejected]
        # Берём первую ошибку как основную причину.
        reason = errors[0]
    else:
        status = CheckStatus.approved
        status_label = STATUS_LABELS[CheckStatus.approved]
        warnings = [msg for level, msg in issues if level == IssueLevel.warning]
        if warnings:
            reason = "Пакет принят с предупреждениями: " + "; ".join(warnings)
        else:
            reason = "Все обязательные документы присутствуют, нарушений не найдено."

    return status, status_label, reason


# ---------- Оркестрация проверки ----------


def run_check(
    files: list[tuple[str, int, BinaryIO]],
    program: ProgramType,
    check_id: str,
    storage: FileStorage,
) -> CheckResult:
    """Выполнить полную проверку пакета документов.

    Args:
        files: список кортежей (filename, size_bytes, content_stream).
        program: federal / regional.
        check_id: идентификатор проверки (используется как подпапка хранилища).
        storage: файловое хранилище.

    Returns:
        CheckResult — полный результат проверки.
    """
    issues: list[tuple[IssueLevel, str]] = []
    documents: list[DetectedFile] = []

    # Шаг 1: сохраняем файлы и собираем DetectedFile.
    for filename, size_bytes, content in files:
        detected = _check_file(filename, size_bytes, content, check_id, storage)
        documents.append(detected)

        # Проверка формата (пункт 5 ТЗ).
        if not detected.is_format_valid:
            issues.append(
                (
                    IssueLevel.error,
                    f"Недопустимый формат файла: «{filename}» "
                    f"(разрешены: {', '.join(settings.allowed_ext_list)})",
                )
            )

        # Проверка размера (пункт 5 ТЗ).
        if not detected.is_size_valid:
            issues.append(
                (
                    IssueLevel.error,
                    f"Размер файла «{filename}» превышает "
                    f"{settings.max_file_size_mb} МБ",
                )
            )

        # Нераспознанное имя файла (пункт 5 ТЗ).
        if detected.detected_type == DocumentType.UNKNOWN:
            issues.append(
                (
                    IssueLevel.warning,
                    f"Не удалось определить тип документа: «{filename}»",
                )
            )

    # Шаг 2: проверяем комплектность (пункт 4 ТЗ).
    issues.extend(_check_completeness(documents, program))

    # Шаг 3: формируем итоговый статус.
    status, status_label, reason = build_status(issues)

    return CheckResult(
        status=status,
        status_label=status_label,
        reason=reason,
        issues=issues,
        documents=documents,
        # extracted — заглушка (см. README → «Известные ограничения»).
        extracted={
            "contractor": None,
            "amount": None,
            "date": None,
            "subject": None,
        },
    )


# ---------- Сохранение результата в БД ----------


def save_check_to_db(
    db: Session,
    check_id: str,
    program: ProgramType,
    result: CheckResult,
) -> Check:
    """Сохранить результат проверки в PostgreSQL."""
    check = Check(
        id=check_id,
        program=program,
        status=result.status,
        status_label=result.status_label,
        reason=result.reason,
        extracted=result.extracted,
        checked_at=result.checked_at,
    )

    for doc in result.documents:
        check.documents.append(
            Document(
                name=doc.name,
                detected_type=doc.detected_type,
                size_kb=doc.size_kb,
                storage_path=doc.storage_path,
            )
        )

    for level, message in result.issues:
        check.issues.append(Issue(level=level, message=message))

    db.add(check)
    db.commit()
    db.refresh(check)
    return check


def to_response(check: Check) -> CheckCreateResponse:
    """Преобразовать ORM-объект Check в Pydantic-схему ответа."""
    return CheckCreateResponse(
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
