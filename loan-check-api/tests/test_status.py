"""Тесты формирования итогового статуса (пункт 7 ТЗ).

Логика:
- есть хотя бы одна ошибка уровня error  → rejected
- только warnings / нет issues           → approved
"""
from __future__ import annotations

from app.models import IssueLevel, ProgramType
from app.services.check_service import (
    CheckResult,
    build_status,
    run_check,
)
from app.services.document_detector import DocumentType


# ---------- Вспомогательные классы для тестов ----------


class _FakeStream:
    """Простейший бинарный поток-заглушка для FileStorage."""

    def __init__(self, content: bytes = b"fake") -> None:
        self._content = content
        self._read = False

    def read(self, size: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._content


# ---------- Тесты build_status ----------


class TestBuildStatus:
    """Тесты функции build_status (чистая логика формирования статуса)."""

    def test_approved_when_no_issues(self) -> None:
        status, label, reason = build_status([])
        assert status.value == "approved"
        assert "можно" in label.lower() or "accepted" in label.lower()
        assert "нарушений не найдено" in reason.lower() or "no" in reason.lower()

    def test_approved_with_only_warnings(self) -> None:
        issues = [
            (IssueLevel.warning, "Не удалось определить тип документа: «scan.jpg»"),
            (IssueLevel.warning, "Ещё одно предупреждение"),
        ]
        status, _label, reason = build_status(issues)
        assert status.value == "approved"
        assert "предупрежден" in reason.lower()

    def test_rejected_when_at_least_one_error(self) -> None:
        issues = [
            (IssueLevel.warning, "Предупреждение"),
            (IssueLevel.error, "Отсутствует обязательный документ: спецификация"),
        ]
        status, _label, reason = build_status(issues)
        assert status.value == "rejected"
        assert "спецификац" in reason.lower()

    def test_rejected_when_multiple_errors_takes_first(self) -> None:
        """reason содержит текст первой ошибки."""
        issues = [
            (IssueLevel.error, "Первая ошибка"),
            (IssueLevel.error, "Вторая ошибка"),
        ]
        _status, _label, reason = build_status(issues)
        assert "первая" in reason.lower()


# ---------- Интеграционные тесты run_check ----------


class TestRunCheckIntegration:
    """Тесты полной проверки пакета через run_check."""

    def test_federal_complete_package_is_approved(
        self, tmp_path, monkeypatch
    ) -> None:
        """Полный пакет federal (4 файла, все типы) → approved."""
        from app.services.file_storage import FileStorage

        storage = FileStorage(base_dir=tmp_path)
        files = [
            ("договор_47.pdf", 100, _FakeStream()),
            ("спецификация_v2.docx", 200, _FakeStream()),
            ("счет_001.pdf", 150, _FakeStream()),
            ("акт_выполненных_работ.pdf", 180, _FakeStream()),
        ]
        result = run_check(files, ProgramType.federal, "test-check-1", storage)

        assert result.status.value == "approved"
        assert len(result.documents) == 4
        # Не должно быть ошибок уровня error.
        assert not any(level == IssueLevel.error for level, _ in result.issues)

    def test_federal_missing_specification_is_rejected(
        self, tmp_path
    ) -> None:
        """federal без спецификации → rejected, в issues есть error про спецификацию."""
        from app.services.file_storage import FileStorage

        storage = FileStorage(base_dir=tmp_path)
        files = [
            ("договор_47.pdf", 100, _FakeStream()),
            ("счет_001.pdf", 150, _FakeStream()),
            ("акт_выполненных_работ.pdf", 180, _FakeStream()),
        ]
        result = run_check(files, ProgramType.federal, "test-check-2", storage)

        assert result.status.value == "rejected"
        error_messages = [msg for level, msg in result.issues if level == IssueLevel.error]
        assert any("спецификац" in m.lower() for m in error_messages)

    def test_regional_without_specification_is_approved(
        self, tmp_path
    ) -> None:
        """regional НЕ требует спецификацию → пакет без неё approved."""
        from app.services.file_storage import FileStorage

        storage = FileStorage(base_dir=tmp_path)
        files = [
            ("договор_47.pdf", 100, _FakeStream()),
            ("счет_001.pdf", 150, _FakeStream()),
            ("акт_выполненных_работ.pdf", 180, _FakeStream()),
        ]
        result = run_check(files, ProgramType.regional, "test-check-3", storage)

        assert result.status.value == "approved"

    def test_invalid_extension_produces_error(self, tmp_path) -> None:
        """Недопустимое расширение → error → rejected."""
        from app.services.file_storage import FileStorage

        storage = FileStorage(base_dir=tmp_path)
        files = [
            ("договор_47.txt", 100, _FakeStream()),  # .txt не разрешён
            ("спецификация.docx", 200, _FakeStream()),
            ("счет.pdf", 150, _FakeStream()),
            ("акт.pdf", 180, _FakeStream()),
        ]
        result = run_check(files, ProgramType.federal, "test-check-4", storage)

        assert result.status.value == "rejected"
        error_messages = [msg for level, msg in result.issues if level == IssueLevel.error]
        assert any("формат" in m.lower() for m in error_messages)

    def test_unknown_filename_produces_warning_not_error(self, tmp_path) -> None:
        """Нераспознанное имя файла → warning (не error).

        Даже если есть warning, статус может оставаться approved (если других
        ошибок нет и пакет комплектен).
        """
        from app.services.file_storage import FileStorage

        storage = FileStorage(base_dir=tmp_path)
        files = [
            ("договор_47.pdf", 100, _FakeStream()),
            ("спецификация.docx", 200, _FakeStream()),
            ("счет.pdf", 150, _FakeStream()),
            ("акт.pdf", 180, _FakeStream()),
            ("scan_0041.jpg", 50, _FakeStream()),  # неизвестный тип
        ]
        result = run_check(files, ProgramType.federal, "test-check-5", storage)

        # warning есть, но error-ов нет → approved
        assert result.status.value == "approved"
        warning_messages = [
            msg for level, msg in result.issues if level == IssueLevel.warning
        ]
        assert any("scan_0041" in m for m in warning_messages)

    def test_oversized_file_produces_error(self, tmp_path, monkeypatch) -> None:
        """Файл больше 20 МБ → error → rejected."""
        from app.services import check_service as cs
        from app.services.file_storage import FileStorage

        # Подменяем лимит на 1 байт, чтобы не создавать реальный большой файл.
        monkeypatch.setattr(cs.settings, "max_file_size_mb", 0)
        # 0 МБ = 0 байт, любой непустой файл превысит лимит.

        storage = FileStorage(base_dir=tmp_path)
        files = [
            ("договор_47.pdf", 100, _FakeStream(b"x" * 100)),
            ("спецификация.docx", 200, _FakeStream()),
            ("счет.pdf", 150, _FakeStream()),
            ("акт.pdf", 180, _FakeStream()),
        ]
        result = run_check(files, ProgramType.federal, "test-check-6", storage)

        assert result.status.value == "rejected"
        error_messages = [msg for level, msg in result.issues if level == IssueLevel.error]
        assert any("превышает" in m.lower() for m in error_messages)

    def test_extracted_is_stub_with_none_values(self, tmp_path) -> None:
        """extracted — заглушка: все поля None (см. README → ограничения)."""
        from app.services.file_storage import FileStorage

        storage = FileStorage(base_dir=tmp_path)
        files = [
            ("договор.pdf", 100, _FakeStream()),
            ("спецификация.docx", 100, _FakeStream()),
            ("счет.pdf", 100, _FakeStream()),
            ("акт.pdf", 100, _FakeStream()),
        ]
        result = run_check(files, ProgramType.federal, "test-check-7", storage)

        assert result.extracted == {
            "contractor": None,
            "amount": None,
            "date": None,
            "subject": None,
        }
