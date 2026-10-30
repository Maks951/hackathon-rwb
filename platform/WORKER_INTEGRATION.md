> Актуальный запуск и ограничения объединённой версии: [../docs/local-stack.md](../docs/local-stack.md).

# SQL-хранилище и worker: интеграционный пакет

Основа: database_backend `4d091d71c26a68ea227ce5178aa523e73d8de5a0`.
Переиспользованный backend Ярослава/Владимира: `b37c7026703417154845fd6e861357e043e47ba5`.
Пакет объединяет исходники этих снимков; это не Git merge commit. Перед общим PR согласовать с Ярославом изменения его ветки после этого SHA.

## Что подключено

- `app.integrations.sql_repository.SqlRunRepository` реализует все async методы существующего `app.ports.RunRepository`.
- Каждый вызов работает через `asyncio.to_thread`, создаёт собственную Session и завершает короткую транзакцию. Session не разделяется между heartbeat и pipeline.
- Существующие модели, миграции и данные Романа сохранены. Миграция `0006_worker_metadata` добавляет `steps.metadata_json` и `runs.package_path`.
- Worker Ярослава, pipeline и Qwen adapter взяты из backend. В worker добавлена совместимость запуска с Windows, в pipeline — регистрация исходников финального workspace вместе с ZIP. У Pipeline нет парковочных ветвлений.
- Метаданные LLM (modelId, promptVersion, usage, hashes) сохраняются немедленно; сырой ответ остаётся артефактом даже при невалидном JSON.
- Ошибки БД представлены безопасным AppError, ошибки этапов — ErrorDto. API не раскрывает DSN/SQL или ключ провайдера.
- Путь Artifact в БД относителен каталогу запуска; порт worker использует `<run UUID>/<path>`. Адаптер проверяет принадлежность, размер и SHA-256.
- Завершённый run не возобновляется. Stale recovery завершает и run, и его работающие steps; поздняя запись worker отклоняется. Lease fencing/exactly-once не реализованы, P0 — один worker.
- `/health` проверяет таблицы и новые колонки, но не доступность Qwen или runner.

## Установка на Windows

Из корня репозитория после применения patch:

```powershell
.\platform\.venv\Scripts\python.exe -m pip install -r .\platform\requirements-integration.lock.txt
.\platform\.venv\Scripts\python.exe .\platform\start_local.py
```

`start_local.py` применяет миграции и запускает `app.main:app` с SQL runtime factory.
Используется прежняя локальная DATABASE_URL, если переменная не задана; общую VM настроить явно.
Пути GENERATED_ROOT и RWB_GENERATED_ROOT согласованы и по умолчанию указывают на platform/generated. Для API и worker нужны одни DATABASE_URL и RWB_GENERATED_ROOT. Ранее созданные файлы сохраняются при использовании того же каталога.

API доступен на http://127.0.0.1:8000/docs. POST создания run теперь принимает тело `{}`. Старые ID проектов/запусков сохраняются.

## Подключение настоящего Qwen

Создайте локальный `platform/.env` (он игнорируется Git). Укажите точные значения организаторов:

```dotenv
QWEN_BASE_URL=<выданный base URL>
QWEN_MODEL=<выданный model ID>
QWEN_API_KEY=<выданный ключ>
QWEN_API_PATH=/chat/completions
```

Путь API подтвердить у организаторов. Секрет не отправлять в чат и не коммитить. Не заменять placeholders выдуманными рабочими URL.

Во втором терминале из корня:

```powershell
.\platform\.venv\Scripts\python.exe .\platform\start_worker.py
```

Worker без Qwen-настроек завершится с `not_ready`; это ожидаемый отказ запуска без обязательной зависимости. Он не создаёт искусственные ответы модели.

## Что ещё подключает команда

Фабрика `app.integrations.database_runtime:create_runtime` уже возвращает SQL repository, существующий Qwen adapter при заполненной конфигурации и artifacts router. В этой же фабрике Ярослав подключает реальный `validator` Дмитрия; optional publisher/deployer пока None.

Сейчас в снимке backend есть только dotnet-api template. Нужны реальные `templates/angular-admin`, `templates/angular-pwa`, `templates/postgres`. Отсутствие шаблона приводит к failed после сохранения предыдущих этапов, а не к фиктивному успеху. Если ранее применялся roman_product_db.patch, его templates/postgres содержит лишь старый пример: не использовать его как шаблон универсального генератора; согласовать замену с командой. SQL-шаблон для универсальной генерации должен быть недоменным и предусматривать `database/generated/`. Парковочный пример из отдельного patch в этот пакет не включён.

Без runner модельные этапы могут сохраняться, но validate завершится `not_ready` и ZIP успешного продукта не появится. Сгенерированный код на машине API/worker не выполняется. Не подключайте тестовые ScriptedValidator/ScriptedGeneration к фабрике.

Полная проверка команды:
1. API и worker запускаются с одной БД/диском и runtime factory.
2. В Swagger POST project, затем POST run с новым Idempotency-Key и телом `{}`.
3. Worker переводит queued в running; GET run и events показывают реальный ход.
4. В списке artifacts появляются input/output/raw call JSON и файлы финального workspace.
5. Только после настоящих зелёных проверок сохраняется package/product.zip, затем run становится succeeded.
6. Перезапуск API не меняет сохранённые результаты; остановка worker приводит к failed через stale recovery при следующем запуске worker.

## Проверка пакета

Из platform:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev-integration.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Интеграционные тесты используют настоящую SQLAlchemy/SQLite БД, worker/pipeline Ярослава и тестовые модель/runner. Они проверяют реальное сохранение между Sessions/engines, успешный полный прогон на тестовых ответах, сохранение raw ответа при ошибке JSON, stale recovery и запрет поздней записи, API/idempotency и отсутствие готового пакета до валидации. Это не smoke реального Qwen и не конкурентная проверка PostgreSQL.

Настоящие PostgreSQL-конкурентность, Qwen credentials/latency, сборка C#/Angular и deployment в этом окружении не проверены. Следующий этап с Дмитрием — такой прогон на отдельной тестовой БД/runner.

Результат проверки этого пакета: 89 тестов прошли на Python 3.12/Linux с SQLite; SQL миграций PostgreSQL сформирован без подключения. Windows/Python 3.11 и выполнение миграций на живом PostgreSQL этой версии пакета пока не проверены.
