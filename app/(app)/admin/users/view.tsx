"use client";

/*
 * Users console (Administrator / Superadministrator — users:manage). The
 * missing half of account management: self-registration only ever creates
 * students, so teacher/admin accounts, role changes, and tenant placement
 * all happen here. RBAC rules mirrored from the API: admins manage students
 * and teachers; admin/superadmin accounts and roles require superadmin.
 */

import { useMemo, useState, type FormEvent } from "react";
import { UserPlus } from "@phosphor-icons/react";
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
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { dateOnly } from "@/lib/format";
import type { Role, TenantOut, UserOut } from "@/lib/api/types";

const ROLE_BADGE: Record<Role, "neutral" | "accent" | "palestras" | "expired"> = {
  student: "neutral",
  teacher: "accent",
  admin: "palestras",
  superadmin: "expired",
};

const NEW_USER = {
  name: "",
  handle: "",
  email: "",
  password: "",
  role: "student" as Role,
  tenant_id: "",
};

export function UsersView() {
  const { user: me } = useSession();
  const users = useApi<UserOut[]>("/api/v1/users");
  const tenants = useApi<TenantOut[]>("/api/v1/admin/tenants");
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [busyRow, setBusyRow] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const isSuperadmin = me.role === "superadmin";
  const forbidden = me.role !== "admin" && !isSuperadmin;

  const activeTenants = useMemo(
    () => (tenants.data ?? []).filter((t) => !t.archived),
    [tenants.data]
  );

  const visible = useMemo(() => {
    const rows = users.data ?? [];
    const q = filter.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((u) =>
      [u.handle, u.name, u.email, u.role, u.tenant_id ?? ""].some((v) =>
        v.toLowerCase().includes(q)
      )
    );
  }, [users.data, filter]);

  /** Admins may not touch admin/superadmin rows; nobody edits their own row
   * here (locking yourself out mid-session helps no one). */
  function editable(u: UserOut): boolean {
    if (u.id === me.id) return false;
    if (isSuperadmin) return true;
    return u.role !== "admin" && u.role !== "superadmin";
  }

  async function changeRole(u: UserOut, role: Role) {
    setBusyRow(u.id);
    setNotice(null);
    try {
      await api.patch<UserOut>(`/api/v1/users/${u.id}/role`, { role });
      setNotice({ ok: true, text: `${u.handle} is now a ${role}.` });
      void users.refetch();
    } catch (err) {
      setNotice({
        ok: false,
        text: err instanceof ApiError ? err.message : "Role change failed.",
      });
    } finally {
      setBusyRow(null);
    }
  }

  async function changeTenant(u: UserOut, tenantId: string) {
    setBusyRow(u.id);
    setNotice(null);
    try {
      await api.patch<UserOut>(`/api/v1/users/${u.id}/tenant`, {
        tenant_id: tenantId === "" ? null : tenantId,
      });
      setNotice({
        ok: true,
        text:
          tenantId === ""
            ? `${u.handle} is no longer assigned to a tenant.`
            : `${u.handle} assigned to ${tenantId}.`,
      });
      void users.refetch();
    } catch (err) {
      setNotice({
        ok: false,
        text: err instanceof ApiError ? err.message : "Tenant change failed.",
      });
    } finally {
      setBusyRow(null);
    }
  }

  if (forbidden) {
    return (
      <>
        <Topbar title="Users" />
        <div className="p-4 sm:p-6">
          <Empty
            title="Administrators only"
            hint="This console requires the users:manage capability (docs/rbac-matrix.md)."
          />
        </div>
      </>
    );
  }

  return (
    <>
      <Topbar title="Users" />
      <div className="space-y-6 p-4 sm:p-6">
        <CreateUserCard
          isSuperadmin={isSuperadmin}
          tenants={activeTenants}
          onCreated={(u) => {
            setNotice({ ok: true, text: `Account ${u.handle} created as ${u.role}.` });
            void users.refetch();
          }}
        />

        {notice && (
          <p
            aria-live="polite"
            className={
              "rounded-(--radius-input) px-4 py-3 font-mono text-xs " +
              (notice.ok ? "bg-accent-soft text-accent" : "bg-expired-soft text-expired")
            }
          >
            {notice.text}
          </p>
        )}

        <Card>
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>All accounts</CardTitle>
              <CardDescription>
                Role changes apply on the user&apos;s next request — no re-login
                needed. Tenant decides where their instances launch.
              </CardDescription>
            </div>
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by handle, email, role..."
              aria-label="Filter users"
              className="h-9 w-full text-[13px] sm:w-64"
            />
          </CardHeader>
          <CardContent>
            {users.loading && <Loading label="loading accounts" />}
            {users.error && <LoadFailed error={users.error} retry={users.refetch} />}
            {users.data && visible.length === 0 && (
              <Empty
                title="No matching accounts"
                hint="Adjust the filter, or create the account above."
              />
            )}
            {visible.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Handle</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Tenant</TableHead>
                    <TableHead className="text-right">Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="font-mono text-xs">
                        {u.handle}
                        {u.id === me.id && (
                          <Badge variant="accent" className="ml-2">
                            you
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="max-w-40 truncate">{u.name}</TableCell>
                      <TableCell className="max-w-52 truncate font-mono text-xs text-muted">
                        {u.email}
                      </TableCell>
                      <TableCell>
                        {editable(u) ? (
                          <Select
                            aria-label={`Role for ${u.handle}`}
                            value={u.role}
                            disabled={busyRow === u.id}
                            onChange={(e) => void changeRole(u, e.target.value as Role)}
                            className="w-36"
                          >
                            <option value="student">student</option>
                            <option value="teacher">teacher</option>
                            {isSuperadmin && <option value="admin">admin</option>}
                            {isSuperadmin && (
                              <option value="superadmin">superadmin</option>
                            )}
                          </Select>
                        ) : (
                          <Badge variant={ROLE_BADGE[u.role]}>{u.role}</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {editable(u) ? (
                          <Select
                            aria-label={`Tenant for ${u.handle}`}
                            value={u.tenant_id ?? ""}
                            disabled={busyRow === u.id || tenants.loading}
                            onChange={(e) => void changeTenant(u, e.target.value)}
                            className="w-44"
                          >
                            <option value="">unassigned</option>
                            {activeTenants.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.id}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <span className="font-mono text-xs text-muted">
                            {u.tenant_id ?? "—"}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted">
                        {u.created_at ? dateOnly(u.created_at) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function CreateUserCard({
  isSuperadmin,
  tenants,
  onCreated,
}: {
  isSuperadmin: boolean;
  tenants: TenantOut[];
  onCreated: (u: UserOut) => void;
}) {
  const [draft, setDraft] = useState(NEW_USER);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      const created = await api.post<UserOut>("/api/v1/users", {
        name: draft.name.trim(),
        handle: draft.handle.trim(),
        email: draft.email.trim(),
        password: draft.password,
        role: draft.role,
        tenant_id: draft.tenant_id === "" ? null : draft.tenant_id,
      });
      setDraft(NEW_USER);
      onCreated(created);
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Creation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserPlus size={15} className="text-accent" />
          Create an account
        </CardTitle>
        <CardDescription>
          Hand the credentials to the user; they can rotate the password and
          enroll a passkey in Settings. Self-registration at /register always
          creates students — teachers{isSuperadmin ? ", admins," : ""} and
          staff accounts start here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={create} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <div className="grid gap-1.5">
            <Label htmlFor="nu-name">Full name</Label>
            <Input
              id="nu-name"
              value={draft.name}
              required
              minLength={2}
              placeholder="Teodoro Dela Cruz"
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className="h-9 text-[13px]"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="nu-handle">Handle</Label>
            <Input
              id="nu-handle"
              value={draft.handle}
              required
              pattern="[a-z0-9_.-]{3,32}"
              title="3-32 chars: lowercase letters, digits, dot, dash, underscore"
              placeholder="sir.delacruz"
              onChange={(e) => setDraft({ ...draft, handle: e.target.value })}
              className="h-9 font-mono text-[13px]"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="nu-email">Email</Label>
            <Input
              id="nu-email"
              type="email"
              value={draft.email}
              required
              placeholder="delacruz@example.edu"
              onChange={(e) => setDraft({ ...draft, email: e.target.value })}
              className="h-9 font-mono text-[13px]"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="nu-password">Temporary password</Label>
            <Input
              id="nu-password"
              type="text"
              value={draft.password}
              required
              minLength={12}
              title="At least 12 characters"
              placeholder="12+ characters"
              onChange={(e) => setDraft({ ...draft, password: e.target.value })}
              className="h-9 font-mono text-[13px]"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="nu-role">Role</Label>
            <Select
              id="nu-role"
              value={draft.role}
              onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}
            >
              <option value="student">student</option>
              <option value="teacher">teacher</option>
              {isSuperadmin && <option value="admin">admin</option>}
              {isSuperadmin && <option value="superadmin">superadmin</option>}
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="nu-tenant">Tenant</Label>
            <Select
              id="nu-tenant"
              value={draft.tenant_id}
              onChange={(e) => setDraft({ ...draft, tenant_id: e.target.value })}
            >
              <option value="">unassigned</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id}
                </option>
              ))}
            </Select>
          </div>
          {failure && (
            <p role="alert" className="text-[13px] text-danger sm:col-span-2 xl:col-span-3">
              {failure}
            </p>
          )}
          <div className="sm:col-span-2 xl:col-span-3">
            <Button type="submit" size="sm" disabled={busy}>
              {busy ? "Creating..." : "Create account"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
