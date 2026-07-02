"""Plugin management: superadmin only (capability plugins:manage, which no
machine scope covers, so this surface is session-token only by design)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import PluginRecord
from ..plugins.registry import LoadedPlugin, PluginError, registry
from ..rbac import Principal
from .deps import require_capability

router = APIRouter(prefix="/plugins", tags=["plugins"])

_ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "unsupported": status.HTTP_409_CONFLICT,
    "scopes": status.HTTP_409_CONFLICT,
    "hook": status.HTTP_409_CONFLICT,
    "config": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _out(loaded: LoadedPlugin, record: PluginRecord | None) -> schemas.PluginOut:
    m = loaded.manifest
    return schemas.PluginOut(
        id=m.id,
        name=m.name,
        version=m.version,
        api=m.api,
        source=loaded.source,
        state=loaded.state,
        error=loaded.error or (record.error if record else None),
        scopes=list(m.scopes),
        granted_scopes=list(record.granted_scopes or []) if record else [],
        config_required=list(m.config_required),
        config_optional=list(m.config_optional),
        config_secret=list(m.config_secret),
    )


@router.get("", response_model=list[schemas.PluginOut])
def list_plugins(
    principal: Principal = Depends(require_capability("plugins:manage")),
    db: Session = Depends(get_db),
):
    return [
        _out(loaded, db.get(PluginRecord, plugin_id))
        for plugin_id, loaded in sorted(registry.plugins.items())
    ]


@router.post("/{plugin_id}/enable", response_model=schemas.PluginOut)
def enable_plugin(
    plugin_id: str,
    body: schemas.PluginEnableIn,
    principal: Principal = Depends(require_capability("plugins:manage")),
    db: Session = Depends(get_db),
):
    try:
        loaded = registry.enable(
            db,
            plugin_id,
            config=body.config,
            granted_by_user_id=principal.user_id,
            approve_scopes=body.approve_scopes,
        )
    except PluginError as exc:
        db.rollback()
        raise HTTPException(_ERROR_STATUS[exc.code], str(exc))
    return _out(loaded, db.get(PluginRecord, plugin_id))


@router.post("/{plugin_id}/disable", response_model=schemas.PluginOut)
def disable_plugin(
    plugin_id: str,
    principal: Principal = Depends(require_capability("plugins:manage")),
    db: Session = Depends(get_db),
):
    try:
        loaded = registry.disable(db, plugin_id)
    except PluginError as exc:
        raise HTTPException(_ERROR_STATUS[exc.code], str(exc))
    return _out(loaded, db.get(PluginRecord, plugin_id))
