# Ярослав — результат работы

Дата: 30.10.2026. Локальная ветка: `backend`.
Задание: `03_Yaroslav_Python_Pipeline.md`; материалы прочитаны из
`/home/hivorbud/rwb hackaton`. Последнее прочитанное уточнение организаторов —
30.10 16:17: Qwen API доступен из VM, HTTP `/chat/completions`; GitLab обещан позже.
Ссылка/ключ/фактический modelId в конфигурацию не выдумывались.

## Обновление: Docker, projects и новые регламенты

Влиты ветки `Docker` (`b8ca420`) и `database_backend` (`18100ec`), их история
сохранена. Код проектов Романа подключён в production composition root через
`app.integrations.projects`: repository/model/migration переиспользованы, новых
таблиц/миграций в этом участке не создавалось. Небольшие изменения в исходниках
Романа — только общее форматирование/UTC alias, бизнес-логика сохранена.

Добавлены platform/Dockerfile, .dockerignore и compose.backend.yaml: PostgreSQL
17.9 → миграция → API, worker отдельно в профиле pipeline; shared generated volume,
пользователь 10001, без Docker socket. Python base закреплён проверенным digest,
requirements для pip экспортированы с hashes из единого uv.lock.

Новые пять PDF организаторов нормализованы в immutable documentation-policy.json
(имена/хеши источников сохранены). Policy передаётся на всех stages; структурная
check documentation проверяет 6 документов, непустые разделы, FR-ID и каждый
API endpoint. Ошибки участвуют в repair. ZIP включает реальный validation report
с source manifest и policy hash. Смысловую правильность документа check не доказывает.

Актуальная инструкция: [Docker](docker-integration.md), [сервис](platform-service.md),
[API](platform-api.md), [политика документации](documentation-policy.md),
[ADR](adr-platform-runtime.md). OpenAPI/TypeScript обновлены для projects; RunDto
и RunDetailsDto сохранены.

Проверки обновления:

```bash
# Из platform; переменная TEST_DATABASE_URL удалена для изоляции SQLite fixtures.
env -u TEST_DATABASE_URL .venv/bin/pytest -q
.venv/bin/ruff check app tests scripts
.venv/bin/ruff format --check app tests scripts
.venv/bin/python -m compileall -q app scripts
.venv/bin/python -m app.export_contracts

# Из корня; в проверенном окружении имеется rootless Podman.
podman build -f platform/Dockerfile -t localhost/rwb-platform:dev .
platform/.venv/bin/python platform/scripts/check_container_stack.py \
  --compose /tmp/rwb-bootstrap/bin/podman-compose
```

Python: **68 passed**, Ruff/format/compileall/OpenAPI export успешно. Есть 20
deprecation warnings из Starlette TestClient и Alembic config, без failures.
Проверка runner требует именно bool True: строка "false" не засчитывается как passed.

Контейнерная сборка и smoke **passed**: настоящий PostgreSQL 17.9, Alembic,
POST project 201, сохранение/GET после рестарта API, 400 invalid input, 404 missing,
UID=10001, writable generated volume, .env/.venv исключены из образа. Проверка
использовала уникальный временный Compose project и удалила только свои volumes.
На системе с podman-compose в PATH аргумент --compose не требуется.
Docker Engine отдельно не проверялся; использован совместимый Podman build/Compose.

### Актуальные блокеры

Работают API проектов и PostgreSQL, но RunRepository (runs/steps/events/artifacts),
Qwen adapter/specs/prompts, изолированный runner и шаблоны admin/PWA/Postgres
продукта ещё отсутствуют. Health=200 подтверждает API/БД, не весь pipeline.
Генерация по настоящему Qwen, PostgreSQL-очередь/конкуренция и deployment продукта
не проверены и не считаются завершёнными. В production-коде заглушек вместо них нет.

Ниже сохранены результаты первого этапа для контекста; они не заменяют актуальный статус выше.

## Что реализовано в своём участке

- `platform/app/api/`, `schemas/runs.py`: FastAPI routes создания/просмотра run,
  events cursor, ZIP download, health и безопасный формат ошибок. POST → 202,
  UUID Idempotency-Key передаётся repository; JSON DTO в camelCase соответствует
  присланным `RunDto`/`RunDetailsDto`.
- `platform/app/worker.py`: отдельный процесс, claim через repository, heartbeat,
  stale recovery hook, deadline, завершение/остановка текущих операций при ошибке.
  Долгие обращения не выполняются в API и не охватываются SQL transaction.
- `platform/app/services/steps.py`: сохранённые входы/выходы, Pydantic validation,
  hashes, promptVersion/modelId/token metrics/time; максимум два transient retry
  и одна JSON correction. Невалидные/обрезанные ответы не считаются успешными.
- `platform/app/services/pipeline.py`: analyze/design → последовательная генерация
  компонентов → validation → до двух repair → package → optional publish/deploy.
  Один сохранённый API contract передаётся всем стадиям. Неизменяемые specs;
  изменение требований требует нового run и нового полного дерева.
- `platform/app/services/storage.py`: allowlist областей и расширений, защита
  traversal/absolute paths/symlinks/duplicates, лимиты, SHA256 manifest,
  неизменяемые попытки и воспроизводимый ZIP с фиксированными timestamps/order.
  Manifest проверяется до/после runner и при упаковке.
- `templates/dotnet-api`: собираемый .NET 10 / C# 14 skeleton, EF PostgreSQL,
  health/readiness, единый безопасный формат ошибок, registration/routing hooks
  для доменного кода модели, xUnit project. Python backend продукта не генерируется.
- `contracts/runs.ts`, `contracts/platform-openapi.json`: экспорт для тимлида/UI;
  генерируются из Python DTO. `platform/uv.lock` и NuGet `packages.lock.json` закреплены.

Статусы имеют отдельный смысл: `run=succeeded` только после passed validation и ZIP;
`deploymentStatus=skipped/failed/deployed` отражает фактический результат deployment.
URL остаются null без успешного соответствующего adapter. Пустой/неполный validation
report не passed; несовпадение API — failed check и блокировка package.

## Проверки и фактический результат

Из `platform/` (использован Python 3.12.16):

```bash
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
.venv/bin/python -m compileall -q app
.venv/bin/pytest -q
.venv/bin/python -m app.export_contracts
```

Результат: Ruff/format/compileall/export успешно; **50 passed** для pytest.
Есть deprecation warning Starlette о будущей замене httpx в TestClient;
на результат тестов не влияет. Тесты API выполнены вне sandbox, поскольку
ограничения локальных сокетов блокируют TestClient при связи между потоками.

Из `templates/dotnet-api/` (временный SDK 10.0.100 в `/tmp/rwb-dotnet`):

```bash
/tmp/rwb-dotnet/dotnet restore Generated.slnx --disable-parallel
/tmp/rwb-dotnet/dotnet test Generated.slnx --no-restore --verbosity minimal -m:1
```

Результат: restore/build успешно; **3 passed, 0 failed, 0 skipped**. Проверены
liveness, безопасный 404 и readiness=503 при отсутствии product DB. MSBuild/test
запускались вне sandbox: внутри запрещены IPC sockets. Это проверка написанного
вручную технологического шаблона, а не сборки произвольного модельного результата.

## Зависимости первого этапа (projects теперь подключены)

1. Роман: PostgreSQL RunRepository с транзакционной идемпотентностью, snapshot,
   SKIP LOCKED queue, событиями/metadata/heartbeat/stale recovery; routers
   artifacts и собственные миграции runs. Projects/model/migration уже подключены из 18100ec.
2. Владимир: реальный Qwen adapter, prompts, полные RequirementsSpec/SystemSpec,
   проверка references, фактические credentials/modelId в ENV на доступной VM.
   Модель и network transport не подменялись заглушкой в production-коде.
3. Дмитрий: изолированный ValidationRunner с реальными build/test/contract/security
   проверками, Compose/CI и optional publisher/deployer. Нельзя засчитывать fake
   runner из тестов как реальную проверку; тестовый generated content не запускается.
4. Максим/Роман: готовые `templates/angular-admin`, `angular-pwa`, `postgres` и
   фиксированные точки подключения генерируемых файлов. Пока отсутствуют, run
   сохраняет выполненные analyze/design и завершается `template_missing`.
5. В composition factory подключить полученные модули по [контракту](integration.md),
   выполнить настоящий Qwen → PostgreSQL → isolated runner → ZIP прогон, затем
   проверить parking acceptance и второй домен с бизнес-экспертами.

Реальные Qwen integration, PostgreSQL queue concurrency, generated product acceptance,
publish и deploy **не проверены**. PostgreSQL для projects проверен в обновлении выше.
Запуск всего командного продукта не заявляется готовым.
Frontend, коллегиальные migrations, Kafka/Compose/CI/модельные prompts не переписывались.
Рабочая ветка для передачи изменений команде: `backend`.
