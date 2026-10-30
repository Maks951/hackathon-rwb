"""Local check only. Yaroslav owns the production app/main.py composition root."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from app.api.runs import router as runs_router
from app.api.projects import router

app = FastAPI(title="Projects integration check")
app.include_router(router)
app.include_router(runs_router)

from app.api.artifacts import router as artifacts_router
app.include_router(artifacts_router)

@app.exception_handler(RequestValidationError)
def invalid_input(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"code": "invalid_input", "message": "Invalid project input"})


@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=detail)
