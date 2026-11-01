"""
Bridge Digital Twin Platform - FastAPI application assembly.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_alert, routes_analysis, routes_data, routes_sensor
from app.config import AppConfig
from app.dependencies import AppServices, create_services, get_services
from app.observability import (
    REQUEST_ID_HEADER,
    configure_logging,
    normalize_request_id,
    redact_text,
    stable_error_payload,
)

logger = logging.getLogger(__name__)


def create_app(
    services: Optional[AppServices] = None,
    *,
    config: AppConfig | None = None,
) -> FastAPI:
    """Build an isolated application with its own mutable service state."""
    resolved_config = config or (
        services.config if services is not None else AppConfig.from_env()
    )
    configure_logging(resolved_config.log_level)
    resolved_services = services or create_services(
        persistence_enabled=True,
        config=resolved_config,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if application.state.services.live_stream_autostart:
            application.state.services.live_stream.start()
        try:
            yield
        finally:
            application.state.services.live_stream.stop()
            persistence = application.state.services.persistence
            if persistence is not None:
                with application.state.services.processing_lock:
                    persistence.commit()

    application = FastAPI(
        title="Bridge Digital Twin Platform",
        description="数字孪生 + 桥梁结构健康监测与预警系统",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.services = resolved_services
    application.state.config = resolved_config

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_config.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request_completed request_id=%s method=%s path=%s status=%d "
            "duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    application.include_router(
        routes_sensor.router, prefix="/api/sensors", tags=["传感器数据"]
    )
    application.include_router(
        routes_alert.router, prefix="/api/alerts", tags=["告警管理"]
    )
    application.include_router(
        routes_analysis.router, prefix="/api/analysis", tags=["数据分析"]
    )
    application.include_router(
        routes_data.router, prefix="/api/data", tags=["数据上传"]
    )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ):
        path = request.url.path
        is_ingestion = path.startswith("/api/data/upload/")
        returns_400_for_query_validation = path in {
            "/api/analysis/report",
            "/api/sensors/history/range",
            "/api/sensors/history/alerts",
        } or (path.startswith("/api/sensors/") and path.endswith("/history"))
        if not (is_ingestion or returns_400_for_query_validation):
            return await request_validation_exception_handler(request, exc)

        errors = [
            {
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid request data", "errors": errors},
            headers={
                REQUEST_ID_HEADER: getattr(request.state, "request_id", "")
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(
            request.state,
            "request_id",
            normalize_request_id(None),
        )
        logger.error(
            "unhandled_request_error request_id=%s method=%s path=%s "
            "error_type=%s message=%s",
            request_id,
            request.method,
            request.url.path,
            type(exc).__name__,
            redact_text(str(exc)),
        )
        return JSONResponse(
            status_code=500,
            content=stable_error_payload(request_id),
            headers={REQUEST_ID_HEADER: request_id},
        )

    @application.get("/")
    async def root():
        return {
            "name": "Bridge Digital Twin Platform",
            "version": "1.0.0",
            "status": "running",
        }

    @application.get("/api/health")
    async def health_check(services: AppServices = Depends(get_services)):
        engine = services.engine
        with services.processing_lock:
            sensor_count = engine.get_sensor_count()
            online_sensor_count = engine.get_online_sensor_count()
            retained_alerts = engine.get_alert_count()
        persistence_status = (
            services.persistence.status()
            if services.persistence is not None
            else {"enabled": False}
        )
        try:
            detector_status = services.detectors.get_stats()
            degraded_detectors = [
                detector["id"]
                for detector in detector_status.get("detectors", [])
                if detector.get("health") != "healthy"
            ]
            detector_health = "degraded" if degraded_detectors else "healthy"
        except Exception as exc:
            detector_health = "degraded"
            degraded_detectors = [type(exc).__name__]
        persistence_degraded = bool(persistence_status.get("last_error"))
        overall_status = (
            "degraded"
            if persistence_degraded or detector_health == "degraded"
            else "healthy"
        )
        return {
            "status": overall_status,
            "sensor_count": sensor_count,
            "online_sensor_count": online_sensor_count,
            "retained_alerts": retained_alerts,
            "simulator_running": (
                services.simulator.is_running
                if services.config.simulation_enabled
                else False
            ),
            "state_scope": "process",
            "persistence": persistence_status,
            "checks": {
                "detectors": {
                    "status": detector_health,
                    "degraded": degraded_detectors,
                },
                "persistence": {
                    "status": (
                        "degraded" if persistence_degraded else "healthy"
                    ),
                },
            },
        }

    @application.websocket("/ws/live")
    async def websocket_live(
        websocket: WebSocket,
        services: AppServices = Depends(get_services),
    ):
        """Subscribe a client to the one application-wide live stream."""
        await services.ws_manager.connect(websocket)
        if services.config.simulation_enabled:
            services.live_stream.start()
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            services.ws_manager.disconnect(websocket)

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    runtime_config = app.state.config
    uvicorn.run(
        "app.main:app",
        host=runtime_config.host,
        port=runtime_config.port,
        reload=True,
    )
