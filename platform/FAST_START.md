# Пакет артефактов — запуск и передача команде

Основа patch: database_backend d453e3f. Существующий локальный repositories/steps.py не меняется.

Из корня репозитория, после применения patch:

```powershell
.\platform\.venv\Scripts\python.exe .\platform\start_local.py
```

Скрипт применяет миграции и запускает локальный demo API. Если DATABASE_URL не задана, используется прежняя локальная БД platform с ролью platform и паролем platform_local. Для VM задайте собственную DATABASE_URL. В production скрипт не используется. GENERATED_ROOT — абсолютный путь к диску с результатами; по умолчанию platform/generated. На общей VM настройте постоянный volume, одинаковый для API и worker.

## Быстрая проверка на Windows

В другом терминале из platform:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://platform:platform_local@localhost:5432/platform"
.\.venv\Scripts\python.exe check_artifacts.py
```

Введите существующий ID запуска. Скрипт создаст storage-check.txt с явной пометкой проверки и ZIP; это проверка хранилища, а не генерация Qwen. Затем в Swagger:

- GET /api/v1/runs/{run_id}/artifacts — два артефакта, исходный файл и ZIP.
- GET /api/v1/artifacts/{artifact_id}/content — текст файла storage-check.txt.
- GET /api/v1/runs/{run_id}/download — готовый ZIP.
- GET /api/v1/runs/{run_id} — теперь также steps, validationStatus и deploymentStatus.

До вызова package_run скачивание возвращает 409. Создание пакета не меняет run на succeeded и не означает, что код собран или развёрнут.

## Для Ярослава

В центральный FastAPI app подключить app.api.artifacts.router; существующий runs router содержит RunDetails. Перенести общий формат ошибок из project_demo.py либо сохранить совместимые собственные обработчики.

Новые функции app.repositories.artifacts:

```python
register_artifact(session, *, run_id, path, mime_type="text/plain", step_id=None)
list_artifacts(session, run_id)
package_run(session, *, run_id)
artifact_path(run_id, relative)
```

Каждый изменяющий вызов получает свежую Session. Используется существующая фабрика app.db.get_session_factory(), expire_on_commit=False. Не передавайте Session между потоками.

Порядок worker:
1. claim_next_run с отдельной Session; транзакция завершена до Qwen.
2. Выполнить шаг. Во время долгого запроса поддерживать heartbeat в другом потоке со своей Session.
3. Файлы писать через temp -> rename внутри GENERATED_ROOT/<run UUID>/<относительный путь>.
4. register_artifact после rename; размер и SHA-256 вычисляются по файлу. step_id проверяется на принадлежность запуску.
5. save_step и append_event вызываются отдельно, после записи результата. Сигнатура save_step — в локальном файле Романа; этот patch её не меняет.
6. Когда все записи файлов завершены и проверки пройдены, package_run; затем worker завершает run. Не паковать параллельно с записью файлов.

API/worker не выполняют содержимое файлов. Только UTF-8 просмотр, JSON или text/plain, лимит 1 MiB. Относительные пути, запрет обхода каталогов и symlink. ZIP создаётся только из зарегистрированных файлов с проверенным хешем. Один файл ограничен 50 MiB; сумма исходных файлов ZIP — 200 MiB. ZIP читается в память: для больших результатов нужен streaming. _package/result.zip зарезервирован для package_run.

Атомарность диска и БД общая не обеспечивается: при сбое между rename и commit возможен orphan. Удалять его только после сверки с metadata и остановки записей для соответствующего run. Отдельного автоматического cleanup в этом пакете нет.

## Проверки

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

По умолчанию SQLite; для реального PostgreSQL используйте отдельную одноразовую TEST_DATABASE_URL, как описано в README. Тесты удаляют таблицы через downgrade. На рабочую БД их не направлять.

Ещё не закрыто: реальный runner/Qwen, интеграция worker, конкурентные проверки PostgreSQL, orphan cleanup, продуктовая БД/PostGIS, backup. Код не утверждает выполнение этих пунктов.
