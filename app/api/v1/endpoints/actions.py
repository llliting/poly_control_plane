from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.mock_data import get_service_or_none, request_action
from app.services.repository import create_action_request, get_action_status, list_services_from_db

router = APIRouter()

ALLOWED_ACTIONS = {"start", "stop"}


class ActionRequest(BaseModel):
    action: str = Field(description="Action name")


@router.post("/services/{service_key}/actions")
def post_service_action(service_key: str, request: ActionRequest) -> dict:
    service = None
    try:
        services = list_services_from_db()
        if services is not None:
            service = next((s for s in services if s["service_key"] == service_key), None)
    except Exception:
        service = None
    if service is None:
        service = get_service_or_none(service_key)

    if not service:
        raise HTTPException(status_code=404, detail="service not found")
    if request.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"unsupported action: {request.action}")

    try:
        created = create_action_request(service_key=service_key, action=request.action, requested_payload={"source": "api"})
        if created is not None:
            return created
    except Exception:
        pass

    return request_action(service_key=service_key, action=request.action)


@router.get("/actions/{action_id}")
def get_action(action_id: str) -> dict:
    try:
        action = get_action_status(action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="action not found")
        return action
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"failed to fetch action: {err}") from err
