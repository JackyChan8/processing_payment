import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.core import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str | None = Security(api_key_header)) -> None:
    expected = settings.API_KEY.get_secret_value()

    # защита от timing-атак
    if not hmac.compare_digest((api_key or "").encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ошибка авторизации",
            headers={"WWW-Authenticate": "ApiKey"},
        )
