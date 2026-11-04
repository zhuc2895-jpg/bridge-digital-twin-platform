"""Bridge model import and activation API."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.bridge_models import (
    BridgeModelError,
    BridgeModelNotFoundError,
    BridgeModelTooLargeError,
)
from app.bridge_scene_profile import BridgeSceneProfileError, bundled_scene_profile
from app.dependencies import AppServices, get_services

router = APIRouter()
DEFAULT_MODEL_URL = "/models/huihe_bridge.glb"


@router.get("")
async def list_models(services: AppServices = Depends(get_services)):
    """List every imported model and the current active selection."""
    store = services.model_store
    active = store.active_model()
    return {
        "models": store.list_models(),
        "active": active.to_public(active=True) if active is not None else None,
        "default_url": DEFAULT_MODEL_URL,
    }


@router.get("/active")
async def get_active_model(services: AppServices = Depends(get_services)):
    """Return the active imported model, or the bundled default model."""
    active = services.model_store.active_model()
    if active is None:
        return {
            "active": None,
            "source": "bundled",
            "file_url": DEFAULT_MODEL_URL,
            "default_url": DEFAULT_MODEL_URL,
            "profile_url": "/api/models/active/profile",
            "profile_revision": 1,
            "profile_source": "bundled",
        }
    return {
        "active": active.to_public(active=True),
        "source": "imported",
        "file_url": f"/api/models/{active.model_id}/file",
        "default_url": DEFAULT_MODEL_URL,
        "profile_url": "/api/models/active/profile",
        "profile_revision": active.profile_revision,
        "profile_source": active.profile_source,
    }


@router.get("/active/profile")
async def get_active_profile(services: AppServices = Depends(get_services)):
    try:
        profile = services.model_store.active_profile()
    except BridgeSceneProfileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return profile.to_dict() if profile is not None else bundled_scene_profile().to_dict()


@router.post("/deactivate")
async def deactivate_model(services: AppServices = Depends(get_services)):
    """Return to the bundled bridge model without deleting imported files."""
    services.model_store.deactivate()
    return {
        "active": None,
        "source": "bundled",
        "file_url": DEFAULT_MODEL_URL,
        "default_url": DEFAULT_MODEL_URL,
    }


@router.post("/import", status_code=201)
async def import_model(
    file: UploadFile = File(...),
    profile_file: UploadFile | None = File(default=None),
    name: str | None = Form(default=None),
    activate: bool = Form(default=True),
    services: AppServices = Depends(get_services),
):
    """Upload a self-contained GLB or glTF bridge model."""
    store = services.model_store
    try:
        profile_document = None
        if profile_file is not None:
            profile_document = await _read_profile_upload(profile_file)
        await file.seek(0)
        model = await run_in_threadpool(
            store.import_stream,
            file.file,
            file.filename or "bridge.glb",
            display_name=name,
            activate=activate,
            profile_document=profile_document,
        )
    except BridgeModelTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except BridgeModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BridgeSceneProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "active" if model["active"] else "imported", "model": model}


@router.get("/{model_id}/profile")
async def get_model_profile(
    model_id: str,
    revision: int | None = None,
    services: AppServices = Depends(get_services),
):
    try:
        return services.model_store.profile_public(model_id, revision)
    except BridgeModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BridgeSceneProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{model_id}/profile")
async def replace_model_profile(
    model_id: str,
    file: UploadFile = File(...),
    services: AppServices = Depends(get_services),
):
    try:
        document = await _read_profile_upload(file)
        model = services.model_store.replace_profile(model_id, document)
    except BridgeModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (BridgeSceneProfileError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "model": model}


@router.get("/{model_id}")
async def get_model(model_id: str, services: AppServices = Depends(get_services)):
    try:
        active = services.model_store.active_model()
        return services.model_store.get(model_id).to_public(
            active=active is not None and active.model_id == model_id
        )
    except BridgeModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{model_id}/activate")
async def activate_model(
    model_id: str,
    services: AppServices = Depends(get_services),
):
    try:
        return {"status": "active", "model": services.model_store.activate(model_id)}
    except BridgeModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{model_id}")
async def delete_model(
    model_id: str,
    services: AppServices = Depends(get_services),
):
    try:
        services.model_store.delete(model_id)
    except BridgeModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BridgeModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "deleted", "model_id": model_id}


@router.get("/{model_id}/file")
async def download_model(
    model_id: str,
    services: AppServices = Depends(get_services),
):
    try:
        record = services.model_store.get(model_id)
        path = services.model_store.file_path(model_id)
    except BridgeModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BridgeModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=record.to_public(active=False)["media_type"],
        filename=record.original_filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "no-cache"},
    )


async def _read_profile_upload(file: UploadFile) -> dict:
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise BridgeSceneProfileError("Scene profile exceeds 2MB")
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeSceneProfileError("Scene profile must be valid UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise BridgeSceneProfileError("Scene profile must contain a JSON object")
    return document
