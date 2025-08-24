
from fastapi import FastAPI
import uvicorn
import asyncio

app = FastAPI(
    title="Capsule Registry MVP",
    version="1.0.0",
    description="Production-grade hackathon MVP"
)

@app.get("/")
async def root():
    return {"status": "healthy", "service": "capsule-registry"}

@app.get("/healthz")
async def health():
    return {"status": "healthy"}

@app.get("/readyz")
async def readiness():
    return {"status": "ready"}

@app.get("/v1/capsules")
async def list_capsules():
    return {"capsules": [], "total": 0, "message": "MVP endpoint working"}

if __name__ == "__main__":
    print("🚀 Starting Capsule Registry MVP...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
