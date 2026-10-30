from app.schemas.runs import ErrorDto


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.error = ErrorDto(code=code, message=message)
        self.status_code = status_code
        super().__init__(code)


class IntegrationUnavailable(AppError):
    def __init__(self, component: str):
        super().__init__("not_ready", f"Не подключён компонент: {component}.", 503)


class ProviderError(AppError):
    """Adapter must use a safe message, never the upstream response body/key."""

    def __init__(self, *, transient: bool = False):
        self.transient = transient
        super().__init__("provider_error", "Ошибка сервиса генерации.", 502)


def safe_error(exc: Exception) -> ErrorDto:
    if isinstance(exc, AppError):
        return exc.error
    # Exception strings may contain credentials, prompts or provider response bodies.
    return ErrorDto(code="internal_error", message="Внутренняя ошибка обработки запуска.")
