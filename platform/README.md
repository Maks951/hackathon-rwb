# Python runs API и worker — участок Ярослава

Реализованы API запусков, orchestration, хранение файлов попыток, repair (до двух
циклов), проверка manifest и воспроизводимый ZIP. Контракт HTTP соответствует
`RunDto`/`RunDetailsDto` из командного задания. Исходники frontend не изменялись.

Это компонент платформы, а не полностью интегрированный командный продукт.
Подключён модуль проектов Романа из `database_backend` (`18100ec`): PostgreSQL,
Alembic и projects API в основном приложении. Runs repository, Qwen,
runner и шаблоны admin/PWA/SQL ещё нужно подключить от владельцев.
Без доступной БД/миграции `/health` отвечает `503`; runs API без RunRepository
также отвечает `503`. Worker без обязательных
адаптеров завершается с понятной ошибкой. В продакшен-коде нет очереди в памяти,
модельных ответов-заглушек и фиктивных результатов проверки.

## Локальный запуск

Рабочий каталог для всех Python-команд — `platform/`. Python 3.12; зависимости
и транзитивные версии закреплены в `uv.lock`.

```bash
uv sync --frozen --group dev
cp .env.example .env
# Сначала настроить существующий PostgreSQL в DATABASE_URL.
uv run --env-file .env --frozen python -m alembic upgrade head
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

После подключения модулей команды укажи в `.env`
`RWB_RUNTIME_FACTORY=имя_модуля:имя_фабрики`. Фабрика возвращает `app.ports.Runtime`;
пример и правила транзакций — в `../docs/integration.md`. Затем в отдельном
терминале из того же каталога и с тем же `.env`:

```bash
uv run --frozen python -m app.worker
```

Swagger: `http://127.0.0.1:8000/docs`. `GET /health` проверяет доступность
repository либо таблицы projects до интеграции runs. Работа worker/runner проверяется прогоном,
а не одним health-запросом. Demo предполагает закрытый командный доступ.

В текущем окружении уже создан интерпретатор `platform/.venv/bin/python`.
Его можно выбрать в настройках Python interpreter в IDE. Команды без uv:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv/bin/python -m app.worker
```

## API и передача тимлиду

- `POST /api/v1/projects` → `201 ProjectRead`, `{name,requirements}`.
- `GET /api/v1/projects` → `{items: ProjectRead[]}`.
- `GET /api/v1/projects/{id}` → ProjectRead или `404 not_found`.
- `POST /api/v1/projects/{id}/runs`, JSON `{}`, header `Idempotency-Key: UUID`
  → `202 RunDto`, header `Location` указывает на статус.
- `GET /api/v1/runs/{id}` → `RunDetailsDto`.
- `GET /api/v1/runs/{id}/events?afterSequence=0` → `items`, `nextSequence`.
- `GET /api/v1/runs/{id}/download` → ZIP или `409 package_not_ready`.
- `GET /health` → `200` или `503`.

Projects router Романа подключён и использует отдельную Session на запрос.
Artifacts/auth можно подключить через `Runtime.routers`. Второго варианта
projects repository или migrations здесь нет.
Polling UI — каждые 2 секунды, остановить на `succeeded`/`failed`.

Готовые файлы контракта: `../contracts/runs.ts`, `../contracts/platform-openapi.json`.
Они описывают runs и подключённые projects routes. Переэкспорт:

```bash
uv run --frozen python -m app.export_contracts
```

## Проверки

```bash
uv run --frozen ruff check app tests
uv run --frozen ruff format --check app tests
uv run --frozen pytest -q
```

Тесты проверяют наш HTTP-контракт и оркестрацию с изолированными test doubles.
Они не доказывают работоспособность PostgreSQL-очереди, реального Qwen, сборку
сгенерированного моделью продукта или deployment. Статус проверок и зависимостей
зафиксирован в `../docs/yaroslav-handoff.md`.

Контейнерный запуск: [docker-integration.md](../docs/docker-integration.md).
Документация сервиса/API: [platform-service.md](../docs/platform-service.md),
[platform-api.md](../docs/platform-api.md).
Новые правила генерации: [documentation-policy.md](../docs/documentation-policy.md).

Технические решения сверены с [документацией FastAPI](https://fastapi.tiangolo.com/advanced/testing-events/)
и [Pydantic aliases](https://docs.pydantic.dev/latest/concepts/alias/).
