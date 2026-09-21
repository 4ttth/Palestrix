import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..events import EVENT_TYPES
from ..netguard import UnsafeWebhookTarget, validate_webhook_url
from ..models import WebhookDelivery, WebhookSubscription
from ..rbac import Principal
from .deps import require_capability

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("", response_model=schemas.WebhookCreatedOut, status_code=201)
def subscribe(
    body: schemas.WebhookCreateIn,
    principal: Principal = Depends(require_capability("webhooks:manage")),
    db: Session = Depends(get_db),
):
    unknown = set(body.events) - EVENT_TYPES
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown event types: {sorted(unknown)}",
        )
    # Refuse an unreachable-by-policy target here, where the person can read
    # the reason. Delivery re-checks the resolved address anyway (DNS can
    # change under us), but a subscription that could never fire is worth a
    # 422 rather than a silent stream of failed deliveries.
    try:
        validate_webhook_url(body.url)
    except UnsafeWebhookTarget as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    sub = WebhookSubscription(
        owner_id=principal.user_id,
        url=body.url,
        secret=secrets.token_hex(24),
        events=body.events,
    )
    db.add(sub)
    db.commit()
    return schemas.WebhookCreatedOut(
        id=sub.id,
        url=sub.url,
        events=sub.events,
        active=sub.active,
        created_at=sub.created_at,
        secret=sub.secret,  # shown exactly once
    )


@router.get("", response_model=list[schemas.WebhookOut])
def list_subscriptions(
    principal: Principal = Depends(require_capability("webhooks:manage")),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(WebhookSubscription).where(
            WebhookSubscription.owner_id == principal.user_id
        )
    ).all()


@router.delete("/{sub_id}", status_code=204)
def unsubscribe(
    sub_id: str,
    principal: Principal = Depends(require_capability("webhooks:manage")),
    db: Session = Depends(get_db),
):
    sub = db.get(WebhookSubscription, sub_id)
    if sub is None or sub.owner_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such subscription")
    sub.active = False
    db.commit()


@router.get("/{sub_id}/deliveries", response_model=list[schemas.WebhookDeliveryOut])
def deliveries(
    sub_id: str,
    principal: Principal = Depends(require_capability("webhooks:manage")),
    db: Session = Depends(get_db),
):
    sub = db.get(WebhookSubscription, sub_id)
    if sub is None or sub.owner_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such subscription")
    return db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.subscription_id == sub_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
    ).all()
