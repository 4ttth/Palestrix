"""Canvas LMS adapter: the ExternalPlatform reference implementation
(docs/integrations-canvas-lms.md).

Protocols, all standard IMS — nothing here is Canvas-proprietary beyond the
default endpoint paths, which is what keeps this file a template for the
next platform:

- Launch + identity: LTI 1.3 (OIDC third-party initiation, RS256 id_token
  against the platform keyset).
- Roster: LTI Names and Role Provisioning Services (NRPS) v2.
- Grade passback: LTI Assignment and Grade Services (AGS) score publish.
- Content selection: LTI Deep Linking 2.0 (signed response JWT).

Service calls (NRPS, AGS) authenticate with OAuth2 client-credentials using
a JWT client assertion signed by the tool key — the same key the tool JWKS
endpoint publishes and Canvas pins. Tokens are minted per call and never
persisted (failure/privacy posture in the integration doc).

Like the Proxmox/OpenNebula/CloudStack adapters, the constructor accepts an
injectable httpx client and explicit config overrides so the contract tests
run against a MockTransport.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..config import get_settings
from ..tls import client_verify
from . import LaunchClaims, LaunchValidationError, RosterEntry

logger = logging.getLogger("palestrix.integrations.canvas")

# The LTI claim URIs, isolated here so nothing outside the adapter needs them.
CLAIM_MESSAGE_TYPE = "https://purl.imsglobal.org/spec/lti/claim/message_type"
CLAIM_VERSION = "https://purl.imsglobal.org/spec/lti/claim/version"
CLAIM_DEPLOYMENT = "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
CLAIM_TARGET = "https://purl.imsglobal.org/spec/lti/claim/target_link_uri"
CLAIM_CONTEXT = "https://purl.imsglobal.org/spec/lti/claim/context"
CLAIM_RESOURCE_LINK = "https://purl.imsglobal.org/spec/lti/claim/resource_link"
CLAIM_ROLES = "https://purl.imsglobal.org/spec/lti/claim/roles"
CLAIM_CUSTOM = "https://purl.imsglobal.org/spec/lti/claim/custom"
CLAIM_NRPS = "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice"
CLAIM_AGS = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"
CLAIM_DL_SETTINGS = "https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings"
CLAIM_DL_CONTENT_ITEMS = "https://purl.imsglobal.org/spec/lti-dl/claim/content_items"
CLAIM_DL_DATA = "https://purl.imsglobal.org/spec/lti-dl/claim/data"

SCOPE_NRPS = "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"
SCOPE_AGS_SCORE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

MESSAGE_TYPES = {
    "LtiResourceLinkRequest": "resource",
    "LtiDeepLinkingRequest": "deep-link",
}


def _normalize_roles(role_uris: list[str]) -> list[str]:
    roles = set()
    for uri in role_uris or []:
        if "Instructor" in uri or "Administrator" in uri:
            roles.add("instructor")
        elif "Learner" in uri:
            roles.add("learner")
    return sorted(roles)


def _scores_url(lineitem_url: str) -> str:
    """AGS scores live at <lineitem>/scores; Canvas line-item URLs may carry
    a query string, so the path segment is inserted before it."""
    scheme, netloc, path, query, fragment = urlsplit(lineitem_url)
    return urlunsplit((scheme, netloc, path.rstrip("/") + "/scores", query, fragment))


class CanvasPlatform:
    id = "canvas-lms"
    name = "Canvas LMS"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        issuer: str | None = None,
        client_id: str | None = None,
        deployment_id: str | None = None,
        auth_url: str | None = None,
        jwks_url: str | None = None,
        token_url: str | None = None,
        private_key_pem: str | None = None,
    ) -> None:
        settings = get_settings()
        self.issuer = (issuer or settings.canvas_issuer).rstrip("/")
        self._client_id = client_id or settings.canvas_client_id
        self._deployment_id = (
            deployment_id if deployment_id is not None else settings.canvas_deployment_id
        )
        # Canvas's conventional endpoint paths under the issuer; the settings
        # override them for nonstandard mounts (e.g. Instructure cloud SSO).
        self._auth_url = auth_url or settings.canvas_auth_url or f"{self.issuer}/api/lti/authorize_redirect"
        self._jwks_url = jwks_url or settings.canvas_jwks_url or f"{self.issuer}/api/lti/security/jwks"
        self._token_url = token_url or settings.canvas_token_url or f"{self.issuer}/login/oauth2/token"
        self._client = client or httpx.Client(
            verify=client_verify(settings.canvas_verify_tls, settings.canvas_ca_bundle),
            timeout=settings.canvas_timeout_seconds,
        )

        pem = private_key_pem if private_key_pem is not None else settings.canvas_tool_private_key
        if pem:
            self._private_key = serialization.load_pem_private_key(
                pem.encode(), password=None
            )
            self.ephemeral_key = False
        else:
            # Dev convenience only: Canvas pins the tool JWKS, so a restart
            # rotating this key breaks launches. The production boot guard
            # flags it (hardening.py).
            self._private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )
            self.ephemeral_key = True
            logger.warning(
                "PALESTRIX_CANVAS_TOOL_PRIVATE_KEY is empty; generated an "
                "ephemeral dev signing key (rotates on restart)"
            )
        public_pem = self._private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self._kid = hashlib.sha256(public_pem).hexdigest()[:16]

    # -- tool keyset ---------------------------------------------------------------

    def jwks(self) -> dict:
        jwk = json.loads(
            pyjwt.algorithms.RSAAlgorithm.to_jwk(self._private_key.public_key())
        )
        jwk.update({"kid": self._kid, "use": "sig", "alg": "RS256"})
        return {"keys": [jwk]}

    def _tool_jwt(self, claims: dict) -> str:
        return pyjwt.encode(
            claims, self._private_key, algorithm="RS256", headers={"kid": self._kid}
        )

    # -- LTI 1.3 launch --------------------------------------------------------------

    def login_redirect_url(
        self, *, login_hint: str, target_link_uri: str, state: str, nonce: str,
        lti_message_hint: str = "",
    ) -> str:
        """OIDC third-party initiation: send the browser to the platform's
        authorization endpoint; Canvas answers with a form_post of the
        id_token to the redirect_uri (our launch endpoint, which the
        developer key registers as the target link URI)."""
        params = {
            "scope": "openid",
            "response_type": "id_token",
            "response_mode": "form_post",
            "prompt": "none",
            "client_id": self._client_id,
            "redirect_uri": target_link_uri,
            "login_hint": login_hint,
            "state": state,
            "nonce": nonce,
        }
        if lti_message_hint:
            params["lti_message_hint"] = lti_message_hint
        return f"{self._auth_url}?{urlencode(params)}"

    def validate_launch(self, id_token: str, *, nonce: str) -> LaunchClaims:
        """Verify the id_token against the platform keyset and normalize the
        claims. Raises LaunchValidationError / pyjwt errors on anything off."""
        header = pyjwt.get_unverified_header(id_token)
        resp = self._client.get(self._jwks_url)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        jwk = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if jwk is None:
            raise LaunchValidationError("id_token kid not in the platform keyset")
        public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        claims = pyjwt.decode(
            id_token,
            key=public_key,
            algorithms=["RS256"],
            audience=self._client_id,
            issuer=self.issuer,
        )
        if claims.get("nonce") != nonce:
            raise LaunchValidationError("nonce mismatch (replayed launch?)")
        if self._deployment_id and claims.get(CLAIM_DEPLOYMENT) != self._deployment_id:
            raise LaunchValidationError("unknown deployment id")
        message_type = MESSAGE_TYPES.get(claims.get(CLAIM_MESSAGE_TYPE, ""))
        if message_type is None:
            raise LaunchValidationError(
                f"unsupported message type {claims.get(CLAIM_MESSAGE_TYPE)!r}"
            )

        context = claims.get(CLAIM_CONTEXT) or {}
        resource_link = claims.get(CLAIM_RESOURCE_LINK) or {}
        nrps = claims.get(CLAIM_NRPS) or {}
        ags = claims.get(CLAIM_AGS) or {}
        dl = claims.get(CLAIM_DL_SETTINGS) or {}
        return LaunchClaims(
            message_type=message_type,
            issuer=claims["iss"],
            subject=claims["sub"],
            email=claims.get("email", ""),
            name=claims.get("name", ""),
            roles=_normalize_roles(claims.get(CLAIM_ROLES, [])),
            deployment_id=claims.get(CLAIM_DEPLOYMENT, ""),
            context_id=context.get("id", ""),
            context_title=context.get("title", ""),
            nrps_url=nrps.get("context_memberships_url", ""),
            lineitem_url=ags.get("lineitem", ""),
            resource_link_id=resource_link.get("id", ""),
            resource_link_title=resource_link.get("title", ""),
            target_link_uri=claims.get(CLAIM_TARGET, ""),
            custom=claims.get(CLAIM_CUSTOM) or {},
            deep_link_return_url=dl.get("deep_link_return_url", ""),
            deep_link_data=dl.get("data", ""),
        )

    # -- OAuth2 client-credentials for the LTI services --------------------------------

    def _access_token(self, scope: str) -> str:
        now = datetime.now(timezone.utc)
        assertion = self._tool_jwt(
            {
                "iss": self._client_id,
                "sub": self._client_id,
                "aud": self._token_url,
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "jti": uuid.uuid4().hex,
            }
        )
        resp = self._client.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": assertion,
                "scope": scope,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # -- NRPS roster --------------------------------------------------------------------

    def fetch_roster(self, link) -> list[RosterEntry]:
        """NRPS membership for the linked context. The launch-provided
        membership URL wins; before any launch has happened, Canvas's
        conventional per-course NRPS path serves the same document."""
        url = (
            link.nrps_url
            or f"{self.issuer}/api/lti/courses/{link.external_course_id}/names_and_roles"
        )
        token = self._access_token(SCOPE_NRPS)
        entries: list[RosterEntry] = []
        while url:
            resp = self._client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.ims.lti-nrps.v2.membershipcontainer+json",
                },
            )
            resp.raise_for_status()
            for member in resp.json().get("members", []):
                if member.get("status", "Active") != "Active":
                    continue
                roles = _normalize_roles(member.get("roles", []))
                role = (
                    "teacher"
                    if "instructor" in roles
                    else "student" if "learner" in roles else "other"
                )
                entries.append(
                    RosterEntry(
                        external_id=str(member.get("user_id", "")),
                        email=member.get("email", ""),
                        name=member.get("name", "")
                        or f"{member.get('given_name', '')} {member.get('family_name', '')}".strip(),
                        role=role,
                    )
                )
            url = resp.links.get("next", {}).get("url", "")  # NRPS pagination
        return entries

    # -- AGS grade passback ----------------------------------------------------------------

    def push_grade(self, passback) -> str:
        """Publish one score to the line item Canvas bound to the content
        link. Raises on any non-2xx; the queue in passback.py owns retries."""
        token = self._access_token(SCOPE_AGS_SCORE)
        body = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scoreGiven": float(passback.score_given),
            "scoreMaximum": float(passback.score_maximum),
            "activityProgress": "Completed",
            "gradingProgress": "FullyGraded",
            "userId": passback.external_user_id,
        }
        resp = self._client.post(
            _scores_url(passback.lineitem_url),
            content=json.dumps(body),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.ims.lis.v1.score+json",
            },
        )
        resp.raise_for_status()
        return resp.headers.get("location", f"http-{resp.status_code}")

    # -- Deep Linking 2.0 -------------------------------------------------------------------

    def deep_link_response_jwt(
        self, *, deployment_id: str, data: str, content_items: list[dict]
    ) -> str:
        """The signed LtiDeepLinkingResponse the picker posts back to the
        platform's return URL. ``data`` echoes the launch's opaque token."""
        now = datetime.now(timezone.utc)
        claims = {
            "iss": self._client_id,  # the tool speaks as its client id
            "aud": self.issuer,
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "nonce": uuid.uuid4().hex,
            CLAIM_MESSAGE_TYPE: "LtiDeepLinkingResponse",
            CLAIM_VERSION: "1.3.0",
            CLAIM_DEPLOYMENT: deployment_id,
            CLAIM_DL_CONTENT_ITEMS: content_items,
        }
        if data:
            claims[CLAIM_DL_DATA] = data
        return self._tool_jwt(claims)

    @staticmethod
    def content_item(template, *, launch_url: str) -> dict:
        """One lab template as an LTI resource-link content item. The custom
        parameter is how a later launch names the template; the lineItem asks
        Canvas to create the grade column AGS will publish into."""
        return {
            "type": "ltiResourceLink",
            "title": template.title,
            "url": launch_url,
            "custom": {"palestrix_template_id": template.id},
            "lineItem": {"scoreMaximum": 100},
        }
