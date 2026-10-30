from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project


def create_project(session: Session, *, name: str, requirements: str) -> Project:
    # Commit before returning: API success means the project is durable.
    with session.begin():
        project = Project(name=name, requirements=requirements)
        session.add(project)
        session.flush()
        session.refresh(project)
    return project


def list_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.created_at, Project.id)))


def get_project(session: Session, project_id: UUID) -> Project | None:
    return session.get(Project, project_id)
