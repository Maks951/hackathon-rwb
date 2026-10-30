import importlib

from app.config import Settings
from app.ports import Runtime


def load_runtime(settings: Settings) -> Runtime:
    """One composition root shared by API and worker; no hidden in-memory fallback."""
    if not settings.runtime_factory:
        return Runtime()
    module_name, separator, name = settings.runtime_factory.partition(":")
    if not separator or not module_name or not name:
        raise ValueError("RWB_RUNTIME_FACTORY must be module:factory")
    factory = getattr(importlib.import_module(module_name), name)
    runtime = factory(settings)
    if not isinstance(runtime, Runtime):
        raise TypeError("Runtime factory must return app.ports.Runtime")
    return runtime
