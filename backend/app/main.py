"""
Bridge Digital Twin Platform - FastAPI application assembly.
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_alert, routes_analysis, routes_data, routes_sensor
from app.dependencies import AppServices, create_services, get_services


def create_app(services: Optional[AppServices] = None) -> FastAPI:
    """Build an isolated application with its own mutable service state."""
    resolved_services = services or create_services()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if application.state.services.live_stream_autostart:
            application.state.services.live_stream.start()
        try:
            yield
        finally:
            application.state.services.live_stream.stop()

    application = FastAPI(
        title="Bridge Digital Twin Platform",
        description="数字孪生 + 桥梁结构健康监测与预警系统",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.services = resolved_services

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        uses_history_query_validation = path in {
            "/api/sensors/history/range",
            "/api/sensors/history/alerts",
        } or (path.startswith("/api/sensors/") and path.endswith("/history"))
        if not (is_ingestion or uses_history_query_validation):
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
        return {
            "status": "healthy",
            "sensor_count": engine.get_sensor_count(),
            "retained_alerts": engine.get_alert_count(),
            "simulator_running": services.simulator.is_running,
        }

    @application.websocket("/ws/live")
    async def websocket_live(
        websocket: WebSocket,
        services: AppServices = Depends(get_services),
    ):
        """Subscribe a client to the one application-wide live stream."""
        await services.ws_manager.connect(websocket)
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

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
