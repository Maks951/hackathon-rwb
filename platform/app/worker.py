"""One dedicated worker process. PostgreSQL queue semantics are the repository's contract."""

import asyncio
import logging
import signal
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from app.composition import load_runtime
from app.config import Settings
from app.errors import AppError, safe_error
from app.ports import RunRecord, RunStatus, Runtime
from app.services.pipeline import Pipeline

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, runtime: Runtime, settings: Settings):
        self.pipeline = Pipeline(runtime, settings)
        self.repository = self.pipeline.repository
        self.settings = settings

    async def run_once(self) -> bool:
        now = datetime.now(UTC)
        await self.repository.fail_stale(now - timedelta(seconds=self.settings.stale_seconds), now)
        # claim_next MUST commit before returning: no transaction surrounds LLM calls.
        run = await self.repository.claim_next()
        if run is None:
            return False
        if run.status != RunStatus.RUNNING:
            raise RuntimeError("claim_next must return a committed running run")
        await self.execute(run)
        return True

    async def execute(self, run: RunRecord) -> None:
        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(self.settings.heartbeat_seconds)
                if not await self.repository.heartbeat(run.id, datetime.now(UTC)):
                    raise AppError("worker_interrupted", "Запуск больше не принадлежит worker.")

        pipeline_task = asyncio.create_task(self.pipeline.run(run))
        heartbeat_task = asyncio.create_task(heartbeat())
        error = None
        try:
            async with asyncio.timeout(self.settings.run_timeout_seconds):
                done, _ = await asyncio.wait(
                    {pipeline_task, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED
                )
                # If heartbeat failed, never allow the pipeline to continue mutating a stale run.
                if heartbeat_task in done:
                    await heartbeat_task
                await pipeline_task
        except asyncio.CancelledError:
            error = AppError(
                "worker_interrupted", "Worker остановлен; создайте новый запуск."
            ).error
            raise
        except TimeoutError:
            error = AppError("run_timeout", "Превышено время выполнения запуска.").error
        except Exception as exc:
            error = safe_error(exc)
            logger.error("Run %s failed (%s)", run.id, error.code)
        finally:
            for task in (pipeline_task, heartbeat_task):
                if not task.done():
                    task.cancel()
            for task in (pipeline_task, heartbeat_task):
                with suppress(asyncio.CancelledError, Exception):
                    await task
            if error is not None:
                await self.repository.finish_run(run.id, RunStatus.FAILED, error, datetime.now(UTC))
            else:
                # Finalize only after heartbeat is stopped; succeeded requires validation + ZIP.
                await self.repository.finish_run(
                    run.id, RunStatus.SUCCEEDED, None, datetime.now(UTC)
                )

    async def serve(self) -> None:
        while True:
            try:
                worked = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A DB outage doesn't lose a run: stale recovery handles it after reconnection.
                logger.error("Worker iteration failed (%s)", type(exc).__name__)
                worked = False
            if not worked:
                await asyncio.sleep(self.settings.poll_seconds)


async def async_main() -> None:
    settings = Settings()
    runtime = load_runtime(settings)
    worker = Worker(runtime, settings)  # Fail startup if mandatory adapters aren't connected.
    task = asyncio.create_task(worker.serve())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):  # Windows event loops lack signal handlers.
            loop.add_signal_handler(sig, task.cancel)
    with suppress(asyncio.CancelledError):
        await task


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(async_main())
    except AppError as exc:
        logger.error("Worker cannot start (%s): %s", exc.error.code, exc.error.message)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
