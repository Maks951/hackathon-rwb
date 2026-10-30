from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.repositories import projects
from app.schemas.projects import ProjectCreate, ProjectList, ProjectRead

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
DbSession = Annotated[Session, Depends(get_session)]


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, session: DbSession):
    return projects.create_project(session, name=payload.name, requirements=payload.requirements)


@router.get("", response_model=ProjectList)
def list_projects(session: DbSession):
    return {"items": projects.list_projects(session)}


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, session: DbSession):
    project = projects.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Project not found"})
    return project
