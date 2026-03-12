from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.mock_data import get_service_or_none, request_action

router = APIRouter()

ALLOWED_ACTIONS = {"start", "stop"}


class ActionRequest(BaseModel):
    action: str = Field(description="Action name")


@router.post("/services/{service_key}/actions")
def post_service_action(service_key: str, request: ActionRequest) -> dict:
    service = get_service_or_none(service_key)
    if not service:
        raise HTTPException(status_code=404, detail="service not found")
    if request.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"unsupported action: {request.action}")
    return request_action(service_key=service_key, action=request.action)

