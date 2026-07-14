"""Определение типа документа по имени файла.

Поддерживаемые типы (поле detected_type в ответе):
- contract       — договор
- specification  — спецификация
- invoice        — счёт
- act            — акт / УПД
- unknown        — тип не распознан (генерирует warning)

Логика (см. пункт 4 ТЗ): анализ по подстроке имени файла (без учёта
регистра) и по количеству обязательных документов каждого типа.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class DocumentType:
    """Строковые константы типов документов."""

    CONTRACT = "contract"
    SPECIFICATION = "specification"
    INVOICE = "invoice"
    ACT = "act"
    UNKNOWN = "unknown"


# Паттерны подстрок (приводим имя к нижнему регистру + ё→е).
# Порядок важен: 'акт' проверяем раньше 'счет/счёт', чтобы не было конфликтов
# (хотя конфликта по подстроке нет, но лучше держать логичный порядок).
TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    (DocumentType.SPECIFICATION, ["специфик", "specification"]),
    (DocumentType.CONTRACT, ["договор", "contract", "дог"]),
    (DocumentType.INVOICE, ["счет", "счёт", "счёт-фактур", "счет-фактур", "invoice"]),
    (DocumentType.ACT, ["акт", "упд", "act", "upd"]),
]


@dataclass
class DetectionResult:
    """Результат определения типа для одного файла."""

    name: str
    detected_type: str


def _normalize(filename: str) -> str:
    """Нормализация имени файла: нижний регистр + замена ё→е.

    Ё→е нужна потому, что в реальных файлах встречается и 'счёт', и 'счет'.
    """
    return filename.lower().replace("ё", "е")


def detect_document_type(filename: str) -> str:
    """Определить тип документа по имени файла.

    Args:
        filename: исходное имя файла (например, 'договор_47.pdf').

    Returns:
        Одна из констант DocumentType.* (включая UNKNOWN).
    """
    if not filename:
        return DocumentType.UNKNOWN

    name = _normalize(filename)
    # Отрезаем расширение, чтобы 'scan.pdf' не воспринимался как 'p'/'f' и т.п.
    stem = re.sub(r"\.[^.]+$", "", name)

    for doc_type, patterns in TYPE_PATTERNS:
        for pattern in patterns:
            if pattern in stem:
                return doc_type

    return DocumentType.UNKNOWN


def detect_documents(filenames: list[str]) -> list[DetectionResult]:
    """Определить тип для каждого файла пакета.

    Args:
        filenames: список имён файлов.

    Returns:
        Список DetectionResult в том же порядке.
    """
    return [DetectionResult(name=n, detected_type=detect_document_type(n)) for n in filenames]


# ---------- Обязательные документы по программе ----------

# Пункт 4 ТЗ:
#   federal  → договор, спецификация, счёт, акт
#   regional → договор, счёт, акт
REQUIRED_BY_PROGRAM: dict[str, list[str]] = {
    "federal": [
        DocumentType.CONTRACT,
        DocumentType.SPECIFICATION,
        DocumentType.INVOICE,
        DocumentType.ACT,
    ],
    "regional": [
        DocumentType.CONTRACT,
        DocumentType.INVOICE,
        DocumentType.ACT,
    ],
}

# Человекочитаемые названия для сообщений об ошибках.
TYPE_LABELS_RU: dict[str, str] = {
    DocumentType.CONTRACT: "договор",
    DocumentType.SPECIFICATION: "спецификация",
    DocumentType.INVOICE: "счёт",
    DocumentType.ACT: "акт/УПД",
    DocumentType.UNKNOWN: "неизвестный тип",
}
