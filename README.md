# Hackathon RWB

Python API/worker участка Ярослава: [platform/README.md](platform/README.md).
Исходное распределение ролей — в командном `03_Yaroslav_Python_Pipeline.md`.

- `platform/` — runs API, worker, orchestration, безопасное дерево файлов и ZIP.
- `templates/dotnet-api/` — C# 14 / .NET 10 backend skeleton для продукта.
- `contracts/runs.ts`, `contracts/platform-openapi.json` — выходной API-контракт для UI/тимлида.
- `docs/integration.md` — точки подключения компонентов коллег.
- `docs/yaroslav-handoff.md` — сделанное, результаты проверок и оставшиеся зависимости.
- `hackathon-rwb-angular/`, `hackthon-rwb-db/` — существующие каталоги команды.

Реальный pipeline подключается через repository/Qwen/runner adapters команды;
до интеграции внешних модулей нельзя считать весь продукт готовым.
