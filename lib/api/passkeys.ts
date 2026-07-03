/*
 * Passkey ceremonies (Phase 5): SimpleWebAuthn on the browser side,
 * py_webauthn on the API (backend/palestrix/webauthn_flow.py). The API
 * hands options as a JSON string; the verified credential goes back the
 * same way.
 */

import {
  startAuthentication,
  startRegistration,
} from "@simplewebauthn/browser";
import { api } from "./client";
import type { TokenOut } from "./types";

/** Enroll a passkey for the signed-in account (requires a session token). */
export async function enrollPasskey(): Promise<void> {
  const { options } = await api.post<{ options: string }>(
    "/api/v1/auth/webauthn/register/options"
  );
  const credential = await startRegistration({
    optionsJSON: JSON.parse(options),
  });
  await api.post("/api/v1/auth/webauthn/register/verify", {
    credential: JSON.stringify(credential),
  });
}

/** Sign in with a passkey; resolves to a session token. */
export async function passkeyLogin(email: string): Promise<TokenOut> {
  const { options } = await api.post<{ options: string }>(
    "/api/v1/auth/webauthn/login/options",
    { email }
  );
  const credential = await startAuthentication({
    optionsJSON: JSON.parse(options),
  });
  return api.post<TokenOut>(
    `/api/v1/auth/webauthn/login/verify?email=${encodeURIComponent(email)}`,
    { credential: JSON.stringify(credential) }
  );
}
