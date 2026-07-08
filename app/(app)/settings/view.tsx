"use client";

/*
 * Profile settings, self-service: display name, password rotation, passkey
 * enrollment/removal, and personal API keys. Identity fields (handle, email,
 * role, tenant) are staff-managed in the users console, so they render
 * read-only here.
 */

import { useState, type FormEvent } from "react";
import { Fingerprint, Key, Plus, Trash } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar } from "@/components/ui/avatar";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { enrollPasskey } from "@/lib/api/passkeys";
import { useSession } from "@/lib/api/session";
import { dateOnly } from "@/lib/format";
import type { ApiKeyCreatedOut, ApiKeyOut, PasskeyOut, UserOut } from "@/lib/api/types";

type Note = { ok: boolean; text: string } | null;

export function SettingsView() {
  return (
    <>
      <Topbar title="Settings" />
      <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
        <ProfileCard />
        <PasswordCard />
        <PasskeysCard />
        <ApiKeysCard />
      </div>
    </>
  );
}

function Notice({ note }: { note: Note }) {
  if (!note) return null;
  return (
    <p
      aria-live="polite"
      className={
        "rounded-(--radius-input) px-3 py-2 font-mono text-[11px] " +
        (note.ok ? "bg-accent-soft text-accent" : "bg-expired-soft text-expired")
      }
    >
      {note.text}
    </p>
  );
}

function ProfileCard() {
  const { user } = useSession();
  const [name, setName] = useState(user.name);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Note>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    try {
      const updated = await api.patch<UserOut>("/api/v1/auth/me", {
        name: name.trim(),
      });
      setName(updated.name);
      setNote({ ok: true, text: "Name saved. It shows after the next reload." });
    } catch (err) {
      setNote({
        ok: false,
        text: err instanceof ApiError ? err.message : "Saving failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>
          Handle, email, role, and tenant are identity — an administrator
          changes those from the users console.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Avatar handle={user.handle} size="lg" />
          <dl className="grid flex-1 grid-cols-2 gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-4">
            <div>
              <dt className="text-[11px] text-muted">Handle</dt>
              <dd className="font-mono">{user.handle}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-muted">Role</dt>
              <dd>
                <Badge variant="accent">{user.role}</Badge>
              </dd>
            </div>
            <div>
              <dt className="text-[11px] text-muted">Email</dt>
              <dd className="truncate font-mono">{user.email}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-muted">Tenant</dt>
              <dd className="font-mono">{user.tenant_id ?? "unassigned"}</dd>
            </div>
          </dl>
        </div>
        <form onSubmit={save} className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
          <div className="grid min-w-56 flex-1 gap-1.5">
            <Label htmlFor="profile-name">Display name</Label>
            <Input
              id="profile-name"
              value={name}
              required
              minLength={2}
              onChange={(e) => setName(e.target.value)}
              className="h-9 text-[13px]"
            />
          </div>
          <Button type="submit" size="sm" disabled={busy || name.trim() === user.name}>
            {busy ? "Saving..." : "Save name"}
          </Button>
          <div className="w-full">
            <Notice note={note} />
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Note>(null);

  async function change(e: FormEvent) {
    e.preventDefault();
    if (next !== confirm) {
      setNote({ ok: false, text: "New passwords do not match." });
      return;
    }
    setBusy(true);
    setNote(null);
    try {
      await api.post("/api/v1/auth/password", {
        current_password: current,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      setNote({ ok: true, text: "Password changed." });
    } catch (err) {
      setNote({
        ok: false,
        text: err instanceof ApiError ? err.message : "Change failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Password</CardTitle>
        <CardDescription>At least 12 characters. Existing sessions stay signed in.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={change} className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pw-current">Current password</Label>
            <Input
              id="pw-current"
              type="password"
              value={current}
              required
              autoComplete="current-password"
              onChange={(e) => setCurrent(e.target.value)}
              className="h-9 text-[13px]"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pw-next">New password</Label>
            <Input
              id="pw-next"
              type="password"
              value={next}
              required
              minLength={12}
              autoComplete="new-password"
              onChange={(e) => setNext(e.target.value)}
              className="h-9 text-[13px]"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pw-confirm">Repeat new password</Label>
            <Input
              id="pw-confirm"
              type="password"
              value={confirm}
              required
              minLength={12}
              autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)}
              className="h-9 text-[13px]"
            />
          </div>
          <div className="sm:col-span-3">
            <Notice note={note} />
          </div>
          <div className="sm:col-span-3">
            <Button type="submit" size="sm" disabled={busy}>
              {busy ? "Changing..." : "Change password"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function PasskeysCard() {
  const passkeys = useApi<PasskeyOut[]>("/api/v1/auth/webauthn/credentials");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Note>(null);

  async function enroll() {
    setBusy(true);
    setNote(null);
    try {
      await enrollPasskey();
      setNote({ ok: true, text: "Passkey enrolled." });
      void passkeys.refetch();
    } catch (err) {
      setNote({
        ok: false,
        text:
          err instanceof ApiError
            ? err.message
            : "Passkey enrollment was cancelled or failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Remove this passkey? You can enroll a new one anytime.")) {
      return;
    }
    setBusy(true);
    setNote(null);
    try {
      await api.del(`/api/v1/auth/webauthn/credentials/${id}`);
      void passkeys.refetch();
    } catch (err) {
      setNote({
        ok: false,
        text: err instanceof ApiError ? err.message : "Removal failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Fingerprint size={15} className="text-accent" />
            Passkeys
          </CardTitle>
          <CardDescription>
            Phishing-resistant sign-in. Enrollment needs a secure origin
            (HTTPS) matching the API&apos;s relying-party settings.
          </CardDescription>
        </div>
        <Button size="sm" disabled={busy} onClick={() => void enroll()}>
          <Plus size={14} />
          Enroll
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <Notice note={note} />
        {passkeys.loading && <Loading label="loading passkeys" />}
        {passkeys.error && (
          <LoadFailed error={passkeys.error} retry={passkeys.refetch} />
        )}
        {passkeys.data && passkeys.data.length === 0 && (
          <Empty
            title="No passkeys enrolled"
            hint="Enroll one to sign in without a password."
          />
        )}
        <ul className="divide-y divide-border">
          {(passkeys.data ?? []).map((p) => (
            <li key={p.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[13px]">
                  {p.transports.length > 0 ? p.transports.join(", ") : "platform key"}
                </p>
                <p className="font-mono text-[11px] text-muted">
                  enrolled {dateOnly(p.created_at)}
                </p>
              </div>
              <button
                type="button"
                title="Remove passkey"
                aria-label="Remove passkey"
                disabled={busy}
                onClick={() => void remove(p.id)}
                className="rounded-(--radius-input) p-1.5 text-muted transition-colors hover:bg-expired-soft hover:text-expired"
              >
                <Trash size={14} />
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ApiKeysCard() {
  const keys = useApi<ApiKeyOut[]>("/api/v1/auth/api-keys");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Note>(null);
  const [revealed, setRevealed] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    setRevealed(null);
    try {
      const created = await api.post<ApiKeyCreatedOut>("/api/v1/auth/api-keys", {
        name: name.trim() || "my key",
        scopes: [],
      });
      setRevealed(created.key);
      setName("");
      void keys.refetch();
    } catch (err) {
      setNote({
        ok: false,
        text: err instanceof ApiError ? err.message : "Creation failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function revoke(key: ApiKeyOut) {
    if (!window.confirm(`Revoke key ${key.prefix}...? Machines using it stop working.`)) {
      return;
    }
    setBusy(true);
    setNote(null);
    try {
      await api.del(`/api/v1/auth/api-keys/${key.id}`);
      void keys.refetch();
    } catch (err) {
      setNote({
        ok: false,
        text: err instanceof ApiError ? err.message : "Revocation failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Key size={15} className="text-accent" />
          API keys
        </CardTitle>
        <CardDescription>
          For scripts against /api/v1 (docs/public-api.md). Keys without
          scopes read only what you own; scoped keys are minted via the API.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={create} className="flex gap-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="key name, e.g. grading-script"
            aria-label="API key name"
            className="h-9 text-[13px]"
          />
          <Button type="submit" size="sm" disabled={busy}>
            Create
          </Button>
        </form>

        {revealed && (
          <p className="break-all rounded-(--radius-input) bg-accent-soft px-3 py-2 font-mono text-[11px] text-accent">
            Copy it now — shown exactly once: {revealed}
          </p>
        )}
        <Notice note={note} />

        {keys.loading && <Loading label="loading keys" />}
        {keys.error && <LoadFailed error={keys.error} retry={keys.refetch} />}
        {keys.data && keys.data.length === 0 && (
          <Empty title="No API keys" hint="Create one for scripted access." />
        )}
        <ul className="divide-y divide-border">
          {(keys.data ?? []).map((k) => (
            <li key={k.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-[13px] font-medium">
                  {k.name}
                  {k.revoked && <Badge variant="expired">revoked</Badge>}
                </p>
                <p className="font-mono text-[11px] text-muted">
                  {k.prefix}... · {k.scopes.length > 0 ? k.scopes.join(", ") : "ownership-scoped"} ·{" "}
                  {dateOnly(k.created_at)}
                </p>
              </div>
              {!k.revoked && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => void revoke(k)}
                >
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
