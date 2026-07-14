"""Тесты логики определения типа документа по имени файла.

Пункт 7 ТЗ: покрыть тестами логику определения типа документа.
"""
from __future__ import annotations

import pytest

from app.services.document_detector import (
    DocumentType,
    REQUIRED_BY_PROGRAM,
    detect_document_type,
    detect_documents,
)


# ---------- Базовые случаи для каждого типа ----------


class TestDetectDocumentType:
    """Тесты функции detect_document_type."""

    @pytest.mark.parametrize(
        "filename, expected",
        [
            # contract
            ("договор_47.pdf", DocumentType.CONTRACT),
            ("Договор поставки 2025.pdf", DocumentType.CONTRACT),
            ("CONTRACT_001.pdf", DocumentType.CONTRACT),
            ("дог_2024.pdf", DocumentType.CONTRACT),
            # specification
            ("спецификация_v2.docx", DocumentType.SPECIFICATION),
            ("Specification_v2.docx", DocumentType.SPECIFICATION),
            ("Спецификация_к_договору.pdf", DocumentType.SPECIFICATION),
            # invoice
            ("счет-фактура.pdf", DocumentType.INVOICE),
            ("счёт_123.pdf", DocumentType.INVOICE),
            ("invoice_2025_03.pdf", DocumentType.INVOICE),
            # act / УПД
            ("акт_выполненных_работ.pdf", DocumentType.ACT),
            ("УПД_456.pdf", DocumentType.ACT),
            ("act_signed.pdf", DocumentType.ACT),
            # unknown
            ("scan_0041.jpg", DocumentType.UNKNOWN),
            ("document.pdf", DocumentType.UNKNOWN),
            ("12345.png", DocumentType.UNKNOWN),
            ("", DocumentType.UNKNOWN),
        ],
    )
    def test_detect_type(self, filename: str, expected: str) -> None:
        assert detect_document_type(filename) == expected

    def test_dogovor_latin_not_recognized_as_contract(self) -> None:
        """Проверка, что 'dogovor' (транслит без 'договор') НЕ распознаётся как contract."""
        # 'dogovor' — латиница, паттерны 'договор'/'contract'/'дог' не совпадают.
        assert detect_document_type("dogovor_smeta.pdf") == DocumentType.UNKNOWN

    def test_case_insensitive(self) -> None:
        """Имя файла нечувствительно к регистру."""
        assert detect_document_type("ДОГОВОР.PDF") == DocumentType.CONTRACT
        assert detect_document_type("Contract.PDF") == DocumentType.CONTRACT

    def test_extension_does_not_affect_detection(self) -> None:
        """Расширение не должно маскировать или подменять тип."""
        assert detect_document_type("договор.pdf") == DocumentType.CONTRACT
        assert detect_document_type("договор.docx") == DocumentType.CONTRACT
        assert detect_document_type("договор.jpg") == DocumentType.CONTRACT

    def test_yo_vs_e_normalization(self) -> None:
        """'счёт' и 'счет' должны распознаваться одинаково."""
        assert detect_document_type("счёт.pdf") == DocumentType.INVOICE
        assert detect_document_type("счет.pdf") == DocumentType.INVOICE

    def test_detect_documents_batch_preserves_order(self) -> None:
        """Пакетная обработка возвращает результат в порядке входного списка."""
        filenames = ["договор.pdf", "scan.png", "акт.pdf"]
        results = detect_documents(filenames)
        assert len(results) == 3
        assert [r.name for r in results] == filenames
        assert results[0].detected_type == DocumentType.CONTRACT
        assert results[1].detected_type == DocumentType.UNKNOWN
        assert results[2].detected_type == DocumentType.ACT


# ---------- Проверка требований к программам ----------


class TestRequiredByProgram:
    """Проверка конфигурации обязательных документов."""

    def test_federal_requires_four_types(self) -> None:
        assert set(REQUIRED_BY_PROGRAM["federal"]) == {
            DocumentType.CONTRACT,
            DocumentType.SPECIFICATION,
            DocumentType.INVOICE,
            DocumentType.ACT,
        }

    def test_regional_requires_three_types(self) -> None:
        assert set(REQUIRED_BY_PROGRAM["regional"]) == {
            DocumentType.CONTRACT,
            DocumentType.INVOICE,
            DocumentType.ACT,
        }

    def test_regional_does_not_require_specification(self) -> None:
        """Реггиональная программа НЕ требует спецификацию (отличие от federal)."""
        assert DocumentType.SPECIFICATION not in REQUIRED_BY_PROGRAM["regional"]
