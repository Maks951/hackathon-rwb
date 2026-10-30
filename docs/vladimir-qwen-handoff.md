# Владимир → Ярослав: Qwen adapter handoff

## Added

- `platform/app/llm/qwen.py`: OpenAI-compatible Qwen HTTP adapter, bearer auth, timeout, bounded response, provider error classification, token usage and finish reason normalization.
- `platform/app/llm/schemas.py`: strict RequirementsSpec/SystemSpec models and reference checks.
- `platform/app/llm/prompts.py`: versioned prompts for analyze/design/all generation stages/repair.
- `platform/app/llm/factory.py`: `create_qwen_adapter(settings)` helper.
- `platform/tests/test_qwen_adapter.py`: transport/schema/prompt tests using `httpx.MockTransport`.
- `platform/scripts/qwen_smoke.py`: one real provider request after credentials are configured.

## One-line integration

In the existing Runtime factory, assign:

```python
from app.llm import create_qwen_adapter

runtime.generation = create_qwen_adapter(settings)
```

Do not move repository, worker, run lifecycle or retries into the adapter. The existing `GenerationAdapter` port and `StepExecutor` remain the owner of orchestration/retry policy.

## Environment

Set the exact provider values in the runtime environment, not in git:

```dotenv
QWEN_BASE_URL=https://<provider-host>/<api-prefix>
QWEN_API_PATH=/chat/completions
QWEN_MODEL=<provider-model-id>
QWEN_API_KEY=<secret>
```

The endpoint path is configurable because OpenAI-compatible providers may expose different base URL prefixes. Do not assume that compatibility guarantees this endpoint; verify with the provider's supplied documentation/credentials.

## Verification performed on this archive

- `python -m compileall -q platform/app/llm platform/scripts/qwen_smoke.py platform/app/config.py` — passed.
- `cd platform && PYTHONPATH=. pytest -q` — 76 passed.
- The project declares Python `>=3.12,<3.13`; this archive was tested in the available Python 3.13.5 environment because Python 3.12 could not be downloaded in this environment. Re-run under Python 3.12 before merging.
- Real Qwen availability, authentication and latency are **not verified**: this archive contains no provider credentials or confirmed endpoint/model values. After configuring ENV, run `cd platform && PYTHONPATH=. python scripts/qwen_smoke.py`.
