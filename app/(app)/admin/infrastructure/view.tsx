"use client";

/*
 * Admin infrastructure console (Administrator / Superadministrator only —
 * every endpoint here requires infra:manage, and the API answers 403 for
 * anyone else). Live composition: active instance providers, the
 * cross-tenant instance registry with real TTLs, the ISO library in object
 * storage, and tenant quota usage. "Run reaper now" forces a reap +
 * reconcile pass.
 */

import { useRef, useState } from "react";
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
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { bytes, dateOnly } from "@/lib/format";
import { stateLabel } from "@/lib/labels";
import type {
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
      await api.postForm("/api/v1/admin/isos", form);
      setNotice(`Stored ${file.name}.`);
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

            {/* Tenants */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HardDrives size={15} className="text-accent" />
                  Tenants and quotas
                </CardTitle>
              </CardHeader>
              <CardContent>
                {tenants.loading && <Loading label="loading tenants" />}
                {tenants.error && (
                  <LoadFailed error={tenants.error} retry={tenants.refetch} />
                )}
                {tenants.data && tenants.data.length === 0 && (
                  <Empty
                    title="No tenants"
                    hint="Create one through POST /api/v1/admin/tenants."
                  />
                )}
                {tenants.data && tenants.data.length > 0 && (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Tenant</TableHead>
                        <TableHead className="text-right">Instances</TableHead>
                        <TableHead className="text-right">Network</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tenants.data.map((t) => (
                        <TableRow key={t.id}>
                          <TableCell className="font-mono text-xs">{t.id}</TableCell>
                          <TableCell className="text-right font-mono text-xs tabular-nums">
                            {t.instances_active}/{t.instance_quota}
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs text-muted">
                            {t.network_cidr || "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
