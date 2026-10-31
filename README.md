# Hackathon RWB

Объединенная версия: [запуск и ограничения](docs/local-stack.md).
Локальная интеграция frontend, SQL API/worker и Qwen adapter; полный сценарий
генерации пока не подтвержден. ValidationRunner реализован в ветке integration/qwen-runner; контейнерный прогон ещё не подтверждён.
Текущая инструкция: [Qwen и runner](docs/qwen-runner.md).

- `apps/hackathon-rwb-angular/`: интерфейс платформы.
- `platform/`: API, очередь PostgreSQL, worker, Qwen и storage.
- `templates/`: .NET backend, Angular admin/PWA, PostgreSQL продукта.
- `compose.yaml`: общий запуск, `compose.backend.yaml`: backend services.
- `contracts/`: экспортированный API-контракт.
- `docs/source-pdfs/`: пять исходных регламентов.
- `docs/pdf/`: рабочие ТЗ, API, сервисы, ADR и проверка соответствия.

```bash
cp platform/.env.example platform/.env
docker compose --env-file platform/.env up --build -d
```

Перед worker настроить Qwen. Команды, зависимости и реальные результаты проверок:
[docs/local-stack.md](docs/local-stack.md), [docs/integration-results.md](docs/integration-results.md).
