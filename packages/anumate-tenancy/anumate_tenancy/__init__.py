from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from jose import jwt


class TenantMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope["headers"]
        tenant_id = None
        for name, value in headers:
            if name.lower() == b"x-tenant-id":
                tenant_id = value.decode("utf-8")
                break

        if tenant_id is None:
            for name, value in headers:
                if name.lower() == b"authorization":
                    try:
                        token = value.decode("utf-8").split(" ")[1]
                        payload = jwt.get_unverified_claims(token)
                        tenant_id = payload.get("tenant_id")
                    except Exception:
                        pass
                    break

        scope["tenant_id"] = tenant_id
        await self.app(scope, receive, send)


def get_tenant_id(request: Request) -> str:
    if not hasattr(request.scope, "tenant_id") or request.scope["tenant_id"] is None:
        raise HTTPException(status_code=400, detail="Tenant ID not found in request")
    return request.scope["tenant_id"]


def add_tenant_middleware(app: Any) -> None:
    app.add_middleware(TenantMiddleware)
