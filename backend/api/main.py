"""FastAPI application for the Engineering Design Toolkit."""

from fastapi import FastAPI

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
