"use client";

/*
 * Active ephemeral lab view, live: the instance from GET /instances/{id},
 * the provisioning log over the authenticated SSE stream, the TTL from the
 * server's expiry timestamp, and the stop / extend / destroy actions wired
 * to their endpoints. GUI labs surface the console endpoint; headless labs
 * surface the ssh line. Nothing on this screen is sample data.
 */

import { useState } from "react";
import Link from "next/link";
import { ArrowClockwise, ArrowLeft, Power, Trash } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Countdown } from "@/components/lab/Countdown";
import { GradingCard } from "@/components/lab/GradingCard";
import { ProvisioningLog } from "@/components/lab/ProvisioningLog";
import { ConnectHelp } from "@/components/lab/ConnectHelp";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { clock } from "@/lib/format";
import { stateLabel } from "@/lib/labels";
import type { InstanceOut } from "@/lib/api/types";

const EXTEND_COST = 150; // PALESTRIX_INSTANCE_EXTEND_COST_PALESTRAS default

export function LabView({ instanceId }: { instanceId: string }) {
  const { refreshSummary } = useSession();
  const instance = useApi<InstanceOut>(`/api/v1/instances/${instanceId}`);
  const [busy, setBusy] = useState<"extend" | "stop" | "destroy" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function act(
    kind: "extend" | "stop" | "destroy",
    run: () => Promise<unknown>
  ) {
    setBusy(kind);
    setFailure(null);
    try {
      await run();
      await instance.refetch();
      void refreshSummary(); // extend spends Palestras
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : `${kind} failed.`);
    } finally {
      setBusy(null);
    }
  }

  if (instance.loading && !instance.data) {
    return (
      <>
        <Topbar title="Active lab" />
        <div className="p-4 sm:p-6">
          <Loading label="loading instance" />
        </div>
      </>
    );
  }

  if (instance.error) {
    return (
      <>
        <Topbar title="Active lab" />
        <div className="p-4 sm:p-6">
          {instance.error.status === 404 ? (
            <Empty
              title="No such instance"
              hint="It may have been reaped already — ephemeral means ephemeral."
            >
              <Link href="/dashboard" className="mt-4 inline-block">
                <Button variant="outline" size="sm">
                  <ArrowLeft size={14} />
                  Back to dashboard
                </Button>
              </Link>
            </Empty>
          ) : (
            <LoadFailed error={instance.error} retry={instance.refetch} />
          )}
        </div>
      </>
    );
  }

  const inst = instance.data!;
  const running = inst.state === "running";
  const settled = inst.state === "expired" || inst.state === "failed";
  const gui = inst.access_mode === "gui";

  return (
    <>
      <Topbar title="Active lab" />
      <div className="space-y-6 p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold tracking-tight">
                {inst.template_title || inst.template_slug}
              </h2>
              <Badge variant={inst.state}>{stateLabel[inst.state]}</Badge>
            </div>
            <p className="mt-1 font-mono text-xs text-muted">
              {inst.id} | tenant {inst.tenant_id} | node {inst.node || "queue"} |{" "}
              {inst.template_slug}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              title={`Costs ${EXTEND_COST} Palestras`}
              disabled={!running || busy !== null}
              onClick={() =>
                act("extend", () =>
                  api.post(`/api/v1/instances/${inst.id}/extend`, { minutes: 30 })
                )
              }
            >
              <ArrowClockwise size={15} />
              {busy === "extend" ? "Extending..." : "Extend 30 min"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!running || busy !== null}
              onClick={() =>
                act("stop", () => api.post(`/api/v1/instances/${inst.id}/stop`))
              }
            >
              <Power size={15} />
              {busy === "stop" ? "Stopping..." : "Stop"}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={settled || busy !== null}
              onClick={() =>
                act("destroy", () => api.del(`/api/v1/instances/${inst.id}`))
              }
            >
              <Trash size={15} />
              {busy === "destroy" ? "Destroying..." : "Destroy"}
            </Button>
          </div>
        </div>

        {failure && (
          <p role="alert" className="rounded-(--radius-input) bg-expired-soft px-4 py-3 text-[13px] text-expired">
            {failure}
          </p>
        )}

        <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
          <div className="space-y-6">
            {/* Console region: noVNC iframe mounts here for GUI labs */}
            <Card>
              <CardHeader>
                <CardTitle>Connection</CardTitle>
                <CardDescription>
                  {settled
                    ? "This instance is gone; its credentials died with it."
                    : gui
                      ? "GUI lab: open the console endpoint below in the noVNC viewer."
                      : `This lab is headless. It runs on an isolated network — join NetBird, then connect over ${inst.proto || "ssh"}.`}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {running && inst.host ? (
                  <div className="flex flex-wrap items-center gap-3">
                    <code className="rounded-(--radius-input) bg-surface-2 px-4 py-2.5 font-mono text-sm">
                      {gui
                        ? `${inst.proto}://${inst.host}:${inst.port}`
                        : `ssh student@${inst.host} -p ${inst.port}`}
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={async () => {
                        await navigator.clipboard.writeText(
                          gui
                            ? `${inst.proto}://${inst.host}:${inst.port}`
                            : `ssh student@${inst.host} -p ${inst.port}`
                        );
                        setCopied(true);
                        setTimeout(() => setCopied(false), 1500);
                      }}
                    >
                      {copied ? "Copied" : gui ? "Copy endpoint" : "Copy command"}
                    </Button>
                  </div>
                ) : (
                  <p className="font-mono text-sm text-muted">
                    {settled
                      ? "no endpoint — instance destroyed"
                      : inst.state === "stopped"
                        ? "instance stopped — the endpoint returns if an admin restarts it"
                        : "endpoint appears once provisioning finishes"}
                  </p>
                )}
                <div className="mt-3">
                  <ConnectHelp
                    endpoint={
                      running && inst.host
                        ? gui
                          ? `${inst.proto}://${inst.host}:${inst.port}`
                          : `ssh student@${inst.host} -p ${inst.port}`
                        : null
                    }
                  />
                </div>
                {running && !gui && (
                  <p className="mt-3 text-[13px] text-muted">
                    Credentials were issued when the instance started and die
                    with it. GUI labs replace this panel with the noVNC console.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Provisioning log</CardTitle>
                <CardDescription>
                  Every line is a real event from the orchestration worker,
                  streamed over SSE.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ProvisioningLog
                  instanceId={inst.id}
                  onSettled={() => void instance.refetch()}
                />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <GradingCard instanceId={inst.id} running={running} />
            <Card>
              <CardHeader>
                <CardTitle>Time to live</CardTitle>
              </CardHeader>
              <CardContent>
                {inst.expires_at && !settled ? (
                  <>
                    <Countdown until={inst.expires_at} className="text-3xl" />
                    <p className="mt-2 text-[13px] leading-relaxed text-muted">
                      Started {clock(inst.created_at)}. At zero the reaper stops
                      and destroys this instance and releases your tenant
                      quota. Extending costs {EXTEND_COST} P per 30 minutes.
                    </p>
                  </>
                ) : (
                  <p className="text-[13px] leading-relaxed text-muted">
                    {settled
                      ? "The TTL elapsed or the instance was destroyed. Quota has been released."
                      : "No expiry recorded."}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Instance details</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2.5 text-sm">
                  {(
                    [
                      ["Template", inst.template_slug],
                      ["Kind", inst.kind],
                      ["Access", inst.access_mode],
                      ["Tenant", inst.tenant_id],
                      ["Node", inst.node || "—"],
                      ["Owner", inst.owner_handle],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between gap-3">
                      <dt className="text-[13px] text-muted">{label}</dt>
                      <dd className="truncate font-mono text-[13px]">{value}</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
