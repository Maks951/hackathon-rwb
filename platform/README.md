# Первый этап Романа: projects

Python 3.12, sync SQLAlchemy 2 + psycopg 3, Alembic. Существующие папки команды сохранены; `platform/` следует общему контракту. `app/main.py` принадлежит Ярославу, здесь его нет. `project_demo.py` — только проверка router до интеграции.

## Запуск на Windows (PowerShell)

Из корня репозитория:

```powershell
cd platform
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock.txt
```

В pgAdmin подключись к своему PostgreSQL, открой Query Tool базы `postgres` и выполни отдельно (однократно):

```sql
CREATE ROLE platform LOGIN PASSWORD 'platform_local';
```

```sql
CREATE DATABASE platform OWNER platform;
```

Пароль выше только для локальной разработки. Для общей VM используй отдельный пароль. БД генерируемого продукта создаётся отдельно; её роль не получает доступ к этой БД.

В том же PowerShell:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://platform:platform_local@localhost:5432/platform"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.project_demo:app --reload
```

`.env.example` — образец, приложение не загружает `.env` автоматически. Ожидается таблица `projects` и Swagger по http://127.0.0.1:8000/docs. UUID создаёт Python; PostgreSQL задаёт время, API возвращает UTC `createdAt`.

В Swagger вызови `POST /api/v1/projects`:

```json
{"name":"Каталог","requirements":"Нужен каталог товаров с названием, ценой и остатком"}
```

Ожидается 201, затем `GET /api/v1/projects` возвращает `{ "items": [...] }`. Перезапусти сервер — проект должен остаться. `GET /api/v1/projects/{id}` возвращает проект или 404. Невалидный UUID/длина поля — 400 в demo-приложении. name: 1–120, requirements: 20–50000; эти ограничения есть и в PostgreSQL.

## Передача Ярославу

В существующем composition root подключить:

```python
from app.api.projects import router as projects_router
app.include_router(projects_router)
```

`get_session()` даёт новую Session на запрос и закрывает её. Обработчики sync (`def`). В фоновых потоках создавать свои Sessions через `get_session_factory()()`; не передавать Session из HTTP-запроса. `create_project(session, *, name, requirements)` владеет транзакцией и commit/rollback; передавать свежую Session без уже начатой транзакции. `get_project(session, project_id)` и `list_projects(session)` читают данные. DTO — `app/schemas/projects.py`. Общие обработчики ошибок `RequestValidationError → 400` и `HTTPException → {code,message}` показаны в `project_demo.py`; их надо перенести/согласовать с центральными обработчиками Ярослава. Без них FastAPI по умолчанию возвращает 422 и обёртку detail.

## Проверка для Романа и Дмитрия

Из `platform/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Без TEST_DATABASE_URL тесты используют временную SQLite: API, сохранение между Sessions, ограничения, rollback всей транзакции, повтор upgrade и downgrade. Это не проверка реального PostgreSQL.

Для проверки PostgreSQL сначала создай **отдельную пустую тестовую БД** `platform_test`, владельцем назначь роль `platform`, затем:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://platform:platform_local@localhost:5432/platform_test"
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
```

Тесты удаляют таблицу projects через downgrade: никогда не указывай рабочую БД в TEST_DATABASE_URL.

SQL миграции без подключения:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

`alembic downgrade base` удаляет projects с данными; для обычного запуска нужен только `upgrade head`. Не используется `Base.metadata.create_all()` при старте сервера. `requirements-dev.lock.txt` фиксирует зависимости проверенного Linux/Python 3.12 окружения; установку на Windows ещё нужно подтвердить.

Следующий этап — runs и единый контракт очереди с Ярославом; в этом изменении runs/worker/artifacts ещё не реализованы.
