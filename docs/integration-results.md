# Результат интеграции — 31.10.2026

База cbc6b57, объединена ветка integration/roman-worker 84e775e в отдельной
integration/complete-stack. Remote не изменен. Исходная рабочая папка была пустой.
Конфликты разрешены с сохранением hash-pinned зависимостей и исправлений Qwen
из local-stack, SQL-моделей, миграций и адаптера worker из roman-worker.

## Изменения

SQL models/migrations/repositories и factory объединены с frontend и Qwen.
В compose.backend.yaml явная factory и host-gateway; compose.yaml добавляет web
с nginx proxy /api/. Новые Dockerfile/nginx.conf находятся в apps/hackathon-rwb-angular.
Завершение worker закрывает SQL engine. Экспорт OpenAPI включает artifacts routes.
SqlRunRepository не выдает legacy ZIP без validation passed и package_path;
добавлена регрессионная проверка, legacy storage test проверяет ZIP отдельно от API.
Angular admin имеет main/index и import generatedRoutes из разрешенного каталога.
Добавлен PWA template с service-worker/manifest и PostgreSQL/PostGIS template.
Prompts требуют routes.ts для admin и PWA, версии Angular берутся из lockfile.
Документы platform-spec, flow, compliance и local-stack дополняют существующие
описания; приложены оригинальные PDF и рабочие PDF. Выполнено форматирование
объединенного Python-кода; исправлены lint errors, без отключения правил.

## Выполненные проверки

- Python: 118 passed (28 dependency deprecation warnings).
- Ruff check: all checks passed; 59 файлов соответствуют format.
- UI: production build прошел; 4 test files, 12 tests passed.
- Angular admin template: production build во временной копии с пустым тестовым
  generatedRoutes прошел. Это проверка host, не работа доменной генерации.
- Alembic: одна head 0006_worker_metadata; offline PostgreSQL SQL сгенерирован.
- SQLite: реальные миграции и SQL persistence в integration tests; Qwen/runner заменены.
- Compose: YAML распарсен; docker compose config/build/up не запускались (нет Docker).
- Пять исходных PDF совпадают SHA256 с documentation-policy.json.
- Пять созданных PDF отрендерены и просмотрены.
- Qwen smoke: qwen_not_configured до сетевого запроса.

## Не подтверждено

Нет ID реального успешного run; отсутствуют credentials Qwen, Docker, сервер
PostgreSQL, .NET SDK и реализация ValidationRunner. Поэтому не проверены реальные
SKIP LOCKED/concurrent claims, рестарт контейнеров, живой вызов модели, сборка и
запуск C# продукта, полный браузерный сценарий и скачивание реального итогового ZIP.
Нужен изолированный runner с backend_build/backend_tests/admin_build/pwa_build,
api_contract/security. Documentation check добавляет pipeline. Нельзя считать
одни тестовые doubles или наличие ZIP доказательством этих проверок.

Точные команды запуска и проверки: local-stack.md. Работа не завершена до
реального сквозного прогона на окружении команды и подключения runner.
