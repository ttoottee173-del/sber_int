# Loan Check API

REST API сервис проверки пакетов документов для льготных кредитов.
Тестовое задание для backend-разработчика.

Сервис принимает пакет документов (договор, спецификация, счёт, акт/УПД),
определяет тип каждого файла по имени, проверяет комплектность пакета
в зависимости от программы (`federal` / `regional`), формирует итоговый
статус `approved` / `rejected` и сохраняет результат в PostgreSQL.

---

## Содержание

1. [Технологии и обоснование](#технологии-и-обоснование)
2. [Архитектура решения](#архитектура-решения)
3. [Быстрый старт (Docker)](#быстрый-старт-docker)
4. [Локальный запуск без Docker](#локальный-запуск-без-docker)
5. [Переменные окружения](#переменные-окружения)
6. [API — примеры использования](#api--примеры-использования)
7. [Тесты](#тесты)
8. [Известные ограничения](#известные-ограничения)

---

## Технологии и обоснование

| Технология | Версия | Зачем |
|---|---|---|
| **Python** | 3.11 | Базовый язык, указан в ТЗ. |
| **FastAPI** | 0.115 | Современный ASGI-фреймворк: автогенерация OpenAPI-документации (`/docs`, `/redoc`), нативная поддержка `multipart/form-data`, Pydantic-валидация. |
| **SQLAlchemy** | 2.0 | ORM поверх PostgreSQL. Используется современный стиль `Mapped`/`mapped_column`. |
| **PostgreSQL** | 16 | Реляционная СУБД для хранения истории проверок, документов и проблем. |
| **Alembic** | 1.14 | Миграции схемы БД. Применяются автоматически при старте контейнера. |
| **Pydantic** | 2.10 / pydantic-settings | Валидация входных данных и типизация ответов. Настройки из `.env`. |
| **Uvicorn** | 0.34 | ASGI-сервер для запуска FastAPI. |
| **pytest** | 8.3 | Тестирование логики детектора документов и формирования статуса. |
| **Docker / Docker Compose** | — | Воспроизводимое окружение: одна команда `docker compose up` поднимает и БД, и API. |

---

## Архитектура решения

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Клиент (curl / frontend)                     │
└───────────────────────────────────┬──────────────────────────────────┘
                                     │  HTTP (multipart/form-data, JSON)
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          FastAPI (app/main.py)                        │
│  - маршрутизация: /api/checks, /api/checks/{id}, /health             │
│  - обработка ошибок (400, 404, 422, 500)                             │
│  - lifespan: создание таблиц (dev) / миграции Alembic (prod)         │
└───────────────────────────────────┬──────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Роутер (app/routers/checks.py)                     │
│  POST /api/checks      — приём файлов + запуск проверки               │
│  GET  /api/checks      — список всех проверок (краткая форма)         │
│  GET  /api/checks/{id} — полный результат одной проверки              │
└──────────────┬───────────────────────┬───────────────────────────────┘
               │                       │
               ▼                       ▼
┌──────────────────────────┐  ┌────────────────────────────────────────┐
│  app/services/           │  │  app/database.py + app/models.py       │
│  ├─ document_detector.py │  │  SQLAlchemy ORM:                        │
│  │   определение типа    │  │   - Check  (одна проверка)              │
│  │   по имени файла      │  │   - Document (файл внутри пакета)       │
│  ├─ file_storage.py      │  │   - Issue   (ошибка/warning)            │
│  │   сохранение файлов   │  └────────────────────────────────────────┘
│  │   в локальную папку   │                  │
│  └─ check_service.py     │                  │
│      оркестрация         │                  ▼
│      проверки + статус   │  ┌────────────────────────────────────────┐
└────────────┬─────────────┘  │           PostgreSQL 16                 │
             │                │  (контейнер db в docker-compose)        │
             ▼                └────────────────────────────────────────┘
┌──────────────────────────┐
│  /app/uploads/<check_id>/│
│   <filename>             │
│   (файловое хранилище)   │
└──────────────────────────┘
```

### Слои приложения

- **`app/main.py`** — точка входа FastAPI, регистрация роутеров, healthcheck.
- **`app/config.py`** — настройки через `pydantic-settings` (читает `.env`).
- **`app/database.py`** — engine, SessionLocal, зависимость `get_db`.
- **`app/models.py`** — ORM-модели `Check`, `Document`, `Issue` + Enum'ы.
- **`app/schemas.py`** — Pydantic-схемы входных/выходных данных.
- **`app/routers/checks.py`** — три эндпоинта API.
- **`app/services/document_detector.py`** — определение типа документа по имени файла.
- **`app/services/file_storage.py`** — сохранение файлов на диск.
- **`app/services/check_service.py`** — оркестрация проверки: сохранение → анализ → статус → БД.
- **`alembic/`** — миграции схемы БД.
- **`tests/`** — pytest-тесты логики (детектор + статус + интеграция).

### Модель данных

```
checks (1) ──< (N) documents     # один пакет — много файлов
checks (1) ──< (N) issues        # один пакет — много проблем
```

`checks.extracted` хранит JSON-поле с извлечёнными данными (contractor, amount,
date, subject). В рамках тестового задания извлечение НЕ реализовано —
поле всегда содержит `null`-значения (см. раздел «Известные ограничения»).

---

## Быстрый старт (Docker)

> Требуется установленный Docker и Docker Compose.

```bash
# 1. Скопировать пример перемененных окружения
cp .env.example .env

# 2. Поднять проект одной командой
docker compose up --build
```

После старта:

- API будет доступен по адресу: **http://localhost:8000**
- Swagger UI (документация): **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**
- Healthcheck: **http://localhost:8000/health**

При первом старте Alembic автоматически применит миграции
(`alembic upgrade head`) и создаст таблицы `checks`, `documents`, `issues`.

### Остановка

```bash
docker compose down           # остановить контейнеры
docker compose down -v        # остановить + удалить том с данными БД
```

---

## Локальный запуск без Docker

Удобно для разработки и отладки.

```bash
# 1. Создать и активировать виртуальное окружение
python -m venv .venv(
  brew install python@3.11 
  /opt/homebrew/bin/python3.11 -m venv venv
  )
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Подготовить .env (минимум — указать URL подключения к БД)
cp .env.example .env
# Отредактировать .env: указать DATABASE_URL для ЛОКАЛЬНОЙ PostgreSQL
#   DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/loan_check_db

# 4. Применить миграции
alembic upgrade head

# 5. Запустить приложение
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> В dev-режиме (`APP_DEBUG=true`) таблицы создаются автоматически через
> `Base.metadata.create_all()` — это позволяет стартовать без Alembic.
> В prod-режиме используйте **только** Alembic.

---

## Переменные окружения

Все переменные описаны в `.env.example`. Копируйте его в `.env` и при
необходимости редактируйте.

| Переменная | По умолчанию | Описание |
|---|---|---|
| `APP_HOST` | `0.0.0.0` | Хост, на котором слушает uvicorn. |
| `APP_PORT` | `8000` | Порт uvicorn. |
| `APP_DEBUG` | `true` | Если `true` — подробные логи + авто-создание таблиц (без Alembic). В prod ставить `false`. |
| `POSTGRES_USER` | `loan_check` | Пользователь PostgreSQL. |
| `POSTGRES_PASSWORD` | `loan_check_pass` | Пароль PostgreSQL. |
| `POSTGRES_DB` | `loan_check_db` | Имя базы данных. |
| `POSTGRES_HOST` | `localhost` | Хост PostgreSQL (имя сервиса в docker-compose). |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL. |
| `DATABASE_URL` | postgresql+psycopg2://loan_check:loan_check_pass@localhost:5432/loan_check_db | Полная строка подключения. **Если задана — имеет приоритет** над отдельными `POSTGRES_*`. |
| `UPLOAD_DIR` | `/app/uploads` | Локальная папка для сохранения загруженных файлов. |
| `MAX_FILE_SIZE_MB` | `20` | Максимальный размер файла в МБ (пункт 5 ТЗ). |
| `ALLOWED_EXTENSIONS` | `pdf,docx,jpg,jpeg,png` | Разрешённые расширения через запятую (пункт 5 ТЗ). |

---

## API — примеры использования

### 1. `POST /api/checks` — загрузить пакет и запустить проверку

Принимает `multipart/form-data`: поле `program` (`federal` или `regional`)
и один или несколько файлов.

```bash
# Полный пакет для federal (должен быть approved)
curl -X POST http://localhost:8000/api/checks \
  -F "program=federal" \
  -F "files=@договор_47.pdf" \
  -F "files=@спецификация_v2.docx" \
  -F "files=@счет_001.pdf" \
  -F "files=@акт_выполненных_работ.pdf"
```

Пример ответа:

```json
{
  "check_id": "abc123-...",
  "status": "approved",
  "status_label": "Можно заявлять в банк",
  "reason": "Все обязательные документы присутствуют, нарушений не найдено.",
  "issues": [],
  "documents": [
    { "name": "договор_47.pdf",         "detected_type": "contract",      "size_kb": 142 },
    { "name": "спецификация_v2.docx",   "detected_type": "specification", "size_kb": 88  },
    { "name": "счет_001.pdf",           "detected_type": "invoice",       "size_kb": 56  },
    { "name": "акт_выполненных_работ.pdf", "detected_type": "act",        "size_kb": 175 }
  ],
  "extracted": {
    "contractor": null,
    "amount": null,
    "date": null,
    "subject": null
  },
  "checked_at": "2025-03-15T14:32:00Z"
}
```

Пример `rejected` (нет спецификации для federal):

```json
{
  "check_id": "xyz789-...",
  "status": "rejected",
  "status_label": "Нельзя заявлять в банк",
  "reason": "Отсутствует обязательный документ: спецификация",
  "issues": [
    { "level": "error",   "message": "Отсутствует обязательный документ: спецификация" },
    { "level": "warning", "message": "Не удалось определить тип документа: «scan_0041.jpg»" }
  ],
  "documents": [...],
  "extracted": {...},
  "checked_at": "2025-03-15T14:35:00Z"
}
```

**HTTP-коды ответов `POST /api/checks`:**

| Код | Когда |
|---|---|
| `201 Created` | Проверка выполнена (статус может быть как `approved`, так и `rejected`). |
| `400 Bad Request` | Не передано ни одного файла. |
| `422 Unprocessable Entity` | Поле `program` не равно `federal`/`regional`. |
| `500 Internal Server Error` | Ошибка БД или файлового хранилища. |

### 2. `GET /api/checks` — список всех проверок

```bash
curl http://localhost:8000/api/checks
```

```json
[
  {
    "id": "abc123-...",
    "checked_at": "2025-03-15T14:32:00Z",
    "program": "federal",
    "status": "approved",
    "documents_count": 4
  },
  {
    "id": "xyz789-...",
    "checked_at": "2025-03-15T14:35:00Z",
    "program": "federal",
    "status": "rejected",
    "documents_count": 3
  }
]
```

### 3. `GET /api/checks/{check_id}` — полный результат проверки

```bash
curl http://localhost:8000/api/checks/abc123-...
```

Возвращает ту же структуру, что и `POST /api/checks`.

| Код | Когда |
|---|---|
| `200 OK` | Проверка найдена. |
| `404 Not Found` | Проверка с указанным `id` не существует. |

---

## Тесты

Тесты покрывают (пункт 7 ТЗ):

- логику определения типа документа (`tests/test_document_detector.py`),
- формирование итогового статуса (`tests/test_status.py`),
- полную интеграцию `run_check` (формат, размер, комплектность).

Тесты используют in-memory SQLite, поэтому **не требуют** запущенный PostgreSQL.

### Запуск в Docker

```bash
docker compose run --rm api pytest -v
```

### Запуск локально

```bash
pip install -r requirements.txt
pytest -v
```

### Что проверяют тесты (минимум 5 кейсов — выполнено с запасом)

| № | Файл | Что проверяет |
|---|---|---|
| 1 | `test_detect_type` (параметризованный, 17 случаев) | Корректное определение типа для всех поддерживаемых шаблонов. |
| 2 | `test_case_insensitive` | Нечувствительность к регистру. |
| 3 | `test_yo_vs_e_normalization` | `счёт` и `счет` распознаются одинаково. |
| 4 | `test_approved_when_no_issues` | Нет проблем → `approved`. |
| 5 | `test_rejected_when_at_least_one_error` | Есть error → `rejected`. |
| 6 | `test_approved_with_only_warnings` | Только warnings → `approved`. |
| 7 | `test_federal_complete_package_is_approved` | Полный пакет federal → `approved`. |
| 8 | `test_federal_missing_specification_is_rejected` | federal без спецификации → `rejected`. |
| 9 | `test_regional_without_specification_is_approved` | regional без спецификации → `approved`. |
| 10 | `test_invalid_extension_produces_error` | `.txt` → `error`. |
| 11 | `test_unknown_filename_produces_warning_not_error` | `scan_0041.jpg` → `warning`. |
| 12 | `test_oversized_file_produces_error` | Файл > 20 МБ → `error`. |

---

## Известные ограничения

В рамках тестового задания следующие возможности **сознательно не реализованы**
(они выходят за рамки обязательных пунктов 1–9 ТЗ):

1. **Извлечение данных (`extracted`)**. Поле `extracted` в ответе всегда содержит
   `null`-значения. Реальное извлечение подрядчика, суммы, даты и предмета
   договора требует OCR для сканов и текстового парсинга для PDF/DOCX — это
   отдельная большая задача. В ТЗ способ извлечения не указан.

2. **Статус `check_in_progress`**. Проверка выполняется синхронно в рамках
   запроса `POST /api/checks`. Поле оставлено в enum'е `CheckStatus` для
   совместимости с ТЗ, но фактически не используется (всегда `approved` или
   `rejected`).

3. **Авторизация и роли**. В пунктах 1–9 ТЗ этого требования нет, хотя в
   разделе TO BE упоминается «разграничение прав доступа». Эндпоинты
   доступны без аутентификации.

4. **Версионность документов**. Каждая загрузка создаёт новый `Check` с новым
   `id`. Истории версий отдельных файлов не ведётся (не требуется пунктами 1–9).

5. **Удаление файлов после rejected**. Файлы сохраняются всегда — даже если
   пакет отклонён. Это позволяет сохранить доказательство загрузки для аудита.

---

## Структура проекта

```
loan-check-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI приложение
│   ├── config.py            # настройки (pydantic-settings)
│   ├── database.py          # SQLAlchemy engine + Session
│   ├── models.py            # ORM-модели (Check, Document, Issue)
│   ├── schemas.py           # Pydantic-схемы
│   ├── routers/
│   │   ├── __init__.py
│   │   └── checks.py        # POST + GET /api/checks
│   └── services/
│       ├── __init__.py
│       ├── document_detector.py   # определение типа по имени файла
│       ├── file_storage.py        # сохранение файлов в папку
│       └── check_service.py       # оркестрация проверки
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial.py  # начальная миграция
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # фикстуры pytest (in-memory SQLite, TestClient)
│   ├── test_document_detector.py
│   └── test_status.py
├── uploads/                 # загруженные файлы (создаётся автоматически)
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```
