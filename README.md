# Hackathon RWB

Python API/worker участка Ярослава: [platform/README.md](platform/README.md).
Исходное распределение ролей — в командном `03_Yaroslav_Python_Pipeline.md`.

- `platform/` — runs API, worker, orchestration, безопасное дерево файлов и ZIP.
- `templates/dotnet-api/` — C# 14 / .NET 10 backend skeleton для продукта.
- `contracts/runs.ts`, `contracts/platform-openapi.json` — выходной API-контракт для UI/тимлида.
- `docs/integration.md` — точки подключения компонентов коллег.
- `docs/yaroslav-handoff.md` — сделанное, результаты проверок и оставшиеся зависимости.
- `compose.backend.yaml`, `platform/Dockerfile` — адаптация Docker-шаблона команды,
  PostgreSQL платформы и API. Запуск: [docs/docker-integration.md](docs/docker-integration.md).
- `platform/app/resources/documentation-policy.json` — новые регламенты СА/API/ADR
  организаторов, передаваемые генератору и проверяемые перед package.
- `hackathon-rwb-angular/`, `hackthon-rwb-db/` — существующие каталоги команды.

Projects Романа подключены, работают с настоящей БД. Полный pipeline подключается
через RunRepository/Qwen/runner adapters команды;
до интеграции внешних модулей нельзя считать весь продукт готовым.
