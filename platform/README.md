# Python runs API и worker — участок Ярослава

Реализованы API запусков, orchestration, хранение файлов попыток, repair (до двух
циклов), проверка manifest и воспроизводимый ZIP. Контракт HTTP соответствует
`RunDto`/`RunDetailsDto` из командного задания. Исходники frontend не изменялись.

Это компонент платформы, а не полностью интегрированный командный продукт.
В исходной ветке были только заглушки backend/DB. Реальные repository, Qwen,
runner и шаблоны admin/PWA/SQL ещё нужно подключить от владельцев.
Без repository `/health` и runs API отвечают `503`; worker без обязательных
адаптеров завершается с понятной ошибкой. В продакшен-коде нет очереди в памяти,
модельных ответов-заглушек и фиктивных результатов проверки.

## Локальный запуск

Рабочий каталог для всех Python-команд — `platform/`. Python 3.12; зависимости
и транзитивные версии закреплены в `uv.lock`.

```bash
uv sync --frozen --group dev
cp .env.example .env
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
repository. Наличие работающего worker и runner проверяется интеграционным прогоном,
а не одним health-запросом. Demo предполагает закрытый командный доступ.

В текущем окружении уже создан интерпретатор `platform/.venv/bin/python`.
Его можно выбрать в настройках Python interpreter в IDE. Команды без uv:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv/bin/python -m app.worker
```

## API и передача тимлиду

- `POST /api/v1/projects/{id}/runs`, JSON `{}`, header `Idempotency-Key: UUID`
  → `202 RunDto`, header `Location` указывает на статус.
- `GET /api/v1/runs/{id}` → `RunDetailsDto`.
- `GET /api/v1/runs/{id}/events?afterSequence=0` → `items`, `nextSequence`.
- `GET /api/v1/runs/{id}/download` → ZIP или `409 package_not_ready`.
- `GET /health` → `200` или `503`.

Projects/artifacts endpoints подключаются готовыми routers Романа через
`Runtime.routers`. Здесь не создаётся второй вариант его API или миграций.
Polling UI — каждые 2 секунды, остановить на `succeeded`/`failed`.

Готовые файлы контракта: `../contracts/runs.ts`, `../contracts/platform-openapi.json`.
Они описывают только подключённые маршруты; API проектов/артефактов добавится при
интеграции. Переэкспорт:

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

Технические решения сверены с [документацией FastAPI](https://fastapi.tiangolo.com/advanced/testing-events/)
и [Pydantic aliases](https://docs.pydantic.dev/latest/concepts/alias/).
