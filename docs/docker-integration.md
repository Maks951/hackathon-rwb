# Docker-шаблон: интеграция с платформой

Источник: ветка `Docker`, коммит `b8ca420`, архив `docker-fastapi-template.zip`.
История ветки влита в backend. Оригинальный архив сохранён; рабочая адаптация —
`platform/Dockerfile`, корневая `.dockerignore`, `compose.backend.yaml`.

Шаблон был рассчитан на `hackathon-rwb-back/requirements.txt`; наш рабочий backend
расположен в `platform/`. Build context — корень репозитория: образу нужны код,
шаблоны продукта и документационная политика. Фактические зависимости экспортированы
из `platform/uv.lock` в requirements.txt с hashes; pip проверяет их через require-hashes.
Python 3.12, UID/GID 10001, локальный порт 127.0.0.1:8000; Docker socket не подключён.

## Запуск из корня репозитория

```bash
cp platform/.env.example platform/.env
# В platform/.env задать свой POSTGRES_PASSWORD для общей VM.
docker compose --env-file platform/.env -f compose.backend.yaml config --quiet
docker compose --env-file platform/.env -f compose.backend.yaml up --build -d
docker compose --env-file platform/.env -f compose.backend.yaml logs --tail 100 api migrate
```

В PowerShell вместо `cp` можно использовать `Copy-Item`. `.env` не коммитится
и не попадает в образ. Compose передаёт ENV явно, а DATABASE_URL внутри контейнеров
использует hostname `database`, независимо от localhost в примере локальной конфигурации.
Для пароля в URL нужны URL-safe символы либо корректное percent encoding.

Последовательность: PostgreSQL ready → Alembic upgrade head → API. Взята существующая
миграция Романа; новых migrations здесь нет. `/health` проверяет доступность таблицы
projects (или реального runs repository после его подключения), не только факт запуска Python.
Данные PostgreSQL и generated сохраняются в двух named volumes.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"Заявки","requirements":"Учет заявок сотрудников и изменение их статусов"}'
curl http://127.0.0.1:8000/api/v1/projects
```

Ожидается health 200 после миграции, создание проекта 201, чтение сохранённого
проекта. Создание run остаётся 503 до настоящего RunRepository, без очереди в памяти.
Health=200 означает готовность API проектов/БД, а не готовность всех стадий генерации.

## Worker и оставшиеся подключения

Worker использует тот же образ и generated volume, запускается отдельным процессом.
До готовности реального RunRepository/Qwen он включается только явно, профилем pipeline:

```bash
# Сначала подключить действительную фабрику в RWB_RUNTIME_FACTORY и ENV её компонентов.
docker compose --env-file platform/.env -f compose.backend.yaml --profile pipeline up -d worker
```

Не подставлять название несуществующей factory в `.env` ради запуска: оно приведёт
к ошибке импорта. Publisher/isolated runner и generated product deployment здесь
не создаются и не считаются проверенными. Это запуск платформы, не runner продукта.

## Остановка

```bash
docker compose --env-file platform/.env -f compose.backend.yaml down
```

Команда оставляет named volumes. Данные не удаляются при обычной остановке.
Python image закреплён по проверенному digest в Dockerfile.
PostgreSQL указан 17.9 по условиям кейса.

В Linux возможен rootless Podman с совместимым Compose provider. Реальные
результаты проверки указаны в `yaroslav-handoff.md`.

Семантика конфигурации: [startup order](https://docs.docker.com/compose/how-tos/startup-order/),
[ENV/interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/),
[profiles](https://docs.docker.com/compose/how-tos/profiles/).
