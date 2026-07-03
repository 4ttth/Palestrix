"use client";

/*
 * Malware sandbox module. The API surface exists (/api/v1/sandbox/*) but
 * answers 501 until the isolated detonation host ships in Phase 6
 * (docs/sandbox-security.md) — so this view asks the live endpoint and
 * renders exactly what it learns: reports when the module is deployed, an
 * honest "not deployed" state otherwise. No sample traces masquerade as
 * analyses.
 */

import { ShieldWarning, UploadSimple } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { useApi } from "@/lib/api/hooks";

type SandboxReport = {
  id: string;
  file: string;
  verdict: "malicious" | "suspicious" | "clean";
  submitted: string;
};

const verdictVariant = {
  malicious: "expired",
  suspicious: "palestras",
  clean: "running",
} as const;

export function SandboxView() {
  const reports = useApi<SandboxReport[]>("/api/v1/sandbox/reports");
  const notDeployed = reports.error?.status === 501;

  return (
    <>
      <Topbar title="Malware sandbox" />
      <div className="space-y-6 p-6">
        {notDeployed && (
          <div className="flex items-start gap-3 rounded-(--radius-card) border border-border bg-surface px-5 py-4">
            <ShieldWarning size={20} className="mt-0.5 shrink-0 text-palestras" />
            <div>
              <p className="text-sm font-semibold tracking-tight">
                The sandbox module is not deployed in this environment
              </p>
              <p className="mt-1 max-w-[70ch] text-[13px] leading-relaxed text-muted">
                The API answers <span className="font-mono">501 Not Implemented</span>{" "}
                until the dedicated, network-isolated detonation host arrives in
                Phase 6. Isolation and hardening requirements are specified in
                docs/sandbox-security.md.
              </p>
            </div>
          </div>
        )}

        <div className="grid gap-6 xl:grid-cols-[1fr_1.6fr]">
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Detonate a sample</CardTitle>
                <CardDescription>
                  Runs on an isolated host with no route to lab or campus
                  networks. Analyses are private to your account.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div
                  aria-disabled={notDeployed}
                  className="flex flex-col items-center gap-2 rounded-(--radius-input) border border-dashed border-border bg-surface-2/50 px-6 py-10 text-center opacity-60"
                >
                  <UploadSimple size={26} className="text-muted" />
                  <span className="text-sm font-medium">
                    {notDeployed
                      ? "Submissions open when the module deploys"
                      : "Drop a file to analyze"}
                  </span>
                  <span className="text-xs text-muted">
                    Up to 100 MB. Archives are extracted with a password of
                    &quot;infected&quot;.
                  </span>
                </div>
                <div className="mt-4 flex items-start gap-2.5 rounded-(--radius-input) bg-expired-soft p-3 text-[13px] leading-relaxed text-expired">
                  <ShieldWarning size={17} className="mt-0.5 shrink-0" />
                  Handle real malware only inside this module. Never download
                  samples to your own machine.
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Recent analyses</CardTitle>
              <CardDescription>
                File-system and network traces stream here per submission.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {reports.loading && <Loading label="asking the sandbox module" />}
              {reports.error && !notDeployed && (
                <LoadFailed error={reports.error} retry={reports.refetch} />
              )}
              {(notDeployed || (reports.data && reports.data.length === 0)) && (
                <Empty
                  title="The detonation queue is empty"
                  hint={
                    notDeployed
                      ? "Behavior traces — process trees, file-system events, network flows — render here once the Phase 6 module is live."
                      : "Submit your first sample to see behavior traces here."
                  }
                />
              )}
              {reports.data && reports.data.length > 0 && (
                <ul className="divide-y divide-border">
                  {reports.data.map((a) => (
                    <li key={a.id} className="flex items-center gap-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-mono text-[13px]">{a.file}</p>
                        <p className="font-mono text-[11px] text-muted">
                          {a.id} at {a.submitted}
                        </p>
                      </div>
                      <Badge variant={verdictVariant[a.verdict]}>{a.verdict}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
