# Anumate Tenancy

This package provides tenancy middleware and helpers for the Anumate platform.

## Usage

To use this package, you need to add the `TenantMiddleware` to your FastAPI application:

```python
from anumate_tenancy import add_tenant_middleware
from fastapi import FastAPI

app = FastAPI()

add_tenant_middleware(app)
```

You can then get the tenant ID in your request handlers using the `get_tenant_id` dependency:

```python
from anumate_tenancy import get_tenant_id
from fastapi import Depends

@app.get("/")
def my_handler(tenant_id: str = Depends(get_tenant_id)):
    return {"tenant_id": tenant_id}
```

The middleware will extract the tenant ID from the `X-Tenant-ID` header or from a JWT token in the `Authorization` header.
