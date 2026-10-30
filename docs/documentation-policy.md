# Документация по новым материалам организаторов

Версия `russtech-sa-2026-10-30`, source of truth:
`platform/app/resources/documentation-policy.json`. Там записаны имена и SHA256
пяти исходных PDF: правила СА и шаблоны ТЗ, API, сервисов и ADR. Сами PDF с
корпоративными примерами не копируются в продукт как будто это его документация.

В нашем участке реализовано подключение правил и проверка структуры; prompts,
RequirementsSpec/SystemSpec и генерация содержимого остаются у Владимира.
Policy — дополнительный сохранённый input, публичные RunDto/RunDetailsDto не менялись.

1. Перед analyze сохраняется immutable documentation-policy.json с SHA256.
2. Все LLM stages получают одинаковые `documentationPolicy` и `documentationPolicySha256`.
3. Генератор должен создать `docs/system-analysis.md`, `api.md`, `services.md`,
   `adr.md`, `user-guide.md`, `runbook.md` в согласованной структуре разделов.
4. В validation наша check `documentation` проверяет наличие файлов, непустые
   разделы, FR-идентификаторы и отдельное описание каждого endpoint из единого
   SystemSpec. Заголовки в code fences/HTML comments не засчитываются.
5. Failed check передаётся repair; обязательные проверки runner выполняются заново.
6. ZIP содержит сохранённую policy и фактический `reports/validation.json` с checks,
   source manifest и policy hash. Модель не пишет этот отчёт вместо реальных проверок.

Нумерованные подразделы допускаются: `2.1 История изменений` соответствует
`История изменений`. Для каждого метода в docs/api.md нужен H2 `METHOD /path`,
внутри него H3 из API-шаблона. Неприменимые части объясняются явно. Согласования,
неизвестные URL, нагрузочные метрики и инфраструктура из PDF-примеров не выдумываются.
Редактируемые диаграммы, примеры запросов/ответов, доступ, сообщения/события,
поля/PK/FK и трассировка перечислены в policy.instructions.

Структурная check не доказывает правильность содержания. Согласованность требований,
маршрутов, данных и тестов остаётся за полными schema/reference checks Владимира,
api_contract/acceptance checks runner и проверкой экспертов. Это Markdown-адаптация
регламента: наличие Confluence, Jira, Figma или подписанного листа согласования не заявляется.
