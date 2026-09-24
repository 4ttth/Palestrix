"use client";

/*
 * Superadmin view of the student-access overlay.
 *
 * Students reach labs over a self-hosted-key NetBird overlay whose peers are
 * ephemeral: a device is reaped an hour after it goes offline, which is what
 * keeps a cohort under the free plan's 100-peer cap without anyone tending it.
 * This console is the window onto that — how full the plan is, who is on it
 * right now — plus the manual override: free the offline slots now instead of
 * waiting out the hour.
 *
 * The reap and per-peer delete are guarded server-side: the router that
 * carries every lab, and admin devices, are never candidates. This UI mirrors
 * that with a lock rather than a delete control on protected peers, so the
 * affordance matches what the API will allow.
 */

import { useState } from "react";
import { ArrowClockwise, Broom, Lock, Trash, WifiHigh, WifiSlash } from "@phosphor-icons/react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import type { NetBirdReapOut, NetBirdStatusOut } from "@/lib/api/types";

function relativeAge(iso: string | null): string {
  if (!iso) return "never";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (secs < 90) return "just now";
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return `${Math.round(secs / 86400)}d ago`;
}

export function NetBirdConsole() {
  const status = useApi<NetBirdStatusOut>("/api/v1/admin/netbird");
  const toast = useToast();
  const [reaping, setReaping] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function reap() {
    setReaping(true);
    try {
      const out = await api.post<NetBirdReapOut>("/api/v1/admin/netbird/reap");
      if (out.reaped.length === 0) {
        toast.info("Nothing to reap", `All ${out.kept} student peer(s) are online.`);
      } else {
        toast.success(
          `Freed ${out.reaped.length} slot${out.reaped.length === 1 ? "" : "s"}`,
          `${out.kept} online student peer(s) left alone.`
        );
      }
      if (out.errors.length) {
        toast.error("Some peers could not be removed", out.errors.join("; "));
      }
      void status.refetch();
    } catch (err) {
      toast.error(
        "Reap failed",
        err instanceof ApiError ? err.message : "The request failed."
      );
    } finally {
      setReaping(false);
    }
  }

  async function removePeer(id: string, name: string) {
    setDeleting(id);
    try {
      await api.del(`/api/v1/admin/netbird/peers/${id}`);
      toast.success(`Removed ${name}`, "Its slot is free.");
      void status.refetch();
    } catch (err) {
      toast.error(
        `Could not remove ${name}`,
        err instanceof ApiError ? err.message : "The request failed."
      );
    } finally {
      setDeleting(null);
    }
  }

  const data = status.data;
  const nearCap =
    data && data.peer_limit > 0 && data.total / data.peer_limit >= 0.85;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Student access overlay (NetBird)</CardTitle>
            <CardDescription>
              {data?.network_name
                ? `Network "${data.network_name}". `
                : ""}
              Peers reap themselves an hour after going offline; reap by hand to
              free slots now.
            </CardDescription>
          </div>
          {data?.configured && (
            <Button
              variant="secondary"
              size="sm"
              loading={reaping}
              loadingLabel="Reaping"
              onClick={reap}
              disabled={data.reapable === 0}
            >
              <Broom className="size-4" aria-hidden />
              {data.reapable > 0
                ? `Reap ${data.reapable} offline`
                : "Nothing to reap"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {status.loading && <Loading label="reading overlay status" />}
        {status.error && <LoadFailed error={status.error} retry={status.refetch} />}

        {data && !data.configured && (
          <Empty
            title="Live view is off"
            hint="No NetBird API token is set, so peer status and manual reap are unavailable. The overlay still works and reaps offline peers on its own — set PALESTRIX_NETBIRD_API_TOKEN to manage it here."
          />
        )}

        {data?.configured && data.error && (
          <p className="rounded-(--radius-input) bg-expired-soft px-4 py-3 text-[13px] text-expired">
            NetBird did not answer: {data.error}
          </p>
        )}

        {data?.configured && !data.error && (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat
                label="Peers"
                value={`${data.total} / ${data.peer_limit}`}
                warn={!!nearCap}
              />
              <Stat label="Connected" value={String(data.connected)} />
              <Stat label="Students" value={String(data.students)} />
              <Stat label="Reapable" value={String(data.reapable)} />
            </div>

            {nearCap && (
              <p className="mb-4 rounded-(--radius-input) bg-palestras-soft px-4 py-2.5 text-[13px] text-palestras">
                Close to the {data.peer_limit}-peer cap. Reaping the offline
                slots buys room without touching anyone connected.
              </p>
            )}

            {data.peers.length === 0 ? (
              <Empty
                title="No peers"
                hint="Nobody has joined the overlay yet."
              />
            ) : (
              <ul className="plx-stagger divide-y divide-border">
                {data.peers.map((peer, i) => (
                  <li
                    key={peer.id}
                    style={{ ["--plx-index" as string]: i }}
                    className="flex items-center justify-between gap-3 py-2.5"
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      {peer.connected ? (
                        <WifiHigh
                          className="size-4 shrink-0 text-running"
                          aria-label="connected"
                        />
                      ) : (
                        <WifiSlash
                          className="size-4 shrink-0 text-muted"
                          aria-label="offline"
                        />
                      )}
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {peer.name}
                          {peer.is_protected && (
                            <Badge variant="accent" className="ml-2">
                              infrastructure
                            </Badge>
                          )}
                        </p>
                        <p className="font-mono text-[11px] text-muted">
                          {peer.ip}
                          {" · "}
                          {peer.connected ? "online" : `seen ${relativeAge(peer.last_seen)}`}
                          {peer.os ? ` · ${peer.os}` : ""}
                        </p>
                      </div>
                    </div>
                    {peer.is_protected ? (
                      <span
                        className="shrink-0 p-1.5 text-muted"
                        title="The lab router / an admin device — protected from reaping"
                      >
                        <Lock className="size-4" aria-hidden />
                      </span>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="shrink-0 text-danger hover:bg-danger/10"
                        loading={deleting === peer.id}
                        onClick={() => removePeer(peer.id, peer.name)}
                      >
                        <Trash className="size-4" aria-hidden />
                        Remove
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  value,
  warn = false,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-(--radius-input) border border-border bg-surface-2/40 px-3 py-2.5",
        warn && "border-palestras/50 bg-palestras-soft"
      )}
    >
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <p
        className={cn(
          "mt-0.5 font-mono text-lg tabular-nums",
          warn && "text-palestras"
        )}
      >
        {value}
      </p>
    </div>
  );
}
