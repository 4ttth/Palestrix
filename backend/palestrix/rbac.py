"""RBAC: the capability matrix from docs/rbac-matrix.md, enforced as FastAPI
dependencies. The UI hides what a role cannot do; this module is the actual
security boundary.

Two principal types reach the API:
- People (session JWT from password/passkey login): carry a Role.
- Machines (API key or OAuth2 client-credentials token): carry scopes.
Scopes map onto capabilities; a machine can never exceed the role of the
account that issued it (enforced at key/client creation time).
"""

from dataclasses import dataclass, field

from .models import Role

# Capability -> roles allowed. "own" restrictions (a teacher edits only their
# own course) are ownership checks in the endpoints; this matrix answers only
# "may this role ever do this".
CAPABILITIES: dict[str, set[Role]] = {
    "academy:complete": {Role.student},
    "instances:launch": {Role.student, Role.teacher, Role.admin, Role.superadmin},
    "instances:read-all": {Role.admin, Role.superadmin},
    "courses:write": {Role.teacher, Role.superadmin},
    "courses:enroll": {Role.student},
    "courses:grade": {Role.teacher, Role.superadmin},
    "community:moderate": {Role.teacher, Role.admin, Role.superadmin},
    "compete:submit": {Role.student},
    "compete:author": {Role.teacher, Role.admin, Role.superadmin},
    "compete:adjust": {Role.admin, Role.superadmin},
    "sandbox:submit": {Role.student, Role.teacher, Role.admin, Role.superadmin},
    "sandbox:read-all": {Role.admin, Role.superadmin},
    "sandbox:export": {Role.admin, Role.superadmin},
    "infra:manage": {Role.admin, Role.superadmin},
    "users:manage": {Role.admin, Role.superadmin},
    "plugins:manage": {Role.superadmin},
    "platform:settings": {Role.superadmin},
    "webhooks:manage": {Role.student, Role.teacher, Role.admin, Role.superadmin},
}

# Scopes grantable to API keys / OAuth clients, and the capability each
# scope unlocks. Read scopes without a capability row are ownership-scoped.
SCOPE_CAPABILITY: dict[str, str | None] = {
    "instances:launch": "instances:launch",
    "instances:read": None,
    "courses:write": "courses:write",
    "courses:read": None,
    "flags:submit": "compete:submit",
    "ledger:read": None,
    "community:write": None,
    "sandbox:submit": "sandbox:submit",
    "sandbox:read": None,
    "webhooks:manage": "webhooks:manage",
    "admin:infra": "infra:manage",
}


def role_allows(role: Role, capability: str) -> bool:
    return role in CAPABILITIES.get(capability, set())


def allowed_scopes_for_role(role: Role) -> set[str]:
    """The most a machine principal created by this role may hold."""
    scopes: set[str] = set()
    for scope, capability in SCOPE_CAPABILITY.items():
        if capability is None or role_allows(role, capability):
            scopes.add(scope)
    return scopes


@dataclass
class Principal:
    """The authenticated caller, human or machine."""

    user_id: str
    role: Role
    tenant_id: str | None
    kind: str = "session"  # session | api-key | client
    scopes: set[str] = field(default_factory=set)

    def can(self, capability: str) -> bool:
        if not role_allows(self.role, capability):
            return False
        if self.kind == "session":
            return True
        # Machine principals additionally need the covering scope.
        needed = {s for s, c in SCOPE_CAPABILITY.items() if c == capability}
        return bool(needed & self.scopes) if needed else False

    def has_scope(self, scope: str) -> bool:
        return self.kind == "session" or scope in self.scopes
