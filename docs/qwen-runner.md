# Qwen + изолированный ValidationRunner

31.10.2026. База f18ca91; ветка integration/qwen-runner. Изменений в remote нет.
Проверены все remote branches; новых коммитов относительно предыдущей работы не найдено.

## Что реализовано

Qwen: опциональное QWEN_ALLOW_VM_HTTP=true разрешает HTTP только к
10.10.10.10:4000/v1. Адреса с credentials, другим портом/путём и двойным /v1
отклоняются. Windows использует SSH tunnel → host.docker.internal:4000;
QWEN_ALLOW_DOCKER_HOST_HTTP=true требуется только для этого доверенного HTTP-доступа.
Сохранены schema prompts, JSON normalization и обработка provider errors.

HttpValidationRunner подключается factory при наличии RWB_RUNNER_URL.
Worker отправляет workspaceId, manifest, SHA256 manifest и base64 файлов.
Брокер проверяет токен, предел размера, пути, размеры и SHA256 перед запуском Docker.
HTTP response ограничен 64 KiB; другой manifest, отсутствующие/повторные checks,
не-bool passed и слишком длинная диагностика отклоняются.

Брокер runner имеет Docker socket и является доверенным инфраструктурным компонентом.
Он не получает platform/.env, Qwen key, пароль БД или SSH credentials. Порт наружу
не публикуется. Socket НЕ передается worker/API или контейнеру с кодом модели.
RWB_RUNNER_TOKEN — отдельный случайный секрет 32+ символа.
Один запрос выполняется одновременно. Прочие получают 503, а не фиктивный успех.

Sandbox запускается одноразово: network=none, root filesystem read-only, uid=10001,
cap-drop=ALL, no-new-privileges, 256 PID, 2 CPU, 2 GiB RAM, ограниченные tmpfs.
Нет host mounts и секретных ENV. Зависимости скачиваются при сборке trusted image,
по зафиксированным lockfiles. npm lifecycle scripts отключены. Generated tree передается
через stdin; исходный immutable workspace не меняется. Команды фиксированы в коде.
Брокер удаляет только созданный им sandbox с уникальным именем после выполнения/timeout.

## Checks и их пределы

- backend_build: offline locked restore + настоящая .NET Release build.
- backend_tests: dotnet test + TRX, минимум четыре успешных теста (три baseline и
  минимум один дополнительный), требуется generated C# test file.
- admin_build / pwa_build: настоящая Angular build с подготовленными зависимостями.
- api_contract: дополнительный trusted xUnit test поднимает WebApplicationFactory,
  читает реальные RouteEndpoint/HttpMethodMetadata и сравнивает набор method/path
  с generated-api.json. Это проверка маршрутов, НЕ схем тел и бизнес-семантики.
- security: сверка всех неизменяемых шаблонов, допустимых путей, поиск private-key/API-key
  литералов и ряда опасных execution/environment primitives. Это ограниченная проверка,
  НЕ полный SAST, аудит зависимостей или доказательство отсутствия уязвимостей.
- documentation добавляет существующий pipeline, брокер его не переопределяет.

Невозможность запустить проверку, timeout, ошибка команды, пустой TRX/отчет или ошибка
целостности дают failed. После repair вызывается тот же runner заново для новой попытки.
Набор checks не подтверждает работоспособность SQL-схемы и бизнес-сценария продукта:
это отдельная приемка после извлечения ZIP и запуска product Compose.

## Windows — один сценарий

После импорта новой ветки, из корня репозитория:

```powershell
powershell -NoProfile -File .\scripts\verify-stack.ps1
```

Сценарий сохраняет существующий .env, задает адрес туннеля и настройки runner,
генерирует отдельный runner token. Если API-key уже заполнен, использует его;
иначе просит скрытый ввод. Пароль SSH запрашивает штатный клиент в другом окне.
При первом SSH-подключении сверить fingerprint VM с командой/организаторами.
Не отключать host-key verification. Туннель оставлять запущенным:

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -p 10021 -L 127.0.0.1:4000:10.10.10.10:4000 team21@85.143.113.230
```

Скрипт последовательно выполняет image build, platform startup, настоящий PostgreSQL
smoke в отдельной схеме, реальный Qwen smoke, запуск worker/runner и API generation smoke.
При первой ошибке останавливается. Он не останавливает существующие данные/volumes.
PostgreSQL smoke сохраняет новую rwb_verify_* схему для диагностики, не изменяет таблицы
основного приложения. Его runId НЕ является ID генерации.

Успешный integration_smoke печатает настоящий runId и путь ZIP; PowerShell копирует
и распаковывает ZIP в verification/<runId>. Эта директория исключена из Git.
Дальше в извлеченном продукте создать .env с новым PRODUCT_DB_PASSWORD, выполнить:

```powershell
docker compose -p rwb-product-demo up --build -d
```

Admin: localhost:4300, PWA: localhost:4301. Порты должны быть свободны.
Создать заявку, обновить статус, обновить страницу, перезапустить product services,
убедиться, что заявка сохранилась. Результаты этого шага фиксировать отдельно.

## VM — из отдельного каталога команды

На VM использовать штатный Docker/Compose. Сначала проверить свободные порты
8000/4200 и ресурсы; при занятости выбрать другие bindings в локальном override.
Создать platform/.env из примера, заполнить Qwen key без включения в Git:
QWEN_BASE_URL=http://10.10.10.10:4000/v1, QWEN_MODEL=qwen3.8-27b,
QWEN_API_PATH=/chat/completions, QWEN_ALLOW_VM_HTTP=true,
QWEN_ALLOW_DOCKER_HOST_HTTP=false, отдельный RWB_RUNNER_TOKEN и run timeout 2400.

```bash
docker build -f infra/runner/Dockerfile.sandbox -t localhost/rwb-sandbox:dev .
docker compose -p rwb-validation --env-file platform/.env up --build -d --wait api web
docker compose -p rwb-validation --env-file platform/.env exec -T api python -m scripts.postgres_smoke
docker compose -p rwb-validation --env-file platform/.env run --rm --no-deps api python -m scripts.qwen_smoke
docker compose -p rwb-validation --env-file platform/.env --profile pipeline up --build -d --wait
docker compose -p rwb-validation --env-file platform/.env exec -T api python -m scripts.integration_smoke
```

Compose project rwb-validation создает собственные volumes. Не подключать его к БД
команды. На общей VM имя sandbox image согласовать при параллельных сборках.

## Фактически проверено в этой сессии

TCP к 85.143.113.230:10021: OSError [Errno 101] Network is unreachable до авторизации.
Пароль/ключ не использовались и не были записаны в файлы. Здесь нет Docker/.NET.
Python: 128 тестов прошли, Ruff check прошёл, 68 файлов соответствуют форматированию.
Compose YAML разобран; config/build/up Docker здесь не запускались.
Python unit/integration tests выполнялись; реальные SQL tests используют SQLite,
а Qwen HTTP и Docker execution в соответствующих unit tests подменены явно.
Контейнерные образы runner, реальный Qwen, PostgreSQL concurrency и бизнес-сценарий
продукта здесь НЕ запускались. Реального успешного generation runId пока нет.
Проверки пользователя предыдущей версии (Docker/API/UI/DB restart) сохраняют силу
только для той версии; новый runner требует прогона выше.
