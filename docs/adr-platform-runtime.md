# ADR: выполнение pipeline вне HTTP-процесса

## Контекст и постановка проблемы

Qwen, проверки и упаковка занимают больше времени, чем обычный HTTP-запрос.
Нужно сохранять прогресс и не терять состояние при остановке API.

## Статус

ПРИНЯТО в командном плане `03_Yaroslav_Python_Pipeline.md` для P0.
Python worker реализован; транзакционная очередь ждёт RunRepository Романа.

## Альтернативы

| Вариант | Плюсы | Минусы |
| --- | --- | --- |
| BackgroundTasks/память API | Простой старт | Потеря очереди при рестарте; нет нужной durability |
| PostgreSQL runs + worker | Состояние и очередь в одной БД; короткие транзакции | Нужны DB constraints, claim/heartbeat/stale logic |
| Celery/Redis или Kafka | Больше возможностей очередей | Дополнительные компоненты и настройка за пределами P0 |

## Принятое решение

API делегирует создание queued run repository и возвращает 202. Worker вызывает
claim_next с commit до LLM, пишет heartbeat, выполняет шаги с immutable files.
После прерывания stale run должен стать failed; новый запуск вместо auto-resume.

## Последствия принятого решения

Один worker в P0. Не заявляются exactly-once, параллельные workers или fencing.
Модуль БД и RunRepository остаются у Романа, Qwen у Владимира, runner у Дмитрия.
Compose использует отдельные API/worker процессы с общим generated volume.

## Ответственные

Ярослав — composition/lifecycle; Роман — PostgreSQL/repository; Дмитрий — deployment.
Внешний лист согласования и корпоративное одобрение не предоставлены.
