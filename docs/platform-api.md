# API платформы

## Общая информация

Markdown-адаптация «Шаблон API_обезл.pdf». Документ описывает фактические маршруты
production composition root; пункты с отсутствующим RunRepository отмечены явно.
Source of truth для полей, required/null, UUID, enum и DTO: [OpenAPI](../contracts/platform-openapi.json)
и [TypeScript](../contracts/runs.ts). Swagger локально: http://127.0.0.1:8000/docs.
Транспорт local demo: HTTP/1.1, без TLS на localhost; TLS/proxy для внешней VM отдельно.

## История изменений документа

| Дата | Версия | Изменение | Ответственный |
| --- | --- | --- | --- |
| 30.10.2026 | 0.2 | Projects Романа подключены к runs composition; новые API/service templates | Ярослав |

## Общие правила авторизации и ошибок

Все методы доступны только команде в закрытом demo. JWT/RBAC не реализованы;
наличие корпоративной авторизации не заявляется. Content-Type JSON для JSON body.
Успешные JSON-ответы используют camelCase. Даты — строки UTC ISO 8601.
`repositoryUrl`, `previewUrl`, `currentStep`, `error`, `finishedAt` nullable по DTO.
Ошибки вне /health: `{code:string,message:string,details?:object|null}`; SQL,
Qwen response, ключи и connection strings не отражаются. Неожиданная ошибка —
500 internal_error. Пример ошибки: `{"code":"not_found","message":"Project not found","details":null}`.
UUID ниже иллюстративны, не являются идентификаторами существующих записей.
Projects сохраняются реально; runs требуют реализации RunRepository.

## POST /api/v1/projects

### Основная информация

Создание проекта. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

JSON {name: string 1–120, requirements: string 20–50000}; Content-Type: application/json. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
POST /api/v1/projects
Content-Type: application/json

{"name":"Заявки","requirements":"Учет заявок сотрудников с изменением статусов"}
```

### Исходящие параметры

Успех: 201 ProjectRead {id,name,requirements,createdAt}. Полные модели/required/enum — OpenAPI.
Ошибки: 400 invalid_input; 503 not_ready/database_unavailable. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

projects: INSERT, id генерируется UUID4, created_at задаёт PostgreSQL.

### Описание алгоритма работы метода

Валидировать DTO → новая Session → repository Романа в begin/commit → вернуть сохранённый проект. Ошибка SQL → rollback и безопасный 503.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.

## GET /api/v1/projects

### Основная информация

Список проектов. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

Нет body/path/query. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
GET /api/v1/projects
```

### Исходящие параметры

Успех: 200 {items: ProjectRead[]}; пустой список — items: []. Полные модели/required/enum — OpenAPI.
Ошибки: 503 not_ready/database_unavailable. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

projects: SELECT с сортировкой created_at, id.

### Описание алгоритма работы метода

Открыть Session → запрос repository → сериализация UTC createdAt → закрыть Session. Пагинация в текущем модуле не реализована.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.

## GET /api/v1/projects/{project_id}

### Основная информация

Просмотр проекта. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

Path project_id: UUID, обязательно. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
GET /api/v1/projects/00000000-0000-0000-0000-000000000001
```

### Исходящие параметры

Успех: 200 ProjectRead. Полные модели/required/enum — OpenAPI.
Ошибки: 400 invalid_input при невалидном UUID; 404 not_found; 503 БД. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

projects: SELECT по primary key.

### Описание алгоритма работы метода

Валидировать UUID → Session → repository.get_project → объект либо 404. Не отражать SQL/credentials в ошибке.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.

## POST /api/v1/projects/{project_id}/runs

### Основная информация

Создание/идемпотентное получение run. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

Path project_id: UUID; обязательный header Idempotency-Key: UUID; JSON {} без overrides. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
POST /api/v1/projects/00000000-0000-0000-0000-000000000001/runs
Content-Type: application/json
Idempotency-Key: 00000000-0000-0000-0000-000000000002

{}
```

### Исходящие параметры

Успех: 202 RunDto; Location: /api/v1/runs/{id}. Повтор ключа/проекта возвращает тот же run. Полные модели/required/enum — OpenAPI.
Ошибки: 400 invalid_input; 404 project missing; 409 active_run/idempotency_conflict; 503 если RunRepository не подключён. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

projects/runs/run_events: атомарный snapshot/idempotency/unique active run — контракт repository Романа, реализация ещё ожидается.

### Описание алгоритма работы метода

Делегировать create_run repository → получить durable queued/существующий run → 202. Ни LLM, ни сборка не выполняются в HTTP. В текущей сборке вернётся 503 до подключения RunRepository.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.

## GET /api/v1/runs/{run_id}

### Основная информация

Статус и шаги run. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

Path run_id: UUID, обязательно. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
GET /api/v1/runs/00000000-0000-0000-0000-000000000003
```

### Исходящие параметры

Успех: 200 RunDetailsDto: RunDto + steps, validationStatus, deploymentStatus. Полные модели/required/enum — OpenAPI.
Ошибки: 400 invalid_input; 404 not_found; 503 RunRepository not ready. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

runs, steps: чтение через repository.

### Описание алгоритма работы метода

Проверить существование run → получить steps → исключить snapshot/internal metadata из публичного DTO → вернуть фактические статусы.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.

## GET /api/v1/runs/{run_id}/events

### Основная информация

События для polling UI. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

Path run_id: UUID; query afterSequence: integer >=0, default 0; body нет. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
GET /api/v1/runs/00000000-0000-0000-0000-000000000003/events?afterSequence=0
```

### Исходящие параметры

Успех: 200 {items: EventDto[],nextSequence: number}; до RWB_MAX_EVENTS (default 200). Полные модели/required/enum — OpenAPI.
Ошибки: 400 invalid_input; 404 not_found; 503 repository not ready. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

runs для existence, run_events: sequence > afterSequence в возрастающем порядке.

### Описание алгоритма работы метода

Прочитать страницу событий → nextSequence = последняя sequence или входной cursor для пустой страницы. Клиент poll раз в 2 секунды, останавливает на terminal run.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.

## GET /api/v1/runs/{run_id}/download

### Основная информация

Скачивание проверенного пакета. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

Path run_id: UUID; body нет. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
GET /api/v1/runs/00000000-0000-0000-0000-000000000003/download
```

### Исходящие параметры

Успех: 200 application/zip; Content-Disposition: attachment, имя {run_id}.zip; Cache-Control: no-store, nosniff. Полные модели/required/enum — OpenAPI.
Ошибки: 400 invalid_input; 404 not_found; 409 package_not_ready; 503 repository/artifact unavailable or corrupt. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

runs/artifacts/package metadata через repository; сами bytes на диске generated.

### Описание алгоритма работы метода

Найти зарегистрированный package → проверить безопасный относительный путь, размер и SHA256 → FileResponse. До успешного package download недоступен.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.

## GET /health

### Основная информация

Готовность API/БД. Контракт DTO/Swagger — по ссылкам выше.

### История изменений

Версия 0.2, 30.10.2026: объединённый API. Для projects использован модуль Романа
`18100ec`; для runs — модуль Ярослава. JIRA/внешнее согласование не предоставлены.

### Входящие параметры

Нет входных параметров. Авторизация и разрешённый круг вызова — общие правила выше.

Пример запроса:

```http
GET /health
```

### Исходящие параметры

Успех: 200 {status:"ok"}. Полные модели/required/enum — OpenAPI.
Ошибки: 503 {status:"not_ready"}; это HealthDto, не ErrorDto. Остальные исключения — общий безопасный ErrorDto.

### Взаимодействие с таблицами

projects: SELECT id LIMIT 1 до runs integration; затем RunRepository.ping.

### Описание алгоритма работы метода

Без подключённого repository проверить доступность таблицы projects с отдельной Session. Ошибки БД/отсутствие миграции дают 503; heartbeat/Qwen/build readiness этим не подтверждаются.

### Взаимодействие с внешними компонентами

Прямых Qwen/runner/publisher вызовов в этом HTTP method нет. Используется repository/БД
или хранилище файлов; длительная обработка вынесена в worker. Кэш и rate limiting
в текущей закрытой demo не реализованы. Таймаут подключения PostgreSQL — 3 секунды по умолчанию.
