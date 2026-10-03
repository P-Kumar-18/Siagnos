from fastapi import FastAPI

from src.tracker.routes import router as tracker_router


app = FastAPI(
    title="Siagnos API",
    version="0.1.0",
)


app.include_router(tracker_router)


@app.get("/")
def root():
    return {
        "name": "Siagnos API",
        "status": "ok",
    }