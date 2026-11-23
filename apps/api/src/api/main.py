import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from env.api import env as http_env
from env.logging import env as logging_env
from env.mistral import env as mistral_env
from env.telemetry import env as telemetry_env
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mistralai_capabilities.fastapi.hooks import FastAPIHooks
from mistralai_capabilities.fastapi.openapi import operation_id
from mistralai_capabilities.fastapi.routing import create_api_router
from utils.logging import configure_logging
from utils.telemetry import configure_telemetry, shutdown_telemetry

from api.domain.errors import DomainError


def create_app(*, hooks: FastAPIHooks | None = None) -> FastAPI:
    configure_logging(log_level=logging_env.log_level, log_format=logging_env.log_format)
    if telemetry_env.telemetry_enabled:
        configure_telemetry(
            endpoint=telemetry_env.telemetry_endpoint,
            api_key=mistral_env.mistral_api_key,
            service_name=telemetry_env.telemetry_service_name,
            export_timeout_seconds=telemetry_env.telemetry_export_timeout_seconds,
        )

    manager = hooks if hooks is not None else FastAPIHooks.discover()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        try:
            await manager.startup(app)
            # Seed the fake data and index the KB at boot, so the first chat turn doesn't pay
            # for it (the chat route still calls ensure_ready as a lock-guarded safety net).
            from api.runtime import build_runtime, ensure_ready

            app.state.bnp_runtime = build_runtime(app)
            try:
                await ensure_ready(app.state.bnp_runtime)
            except Exception:
                logging.getLogger("bnp.startup").exception("ensure_ready failed at boot; the first request retries it")
            yield
        finally:
            # Hooks first, so their shutdown logs still export; telemetry last, even if one raises.
            try:
                await manager.shutdown(app)
            finally:
                shutdown_telemetry()

    # FastAPI 0.142+ logs every unhandled exception, stack trace included, to the global OTel logger
    # provider. That provider exports to TELEMETRY_ENDPOINT, which takes evaluation results only, so
    # keep the API's own error logs out of it.
    # Studio HTTP connectors import this spec and name each MCP tool after its operationId.
    app = FastAPI(lifespan=lifespan, telemetry={"logs": False}, generate_unique_id_function=operation_id)
    app.state.fastapi_hooks = manager
    manager.configure(app)
    app.include_router(create_api_router("api.routers"))

    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        # Domain errors carry their own status (ownership failures are 404 on purpose).
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": str(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[http_env.cors_origin],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    return app


app = create_app()
