"""Sandbox API surface. The detonation module itself is the Phase 6
deliverable (docs/sandbox-security.md); the contract is declared now so
clients and the OpenAPI spec are stable."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..rbac import Principal
from .deps import get_principal

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

_NOT_YET = HTTPException(
    status.HTTP_501_NOT_IMPLEMENTED,
    "the malware sandbox module ships in Phase 6; this endpoint is reserved",
)


@router.post("/samples", status_code=501)
def submit_sample(principal: Principal = Depends(get_principal)):
    raise _NOT_YET


@router.get("/reports", status_code=501)
def list_reports(principal: Principal = Depends(get_principal)):
    raise _NOT_YET
