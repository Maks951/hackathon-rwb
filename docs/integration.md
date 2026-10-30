# Интеграционный контракт участка Ярослава

Источник ролей и публичных DTO: `03_Yaroslav_Python_Pipeline.md`. Публичные поля
сохранены. Внутренние Python Protocol в `platform/app/ports.py` — точки стыковки
для отсутствующих в ветке модулей; это не утверждение, что коллеги уже реализовали
именно такие методы. При интеграции существующие модули оборачиваются адаптерами.

## Composition root

API и worker загружают одну фабрику из `RWB_RUNTIME_FACTORY=module:factory`:

```python
from app.ports import Runtime

def create_runtime(settings) -> Runtime:
    # Здесь подключить реальные экземпляры из модулей владельцев.
    return Runtime(
        repository=run_repository,     # Роман
        generation=qwen_adapter,       # Владимир
        validator=validation_runner,   # Дмитрий
        publisher=publisher_or_none,   # Дмитрий, optional
        deployer=deployer_or_none,     # Дмитрий, optional
        routers=(artifacts_router,),  # Роман, existing prefix; projects already integrated
    )
```

Projects router/repository/migration Романа уже влиты из `18100ec` и подключены
через `app.integrations.projects`. Его sync Sessions выполняются FastAPI в threadpool.
Основной app берёт DATABASE_URL из ENV/.env; engine закрывается при shutdown.
Остальные переменные примера — точки для отсутствующих модулей, не рабочие импорты.
API и worker —
разные процессы; factory не должна запускать фоновые worker-задачи или сохранять
очередь в памяти. SQLAlchemy 2, psycopg 3, Alembic уже включены в
`platform/pyproject.toml`; будущий HTTP adapter добавляет свои runtime зависимости
туда и обновляет uv.lock.
API не получает Qwen/GitLab секреты в ответах; factory берёт секреты из ENV.

## Repository — Роман

Возвращает `RunRecord`, `StepDto`, `EventDto`, `ArtifactRecord` из общего контракта.
Все методы async, самостоятельно открывают и завершают короткие транзакции.
Нельзя хранить одну открытую session/transaction на всё время run или разделять
один mutable AsyncSession между heartbeat и основным pipeline task.

- `create_run(project_id, idempotency_key)` атомарно проверяет проект, копирует
  requirements в неизменяемый snapshot, сохраняет ключ и queued run. Повтор того
  же ключа/проекта возвращает тот же run, включая terminal run. Другой проект с
  тем же ключом → `AppError(..., 409)`. Один queued/running на проект: обеспечить
  unique constraints/partial index и разбор гонок в БД, не только Python-проверку.
  Несуществующий проект → `AppError("not_found", безопасное_сообщение, 404)`.
- `claim_next()` выбирает queued run через `SELECT … FOR UPDATE SKIP LOCKED`,
  ставит `running`, первый heartbeat, событие и **commit до возврата**. Нет run →
  `None`. Сам SQL, модели и миграции остаются в модуле Романа.
- `heartbeat(run_id, now)` обновляет только running run, возвращает bool.
  False/исключение останавливает текущую генерацию; обновлять terminal run нельзя.
- `fail_stale(before, now)` атомарно переводит просроченные running runs и их
  running steps в failed, `worker_interrupted`, устанавливает finishedAt, пишет
  событие. Никакого running→queued или автоматического продолжения.
- `start_step` сохраняет input_path, started_at, `(run_id,key,attempt)` unique,
  running status, current_step и событие. `record_call` немедленно сохраняет
  метаданные вызова и raw-JSON artifact, в том числе для невалидного ответа модели.
- `complete_step` сохраняет output_path, hashes, model/prompt metadata, метрики,
  artifacts, finished_at и status. При `error` не None итоговый status=failed,
  иначе succeeded, в одной транзакции. Так неуспешный validation report остаётся
  сохранённым без промежуточного ложного succeeded. `fail_step` сохраняет failed
  и безопасную ошибку для исключений, когда обычного output нет.
- `set_validation`, `set_deployment`, `set_repository_url`, `save_package` сохраняют
  только фактические результаты. `get_package` возвращает зарегистрированный ZIP
  или None. Непрошедший проверки run ZIP в production pipeline не регистрирует.
- `finish_run` завершает только running run, очищает current_step, ставит
  finished_at и событие. Terminal run не перезаписывать и не возобновлять.
- `list_events` возвращает строго возрастающий sequence, фильтр `sequence > after`,
  limit; sequence выделяется атомарно внутри run. Отсутствие событий не сдвигает cursor.
- Все mutations steps/events/artifacts проверяют принадлежность run и его
  running status. Метаданные raw response регистрируются без утечки в публичный DTO.

Сохраняются UUID, timezone-aware UTC, FK, SHA256 и относительные пути. Для API-ошибок
использовать `AppError` с безопасными текстами; SQL/секреты не попадут в ответ.
Один worker в P0; параллельные воркеры, lease fencing и exactly-once не заявлены.

## Qwen и schema models — Владимир

`output_schema(stage) -> type[BaseModel]`, `generate(GenerationRequest) -> GenerationResponse`.
Настоящий HTTP transport, modelId, auth, prompts и проверка references принадлежат
адаптеру. Локальный pipeline не подставляет выдуманный Qwen endpoint/modelId.

В `inputs`: сохранённый requirements snapshot для analyze; сохранённый
RequirementsSpec для design; сохранённый SystemSpec, единый `generatedApi`, его
hash и контекст соответствующего шаблона для генерации файлов. Большой репозиторий
целиком модели не передаётся. Для repair: сохранённый spec/contract, текущие
генерируемые файлы, diagnostics и workspaceId.
Все stages также получают `documentationPolicy` и SHA256: новые PDF организаторов
нормализованы в `app/resources/documentation-policy.json`.
Правила и имена Markdown-файлов: [documentation-policy.md](documentation-policy.md).

`GenerationResponse`: content — JSON-текст, model_id, prompt_version, finish_reason
(успешное завершение нормализовать в `stop`), nullable input/output_tokens.
`ProviderError(transient=True)` только для 429/5xx/временных transport errors;
ошибки auth/4xx не transient. Адаптер не делает дополнительные скрытые retries:
orchestrator ограничивает их двумя с backoff. Timeout по умолчанию 120 секунд.
Одна JSON correction получает `json_errors` и `previous_output`, невалидный
JSON не парсится через eval и не считается успешным шагом.

Схемы RequirementsSpec/SystemSpec из задания реализует Владимир; reference checks,
уникальные id и типы обязательны. Кодовые этапы возвращают общий `StageFiles`:

```json
{"schemaVersion":1,"files":[{"path":"docs/example.md","content":"..."}],"notes":[]}
```

StageFiles определён в `app.services.storage`. Разрешённые области:

| Stage | Пути продукта |
| --- | --- |
| generate_db | database/generated/*.sql |
| generate_backend | backend/src/Generated.Api/Generated/**/*.cs; backend/tests/Generated.Api.Tests/Generated/**/*.cs |
| generate_web | admin/src/app/generated/** (.ts/.html/.scss/.css) |
| generate_pwa | pwa/src/app/generated/** (.ts/.html/.scss/.css) |
| generate_tests_docs | docs/**/*.md; C# tests/Generated; Angular generated *.spec.ts |
| repair | Только объединение перечисленных областей, без смены spec/контракта/зависимостей |

`SystemSpec.endpoints` сохраняется в один generated-api.json. Идентификаторы endpoint
обязательны и уникальны. Backend/frontend/tests получают этот же контракт. Реальное
совпадение маршрутов/моделей проверяет api_contract check runner.
Пересоздание spec допускается только новым run с новым snapshot: downstream outputs
не переиспользуются. In-run spec editing, step retry/cancel — P1.

Для C# генерации: `IGeneratedModule.RegisterServices/MapEndpoints`, partial
`ProductDbContext`, `IEntityTypeConfiguration<T>`, `db.Set<T>()`. Шаблон не содержит
доменных сущностей. Не генерировать csproj, package manifests, Program.cs или lock.
Правила parking (подтверждение сессии, reminder/history/mock payment) должны
появляться из входных требований/prompts; специальных parking-ветвлений в pipeline нет.

## Templates — Максим / Роман

Загрузить готовые каталоги `templates/angular-admin`, `templates/angular-pwa`,
`templates/postgres`. Они отображаются в продукте в `admin/`, `pwa/`, `database/`;
свой `templates/dotnet-api` отображается в `backend/`.
Angular шаблон должен подключать `src/app/generated/` из фиксированного routing/host,
SQL шаблон — выполнять `database/generated/`, а Compose/CI Дмитрия — собирать это
согласованное дерево. Шаблоны не должны содержать реальные секреты или symlinks.
Модель не может редактировать файлы шаблонов; расширения надо предусмотреть заранее.

## Validation / publish / deploy — Дмитрий

`validate(Workspace)` получает только валидированный workspace ID `<UUID>/<000..002>`
и manifest `{path,mime_type,size_bytes,sha256}`. По manifest скопировать дерево
из `generated/<UUID>/workspaces/<attempt>/` в изолированный runner. Сверить SHA256.
Не собирать прямо в неизменяемом дереве попытки: новые/изменённые файлы будут
обнаружены как corruption. Результат привязан к полному manifest.

Runner не получает shell-команд от модели, Qwen/GitLab секретов, Docker socket
платформы или host mounts. Фиксированный allowlisted профиль, лимиты и изоляция —
ответственность готового runner. Эта часть не запускает сгенерированный код локально.

`ValidationReport.checks` должен содержать уникальные checks с bool passed и
безопасным ограниченным message. Пустой/частичный отчёт не может быть passed.
Обязательные имена: `backend_build`, `backend_tests`, `admin_build`, `pwa_build`,
`api_contract`, `security`. Check `documentation` добавляется pipeline по новым
правилам; это зарезервированное имя, runner его не подменяет.
Можно добавить acceptance/integration/PWA checks;
любая failed check блокирует package. `security` — реальный запуск согласованных
проверок, а не факт наличия сканера. Диагностика не содержит секретов.
Все обязательные checks повторяются после каждого repair (максимум 2).

Optional `publish(run_id, package) -> repositoryUrl`,
`deploy(run_id, workspace) -> previewUrl`: URL только http(s), без credentials,
query-токенов и fragment. None adapter означает отсутствие публикации/`skipped`
deployment. При ошибке deploy: failed step и deploymentStatus=failed, previewUrl=null.
Проверенный/package-ready run может быть succeeded независимо от deploymentStatus.
Токен GitLab остаётся у publisher, не в архиве или UI.

## Владимир: Qwen adapter (реализация в `platform/app/llm/`)

- `QwenGenerationAdapter` реализует существующий `GenerationAdapter` без изменения порта.
- Настройки: `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_API_KEY`; опционально `QWEN_API_PATH` (default `/chat/completions`). Использовать только точные значения endpoint/model/key от организаторов. HTTP разрешён только для localhost; внешний endpoint должен быть HTTPS.
- Ярослав подключает его в своей runtime factory: `generation=create_qwen_adapter(settings)`. Repository/worker composition остаются у Ярослава/Романа.
- Схемы: `RequirementsSpec` для `analyze`, `SystemSpec` для `design`, общий `StageFiles` для всех code/repair stages. Проверяются типы, уникальность id в коллекциях и ссылки.
- `httpx` transport не делает скрытых retry. 429/5xx и transport errors помечаются transient; auth/прочие 4xx — non-transient. Retry/backoff и JSON correction остаются у `StepExecutor`.
- Usage берётся только из provider response; если поля отсутствуют, сохраняется `null`. `finish_reason=length` передаётся наверх как truncation.
- Реальный smoke test после заполнения ENV: `cd platform && PYTHONPATH=. python scripts/qwen_smoke.py`. Он печатает только безопасные метаданные, не API key и не полный ответ.
- Endpoint compatibility, latency и реальную доступность нельзя считать проверенными до smoke test с credentials организаторов.
