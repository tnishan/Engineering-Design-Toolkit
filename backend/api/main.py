"""FastAPI application for the Engineering Design Toolkit."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routers import beam, post, projects, soil

app = FastAPI(
    title="Engineering Design Toolkit",
    description="Structural design tools to OBC 2024 / CSA O86-19.",
    version="0.1.0",
)

app.include_router(beam.router)
app.include_router(post.router)
app.include_router(projects.router)
app.include_router(soil.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve built frontend static files if present (allows single-server deployment on port 8010)
DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")
