"use client";

/*
 * Admin infrastructure console (Administrator / Superadministrator only —
 * every endpoint here requires infra:manage, and the API answers 403 for
 * anyone else). Live composition: active instance providers, the
 * cross-tenant instance registry with real TTLs, the ISO library in object
 * storage, and tenant quota usage. "Run reaper now" forces a reap +
 * reconcile pass.
 */

import { useRef, useState, type FormEvent } from "react";
import { Cpu, HardDrives, UploadSimple } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Countdown } from "@/components/lab/Countdown";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api/client";
import { useApi, type Async } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { bytes, dateOnly } from "@/lib/format";
import { stateLabel } from "@/lib/labels";
import type {
  CloudOut,
  InstanceOut,
  ProviderOut,
  StoredObjectOut,
  TenantOut,
} from "@/lib/api/types";

const ALIVE = new Set(["requested", "provisioning", "running", "stopped"]);

export function InfrastructureView() {
  const { user } = useSession();
  const providers = useApi<ProviderOut[]>("/api/v1/admin/providers");
  const registry = useApi<InstanceOut[]>("/api/v1/instances?all_tenants=true");
  const isos = useApi<StoredObjectOut[]>("/api/v1/admin/isos");
  const tenants = useApi<TenantOut[]>("/api/v1/admin/tenants");
  const cloud = useApi<CloudOut>("/api/v1/admin/cloud");
  const [reaping, setReaping] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const forbidden = user.role !== "admin" && user.role !== "superadmin";

  async function runReaper() {
    setReaping(true);
    setNotice(null);
    try {
      const result = await api.post<{ reaped: string[]; count: number }>(
        "/api/v1/admin/reaper/run"
      );
      setNotice(
        result.count === 0
          ? "Reaper pass complete: nothing was overdue."
          : `Reaper destroyed ${result.count} expired instance${result.count === 1 ? "" : "s"}: ${result.reaped.join(", ")}`
      );
      void registry.refetch();
      void tenants.refetch();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Reaper run failed.");
    } finally {
      setReaping(false);
    }
  }

  async function uploadIso(file: File) {
    setUploading(true);
    setNotice(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api.postForm<{
        stored: string;
        forwarded_to: string | null;
        forward_error?: string;
      }>("/api/v1/admin/isos", form);
      setNotice(
        result.forward_error
          ? `Stored ${file.name}, but cluster forwarding failed: ${result.forward_error}`
          : result.forwarded_to
            ? `Stored ${file.name} and forwarded it to cluster storage (${result.forwarded_to}).`
            : `Stored ${file.name}.`
      );
      void isos.refetch();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "ISO upload failed.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (forbidden) {
    return (
      <>
        <Topbar title="Infrastructure" />
        <div className="p-6">
          <Empty
            title="Administrators only"
            hint="This console requires the infra:manage capability (docs/rbac-matrix.md)."
          />
        </div>
      </>
    );
  }

  return (
    <>
      <Topbar title="Infrastructure" />
      <div className="space-y-6 p-6">
        {/* Instance providers: the adapter-level truth from the registry */}
        {providers.loading && <Loading label="loading providers" />}
        {providers.error && (
          <LoadFailed error={providers.error} retry={providers.refetch} />
        )}
        <div className="grid gap-4 lg:grid-cols-3">
          {(providers.data ?? []).map((p) => (
            <Card key={p.name}>
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle className="font-mono">{p.name}</CardTitle>
                  <CardDescription>Instance provider</CardDescription>
                </div>
                <Badge variant="running">active</Badge>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-[11px] text-muted">Kinds</dt>
                    <dd className="font-mono text-[13px]">{p.kinds.join(", ")}</dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-muted">Live instances</dt>
                    <dd className="font-mono tabular-nums">{p.instances_active}</dd>
                  </div>
                </dl>
                {p.name === "demo" && (
                  <p className="mt-3 flex items-start gap-2 text-[13px] leading-relaxed text-muted">
                    <Cpu size={15} className="mt-0.5 shrink-0" />
                    Development placeholder. Proxmox and Docker adapters take
                    over their kinds when configured (backend/README.md).
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>

        {notice && (
          <p
            aria-live="polite"
            className="rounded-(--radius-input) bg-accent-soft px-4 py-3 font-mono text-xs text-accent"
          >
            {notice}
          </p>
        )}

        <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
          {/* Instance registry */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Instance registry</CardTitle>
                <CardDescription>
                  Every ephemeral instance across all tenants, live from the
                  orchestration service.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={runReaper} disabled={reaping}>
                {reaping ? "Reaping..." : "Run reaper now"}
              </Button>
            </CardHeader>
            <CardContent>
              {registry.loading && <Loading label="loading registry" />}
              {registry.error && (
                <LoadFailed error={registry.error} retry={registry.refetch} />
              )}
              {registry.data && registry.data.length === 0 && (
                <Empty
                  title="The registry is empty"
                  hint="Instances appear the moment a student launches a lab."
                />
              )}
              {registry.data && registry.data.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Owner</TableHead>
                      <TableHead>Template</TableHead>
                      <TableHead>Kind</TableHead>
                      <TableHead>Node</TableHead>
                      <TableHead>State</TableHead>
                      <TableHead className="text-right">TTL</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {registry.data.map((i) => (
                      <TableRow key={i.id}>
                        <TableCell className="font-mono text-xs">{i.id}</TableCell>
                        <TableCell className="font-mono text-xs">
                          {i.owner_handle}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {i.template_slug}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted">
                          {i.kind === "vm" ? "VM" : i.kind === "container" ? "CT" : i.kind}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted">
                          {i.node || "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant={i.state}>{stateLabel[i.state]}</Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {ALIVE.has(i.state) && i.expires_at ? (
                            <Countdown until={i.expires_at} className="text-xs" />
                          ) : (
                            "00:00:00"
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <div className="space-y-6">
            {/* ISO library */}
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle>ISO library</CardTitle>
                  <CardDescription>
                    Consumed by the Proxmox API when building VM templates.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  disabled={uploading}
                  onClick={() => fileRef.current?.click()}
                >
                  <UploadSimple size={15} />
                  {uploading ? "Uploading..." : "Upload ISO"}
                </Button>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".iso"
                  className="sr-only"
                  aria-label="Upload ISO"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void uploadIso(f);
                  }}
                />
              </CardHeader>
              <CardContent>
                {isos.loading && <Loading label="listing objects" />}
                {isos.error && <LoadFailed error={isos.error} retry={isos.refetch} />}
                {isos.data && isos.data.length === 0 && (
                  <Empty
                    title="No ISOs stored"
                    hint="Upload installers here for admins to build VM templates from."
                  />
                )}
                <ul className="divide-y divide-border">
                  {(isos.data ?? []).map((iso) => (
                    <li key={iso.key} className="py-2.5">
                      <p className="truncate font-mono text-[13px]">{iso.key}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted">
                        {bytes(iso.size)}
                        {iso.last_modified && ` | ${dateOnly(iso.last_modified)}`}
                      </p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {/* Tenants: full lifecycle against the Phase 7 cloud layer */}
            <TenantsCard tenants={tenants} cloud={cloud} />
          </div>
        </div>
      </div>
    </>
  );
}

const TENANT_DRAFT = {
  id: "",
  name: "",
  instance_quota: "3",
  cpu_cap: "48",
  ram_cap_gb: "96",
};

/*
 * Tenant lifecycle against the Phase 7 multitenant cloud layer: create
 * (materializes VLAN + CIDR through the active adapter), quota edits
 * (pushed to OpenNebula/CloudStack when one fronts the hypervisor), and
 * archive (refused by the API while the tenant holds active instances).
 * VLAN and CIDR are fixed at creation — no edit surface for them.
 */
function TenantsCard({
  tenants,
  cloud,
}: {
  tenants: Async<TenantOut[]>;
  cloud: Async<CloudOut>;
}) {
  const [draft, setDraft] = useState(TENANT_DRAFT);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [editing, setEditing] = useState<TenantOut | null>(null);
  const [caps, setCaps] = useState(TENANT_DRAFT);

  async function act(work: () => Promise<string>) {
    setBusy(true);
    setNote(null);
    try {
      setNote(await work());
      void tenants.refetch();
      void cloud.refetch();
    } catch (err) {
      setNote(err instanceof ApiError ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  }

  function createTenant(e: FormEvent) {
    e.preventDefault();
    void act(async () => {
      const t = await api.post<TenantOut>("/api/v1/admin/tenants", {
        id: draft.id.trim(),
        name: draft.name.trim() || draft.id.trim(),
        instance_quota: Number(draft.instance_quota),
        cpu_cap: Number(draft.cpu_cap),
        ram_cap_gb: Number(draft.ram_cap_gb),
      });
      setDraft(TENANT_DRAFT);
      return `Created ${t.id}: vlan ${t.vlan_id ?? "—"}, ${t.network_cidr}.`;
    });
  }

  function saveQuotas(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    void act(async () => {
      const t = await api.patch<TenantOut>(`/api/v1/admin/tenants/${editing.id}`, {
        instance_quota: Number(caps.instance_quota),
        cpu_cap: Number(caps.cpu_cap),
        ram_cap_gb: Number(caps.ram_cap_gb),
      });
      setEditing(null);
      return `Quotas for ${t.id}: ${t.instance_quota} instances, ${t.cpu_cap} vCPU, ${t.ram_cap_gb} GB RAM.`;
    });
  }

  function archiveTenant(t: TenantOut) {
    if (
      !window.confirm(
        `Archive tenant ${t.id}? Its members can no longer launch; history and its network stay reserved.`
      )
    ) {
      return;
    }
    void act(async () => {
      await api.del<TenantOut>(`/api/v1/admin/tenants/${t.id}`);
      return `Archived ${t.id}.`;
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HardDrives size={15} className="text-accent" />
          Tenants and quotas
        </CardTitle>
        <CardDescription>
          Cloud layer:{" "}
          <span className="font-mono text-foreground">
            {cloud.data?.name ?? "…"}
          </span>
          {cloud.data && cloud.data.tenants_archived > 0 && (
            <> — {cloud.data.tenants_archived} archived</>
          )}
          . Quotas are enforced at launch; archiving needs an idle tenant.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={createTenant} className="mb-4 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <Input
              value={draft.id}
              onChange={(e) => setDraft({ ...draft, id: e.target.value })}
              placeholder="tenant-id"
              aria-label="Tenant id"
              pattern="[a-z0-9-]{3,64}"
              title="3-64 chars: lowercase letters, digits, hyphens"
              required
              className="h-9 font-mono text-xs"
            />
            <Input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="Display name"
              aria-label="Tenant name"
              className="h-9 text-xs"
            />
          </div>
          <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2">
            <Input
              type="number"
              min={0}
              value={draft.instance_quota}
              onChange={(e) =>
                setDraft({ ...draft, instance_quota: e.target.value })
              }
              aria-label="Instance quota"
              title="Instance quota"
              className="h-9 font-mono text-xs"
            />
            <Input
              type="number"
              min={0}
              value={draft.cpu_cap}
              onChange={(e) => setDraft({ ...draft, cpu_cap: e.target.value })}
              aria-label="vCPU cap"
              title="vCPU cap"
              className="h-9 font-mono text-xs"
            />
            <Input
              type="number"
              min={0}
              value={draft.ram_cap_gb}
              onChange={(e) =>
                setDraft({ ...draft, ram_cap_gb: e.target.value })
              }
              aria-label="RAM cap (GB)"
              title="RAM cap (GB)"
              className="h-9 font-mono text-xs"
            />
            <Button type="submit" size="sm" disabled={busy}>
              Create
            </Button>
          </div>
          <p className="font-mono text-[11px] text-muted">
            caps: instances | vCPU | RAM GB
          </p>
        </form>

        {note && (
          <p
            aria-live="polite"
            className="mb-3 rounded-(--radius-input) bg-accent-soft px-3 py-2 font-mono text-[11px] text-accent"
          >
            {note}
          </p>
        )}

        {tenants.loading && <Loading label="loading tenants" />}
        {tenants.error && (
          <LoadFailed error={tenants.error} retry={tenants.refetch} />
        )}
        {tenants.data && tenants.data.length === 0 && (
          <Empty title="No tenants" hint="Create the first one above." />
        )}
        <ul className="divide-y divide-border">
          {(tenants.data ?? []).map((t) => (
            <li key={t.id} className="py-3">
              <div className="flex items-center justify-between gap-2">
                <p className="flex items-center gap-2 truncate font-mono text-[13px]">
                  {t.id}
                  {t.archived && <Badge variant="expired">archived</Badge>}
                </p>
                {!t.archived && (
                  <span className="flex shrink-0 gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => {
                        setEditing(t);
                        setCaps({
                          ...TENANT_DRAFT,
                          instance_quota: String(t.instance_quota),
                          cpu_cap: String(t.cpu_cap),
                          ram_cap_gb: String(t.ram_cap_gb),
                        });
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => archiveTenant(t)}
                    >
                      Archive
                    </Button>
                  </span>
                )}
              </div>
              <p className="mt-1 font-mono text-[11px] tabular-nums text-muted">
                {t.instances_active}/{t.instance_quota} inst | {t.cpu_active}/
                {t.cpu_cap} vCPU | {t.ram_active_gb}/{t.ram_cap_gb} GB
              </p>
              <p className="font-mono text-[11px] text-muted">
                {t.network_cidr || "—"}
                {t.vlan_id != null && ` | vlan ${t.vlan_id}`}
              </p>
              {editing?.id === t.id && (
                <form
                  onSubmit={saveQuotas}
                  className="mt-2 grid grid-cols-[1fr_1fr_1fr_auto_auto] gap-1.5"
                >
                  <Input
                    type="number"
                    min={0}
                    value={caps.instance_quota}
                    onChange={(e) =>
                      setCaps({ ...caps, instance_quota: e.target.value })
                    }
                    aria-label="Instance quota"
                    title="Instance quota"
                    className="h-8 font-mono text-xs"
                  />
                  <Input
                    type="number"
                    min={0}
                    value={caps.cpu_cap}
                    onChange={(e) => setCaps({ ...caps, cpu_cap: e.target.value })}
                    aria-label="vCPU cap"
                    title="vCPU cap"
                    className="h-8 font-mono text-xs"
                  />
                  <Input
                    type="number"
                    min={0}
                    value={caps.ram_cap_gb}
                    onChange={(e) =>
                      setCaps({ ...caps, ram_cap_gb: e.target.value })
                    }
                    aria-label="RAM cap (GB)"
                    title="RAM cap (GB)"
                    className="h-8 font-mono text-xs"
                  />
                  <Button type="submit" size="sm" disabled={busy}>
                    Save
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditing(null)}
                  >
                    Cancel
                  </Button>
                </form>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
