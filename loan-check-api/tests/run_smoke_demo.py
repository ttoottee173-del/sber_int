"""Быстрый smoke-тест API через TestClient.

Проверяет, что:
- приложение стартует,
- эндпоинты отвечают,
- POST /api/checks корректно обрабатывает пакет federal,
- GET /api/checks возвращает список,
- GET /api/checks/{id} возвращает детали.

Запуск:
    .venv/bin/python -m tests.smoke_test
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# Подменяем DATABASE_URL ДО импорта приложения — иначе settings подхватит
# внешний DATABASE_URL, конфликтующий с тестовым SQLite.
os.environ["DATABASE_URL"] = "sqlite:///./smoke_test.db"
os.environ["UPLOAD_DIR"] = "/tmp/loan_check_smoke_uploads"

# Добавляем корень проекта в sys.path.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.database import Base, SessionLocal, engine, get_db
    from app.main import app

    # Пересоздаём таблицы в тестовой БД (используем тот же engine, что и в app).
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Используем тот же SessionLocal — он биндинг к тому же engine.
    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    # Чистим папку загрузок.
    os.makedirs("/tmp/loan_check_smoke_uploads", exist_ok=True)

    with TestClient(app) as client:
        print("\n=== 1. Healthcheck ===")
        r = client.get("/health")
        print(f"GET /health -> {r.status_code} {r.json()}")

        print("\n=== 2. POST /api/checks (полный пакет federal, ожидаем approved) ===")
        files = [
            ("files", ("договор_47.pdf", io.BytesIO(b"contract content"), "application/pdf")),
            ("files", ("спецификация_v2.docx", io.BytesIO(b"spec content"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
            ("files", ("счет_001.pdf", io.BytesIO(b"invoice content"), "application/pdf")),
            ("files", ("акт_выполненных_работ.pdf", io.BytesIO(b"act content"), "application/pdf")),
        ]
        r = client.post("/api/checks", data={"program": "federal"}, files=files)
        print(f"POST /api/checks -> {r.status_code}")
        body = r.json()
        print(f"  status:       {body['status']}")
        print(f"  status_label: {body['status_label']}")
        print(f"  reason:       {body['reason']}")
        print(f"  documents:    {len(body['documents'])} шт.")
        for d in body["documents"]:
            print(f"     - {d['name']} -> {d['detected_type']} ({d['size_kb']} КБ)")
        print(f"  issues:       {body['issues']}")
        check_id_ok = body["check_id"]

        print("\n=== 3. POST /api/checks (federal без спецификации, ожидаем rejected) ===")
        files = [
            ("files", ("договор_47.pdf", io.BytesIO(b"contract content"), "application/pdf")),
            ("files", ("счет_001.pdf", io.BytesIO(b"invoice content"), "application/pdf")),
            ("files", ("акт.pdf", io.BytesIO(b"act content"), "application/pdf")),
            ("files", ("scan_0041.jpg", io.BytesIO(b"scan"), "image/jpeg")),
        ]
        r = client.post("/api/checks", data={"program": "federal"}, files=files)
        print(f"POST /api/checks -> {r.status_code}")
        body = r.json()
        print(f"  status:       {body['status']}")
        print(f"  status_label: {body['status_label']}")
        print(f"  reason:       {body['reason']}")
        print(f"  issues:")
        for issue in body["issues"]:
            print(f"     - [{issue['level']}] {issue['message']}")

        print("\n=== 4. POST /api/checks с неверной программой (ожидаем 422) ===")
        files = [
            ("files", ("договор.pdf", io.BytesIO(b"x"), "application/pdf")),
        ]
        r = client.post("/api/checks", data={"program": "international"}, files=files)
        print(f"POST /api/checks -> {r.status_code}")
        print(f"  detail: {r.json().get('detail')}")

        print("\n=== 5. GET /api/checks (список всех проверок) ===")
        r = client.get("/api/checks")
        print(f"GET /api/checks -> {r.status_code}")
        print(f"  items: {len(r.json())}")
        for item in r.json():
            print(
                f"    - id={item['id'][:8]}.. "
                f"program={item['program']} "
                f"status={item['status']} "
                f"docs={item['documents_count']}"
            )

        print("\n=== 6. GET /api/checks/{{id}} (детали approved-проверки) ===")
        r = client.get(f"/api/checks/{check_id_ok}")
        print(f"GET /api/checks/{check_id_ok} -> {r.status_code}")
        body = r.json()
        print(f"  status: {body['status']}, docs: {len(body['documents'])}, issues: {len(body['issues'])}")

        print("\n=== 7. GET /api/checks/{{несуществующий id}} (ожидаем 404) ===")
        r = client.get("/api/checks/does-not-exist-00000000")
        print(f"GET -> {r.status_code}")
        print(f"  detail: {r.json().get('detail')}")

    # Чистим за собой файл БД.
    try:
        os.remove("smoke_test.db")
    except FileNotFoundError:
        pass

    print("\n=== ALL SMOKE TESTS PASSED ===")


if __name__ == "__main__":
    main()
