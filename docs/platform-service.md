# Сервис Python API / worker

## Описание

Python 3.12, FastAPI/Pydantic 2. API проектов использует модуль Романа:
sync SQLAlchemy 2 + psycopg 3, Alembic, PostgreSQL платформы. Runs API и отдельный
worker управляют pipeline; generated product использует независимый C# backend.

## Ссылки

Локальный Swagger: http://127.0.0.1:8000/docs; контракт —
`../contracts/platform-openapi.json`, методы — `platform-api.md`.
Prod/Stage URL не назначены; рабочий preview пока не заявляется.

## Требования к ресурсам

Python 3.12 и PostgreSQL, диск под generated (до 24 MiB файлов продукта на попытку
по текущим лимитам плюс LLM inputs/outputs и отчёты). Измеренных RAM/CPU/IO лимитов
ещё нет; не подставляются цифры из примеров регламента. Ограничения runner задаёт Дмитрий.

## Отказоустойчивость

P0: один worker. DB commit на создание проекта; RunRepository должен атомарно
забирать queued run. Heartbeat и stale recovery предусмотрены контрактом,
автоматического resume нет. При рестарте API данные проектов остаются в PostgreSQL.
Репликация и подтверждённый RTO/RPO не реализованы.

## Предельные ограничения работы сервиса

Название проекта 1–120 символов, requirements 20–50000. Один активный run/project
должен обеспечиваться DB repository. Файлы продукта: до 500, до 1 MiB каждый,
дерево до 24 MiB; LLM response до 8 MiB. Нагрузочная пропускная способность не измерена.

## Работа сервиса

HTTP возвращает созданный run без ожидания Qwen. Отдельный worker получает run
из repository и сохраняет шаги. Подключены projects, SQL RunRepository и Qwen factory. Qwen требует ENV;
validator пока отсутствует. Успешная полная генерация не подтверждена.

## Авторизация

P0 — закрытая командная demo, без публичной регистрации и multi-tenancy.
Встроенного JWT/RBAC сейчас нет. Доступ ограничивается окружением; реальный
auth нельзя заявлять выполненным. API/worker не получают Docker socket.

## Описание окружений

Test: временные SQLite в Python-тестах; контейнерный PostgreSQL для интеграционной
проверки, если она отмечена успешной в handoff. Local: Compose из docker-integration.md.
Stage/Prod: адреса и процедуры пока не предоставлены, не считаются развёрнутыми.

## Сборка

`platform/Dockerfile`, root context. requirements.txt экспортирован из uv.lock
с hashes, pip require-hashes; запуск от UID 10001. Исходный Docker-шаблон Дмитрия
сохранён в истории ветки. Генерируемый код в этом образе не собирается/не исполняется.

## Деплой

Локальная платформа: database healthy → migrate completed → api.
Worker — отдельный профиль pipeline. Deployment generated product — adapter Дмитрия;
реального cloud/prod deployment здесь нет. Инструкция: docker-integration.md.

## Конфигурация

`DATABASE_URL` — PostgreSQL SQLAlchemy URL, `RWB_RUNTIME_FACTORY` — реальная
factory для runs/Qwen/runner, `RWB_GENERATED_ROOT`/`RWB_TEMPLATES_ROOT` — каталоги,
`RWB_CORS_ORIGINS` — JSON origins. Остальные лимиты — `app/config.py`.
Секреты только в ENV/.env вне Git. Не выводить URL с credentials в ошибки/логи.

## Переменные окружения для CI/CD

CI команды пока у Дмитрия. Требуются секреты окружения БД и адаптеров;
Qwen key не передаётся продукту, GitLab token остаётся у publisher.
Конкретные имена Qwen/publisher ENV согласуются с владельцами, не придуманы здесь.

## Мониторинг

`/health`: 200 при доступности repository/таблицы projects, иначе 503.
Это readiness API, а не признак готовности всего pipeline. Worker пишет безопасные
ошибки и heartbeat через repository. Zabbix/Prometheus здесь не подключены.

## Логирование

STDOUT/STDERR контейнеров, названия классов ошибок и безопасные codes.
Raw provider body не логируется. Сбор в Elasticsearch/Kibana требует инфраструктуры
коллег; наличие такой системы из корпоративного примера не заявляется.

## Сетевая связность

API опубликован на localhost:8000; БД внутри Compose network без host port.
Qwen доступен из VM организаторов согласно уточнению 30.10 16:17.
Сеть изолированного generated-code runner настраивается отдельно.

## Доступы к сервису

Команда demo через локальный порт/согласованный доступ VM. Нет утверждённых
корпоративных подсетей, ролей доступа или процедур удалённой эксплуатации.
