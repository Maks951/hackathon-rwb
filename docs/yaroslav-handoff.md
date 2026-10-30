# Ярослав — результат работы

Дата: 30.10.2026. Локальная ветка: `backend`.
Задание: `03_Yaroslav_Python_Pipeline.md`; материалы прочитаны из
`/home/hivorbud/rwb hackaton`. Последнее прочитанное уточнение организаторов —
30.10 16:17: Qwen API доступен из VM, HTTP `/chat/completions`; GitLab обещан позже.
Ссылка/ключ/фактический modelId в конфигурацию не выдумывались.

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

## Что нужно получить для настоящего end-to-end

1. Роман: PostgreSQL RunRepository с транзакционной идемпотентностью, snapshot,
   SKIP LOCKED queue, событиями/metadata/heartbeat/stale recovery; routers
   проектов и artifacts, свои модели и Alembic миграции. Их реализация не дублировалась.
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

Реальные Qwen/DB integration, PostgreSQL concurrency, generated product acceptance,
publish и deploy **не проверены**: требуемые модули/доступы отсутствовали в ветке.
Запуск всего командного продукта не заявляется готовым.
Frontend, коллегиальные migrations, Kafka/Compose/CI/модельные prompts не переписывались.
Рабочая ветка для передачи изменений команде: `backend`.
