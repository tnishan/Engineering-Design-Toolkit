"""Saved project storage.

Projects are stored as plain JSON files in ``backend/projects/`` so they can be
copied, diffed, backed up or committed like any other engineering file. The
stored payload is the design *input* only - results are always recomputed on
load, so a saved project never goes stale against a code or formula change.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.schemas.beam import DesignRequestIn

router = APIRouter(prefix="/api/projects", tags=["projects"])

PROJECT_DIR = Path(__file__).resolve().parents[2] / "projects"
_SAFE = re.compile(r"[^a-z0-9]+")
_MAX_PROJECTS = 500


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    payload: DesignRequestIn


class ProjectSummary(BaseModel):
    id: str
    name: str
    saved_at: str
    member: str
    material_key: str
    spans: list[str]


class ProjectOut(ProjectSummary):
    payload: DesignRequestIn


def _slug(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    slug = _SAFE.sub("-", ascii_name.lower()).strip("-")
    return slug or "project"


def _path(project_id: str) -> Path:
    """Resolve an id to a file, refusing anything that escapes the directory."""
    if project_id != _slug(project_id):
        raise HTTPException(status_code=400, detail="Invalid project id.")
    path = (PROJECT_DIR / f"{project_id}.json").resolve()
    if path.parent != PROJECT_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid project id.")
    return path


def _summary(data: dict, project_id: str) -> dict:
    payload = data.get("payload", {})
    return {
        "id": project_id,
        "name": data.get("name", project_id),
        "saved_at": data.get("saved_at", ""),
        "member": payload.get("member", ""),
        "material_key": payload.get("material_key", ""),
        "spans": [str(s) for s in payload.get("spans", [])],
    }


@router.get("", response_model=list[ProjectSummary])
def list_projects() -> list[dict]:
    if not PROJECT_DIR.exists():
        return []
    out = []
    for path in PROJECT_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # skip anything hand-edited into an unreadable state
        out.append(_summary(data, path.stem))
    out.sort(key=lambda p: p["saved_at"], reverse=True)
    return out


@router.put("/{project_id}", response_model=ProjectSummary)
@router.post("", response_model=ProjectSummary)
def save_project(project: ProjectIn, project_id: str | None = None) -> dict:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    pid = project_id or _slug(project.name)
    path = _path(pid)

    if not path.exists() and len(list(PROJECT_DIR.glob("*.json"))) >= _MAX_PROJECTS:
        raise HTTPException(
            status_code=400,
            detail=f"Project limit of {_MAX_PROJECTS} reached; delete some first.",
        )

    record = {
        "name": project.name,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": project.payload.model_dump(mode="json"),
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return _summary(record, pid)


@router.get("/{project_id}", response_model=ProjectOut)
def load_project(project_id: str) -> dict:
    path = _path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No project named {project_id!r}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Project file unreadable: {exc}") from exc
    return {**_summary(data, project_id), "payload": data.get("payload", {})}


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    path = _path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No project named {project_id!r}.")
    path.unlink()
    return {"status": "deleted", "id": project_id}
