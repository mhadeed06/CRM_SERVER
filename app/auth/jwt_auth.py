"""
JWT bearer-token verification for endpoints called by the PracticeEHR .NET CRM.

Matches the .NET TokenValidationParameters config:
- HS256 signing
- ValidateIssuer = false
- ValidateAudience = false
- ClockSkew = Zero (leeway=0)
- exp claim required
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import CONFIG

_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not Authorized",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            CONFIG.JWT_SECRET_KEY,
            algorithms=["HS256"],
            options={
                "verify_iss": False,
                "verify_aud": False,
                "require": ["exp"],
            },
            leeway=0,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Expired",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not Authorized",
        )

    return payload
