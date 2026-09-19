from sqlalchemy.orm import Session

from app.models import User, Workspace

DEFAULT_WORKSPACE_NAME = "My Workspace"
DEFAULT_USER_NAME = "Me"


def seed_default_workspace(db: Session) -> tuple[Workspace, User]:
    workspace = db.query(Workspace).filter_by(name=DEFAULT_WORKSPACE_NAME).first()
    if workspace is None:
        workspace = Workspace(name=DEFAULT_WORKSPACE_NAME)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

    user = db.query(User).filter_by(workspace_id=workspace.id).first()
    if user is None:
        user = User(workspace_id=workspace.id, name=DEFAULT_USER_NAME)
        db.add(user)
        db.commit()
        db.refresh(user)

    return workspace, user
