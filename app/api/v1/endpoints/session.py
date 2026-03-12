from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/session")
def get_session() -> dict:
    return {
        "environment": settings.environment,
        "operator": {
            "email": "operator@example.com",
            "display_name": "operator",
        },
        "auth": {
            "provider": "cloudflare_access",
        },
    }

