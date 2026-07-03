"use client";

/*
 * Malware sandbox module, live (Phase 6). Every panel renders real
 * /api/v1/sandbox data: submit a sample, watch the detonation trace stream in
 * over SSE, read the verdict, static pre-check, IOCs, MITRE mapping, and pull
 * archived artifacts. The demo detonator runs real static analysis and a
 * clearly-labelled synthetic dynamic trace; a deployment with an isolated host
 * (status.live) streams genuine behavior. Nothing here is mock data — when the
 * module is disabled the API answers 501 and this view says so honestly.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Brain,
  CheckCircle,
  DownloadSimple,
  Fingerprint,
  Gear,
  Globe,
  HardDrives,
  Question,
   ShareNetwork,
  ShieldWarning,
  Skull,
  TreeStructure,
  UploadSimple,
  Warning,
} from "@phosphor-icons/react";
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
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError, API_ORIGIN, readToken } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { streamSandboxEvents } from "@/lib/api/stream";
import { ago, bytes } from "@/lib/format";
import type {
  SandboxArtifactOut,
  SandboxEventOut,
  SandboxReportOut,
  SandboxStatusOut,
  SandboxVerdict,
} from "@/lib/api/types";

const verdictBadge: Record<SandboxVerdict, "expired" | "palestras" | "running" | "neutral"> = {
  malicious: "expired",
  suspicious: "palestras",
  clean: "running",
  unknown: "neutral",
};

const verdictBar: Record<SandboxVerdict, string> = {
  malicious: "bg-expired",
  suspicious: "bg-palestras",
  clean: "bg-running",
  unknown: "bg-muted",
};

const LIVE_STATES = new Set(["queued", "static", "detonating"]);

const categoryIcon = {
  process: TreeStructure,
  file: HardDrives,
  network: Globe,
  memory: Brain,
  static: Fingerprint,
  system: Gear,
} as const;

const levelClass: Record<string, string> = {
  info: "text-muted",
  ok: "text-running",
  warn: "text-palestras",
  alert: "text-expired",
};

export function SandboxView() {
  const { user } = useSession();
  const status = useApi<SandboxStatusOut>("/api/v1/sandbox/status");
  const reports = useApi<SandboxReportOut[]>("/api/v1/sandbox/reports");
  const [selected, setSelected] = useState<string | null>(null);
  const notDeployed = status.error?.status === 501 || status.data?.enabled === false;

  const selectedReport = useMemo(
    () => reports.data?.find((r) => r.id === selected) ?? null,
    [reports.data, selected]
  );

  return (
    <>
      <Topbar title="Malware sandbox" />
      <div className="space-y-6 p-6">
        {notDeployed ? (
          <NotDeployed />
        ) : (
          status.data && <StatusBanner status={status.data} />
        )}

        <div className="grid gap-6 xl:grid-cols-[1fr_1.4fr]">
          <div className="space-y-6">
            <SubmitPanel
              disabled={notDeployed}
              maxMb={status.data?.max_sample_mb ?? 100}
              onSubmitted={(report) => {
                setSelected(report.id);
                void reports.refetch();
              }}
            />
            <ReportsList
              reports={reports}
              selected={selected}
              onSelect={setSelected}
              notDeployed={notDeployed}
            />
          </div>

          <div className="space-y-6">
            {selectedReport ? (
              <ReportDetail
                report={selectedReport}
                canExport={user.role === "admin" || user.role === "superadmin"}
                isOwner={selectedReport.submitter_handle === user.handle}
                onChanged={() => void reports.refetch()}
              />
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle>Analysis report</CardTitle>
                  <CardDescription>
                    Pick a submission to see its verdict, behavior trace, and
                    indicators.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Empty
                    title="No report selected"
                    hint="Submit a sample or choose one from the queue on the left."
                  />
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function NotDeployed() {
  return (
    <div className="flex items-start gap-3 rounded-(--radius-card) border border-border bg-surface px-5 py-4">
      <ShieldWarning size={20} className="mt-0.5 shrink-0 text-palestras" />
      <div>
        <p className="text-sm font-semibold tracking-tight">
          The sandbox module is not deployed in this environment
        </p>
        <p className="mt-1 max-w-[70ch] text-[13px] leading-relaxed text-muted">
          The API answers <span className="font-mono">501 Not Implemented</span>{" "}
          until the dedicated, network-isolated detonation host is enabled.
          Isolation and hardening requirements are in docs/sandbox-security.md.
        </p>
      </div>
    </div>
  );
}

function StatusBanner({ status }: { status: SandboxStatusOut }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-(--radius-card) border border-border bg-surface px-5 py-3 text-[13px]">
      <span className="flex items-center gap-2 font-medium">
        <ShieldWarning size={16} className="text-accent" />
        Detonation engine
      </span>
      <Badge variant={status.live ? "running" : "neutral"}>
        {status.live ? "live isolated host" : "demo detonator"}
      </Badge>
      <span className="text-muted">
        {status.live
          ? "Samples detonate on the isolated host; behavior is real."
          : "Static analysis is real; the dynamic trace is simulated. Deploy a coordinator host for live detonation."}
      </span>
      <span className="ml-auto font-mono text-xs text-muted">
        max {status.max_sample_mb} MB · {status.wall_clock_seconds}s wall clock
      </span>
    </div>
  );
}

function SubmitPanel({
  disabled,
  maxMb,
  onSubmitted,
}: {
  disabled: boolean;
  maxMb: number;
  onSubmitted: (report: SandboxReportOut) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function submit() {
    if (!file) return;
    if (file.size > maxMb * 1024 * 1024) {
      setFailure(`That file is over the ${maxMb} MB limit.`);
      return;
    }
    setSubmitting(true);
    setFailure(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const report = await api.postForm<SandboxReportOut>(
        "/api/v1/sandbox/samples",
        form
      );
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onSubmitted(report);
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Submission failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Detonate a sample</CardTitle>
        <CardDescription>
          Runs on an isolated host with no route to lab or campus networks.
          Analyses are private to your account until you share them.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <label
          aria-disabled={disabled}
          className={
            "flex cursor-pointer flex-col items-center gap-2 rounded-(--radius-input) border border-dashed border-border bg-surface-2/50 px-6 py-8 text-center transition-colors hover:border-accent " +
            (disabled ? "pointer-events-none opacity-60" : "")
          }
        >
          <UploadSimple size={26} className="text-muted" />
          <span className="text-sm font-medium">
            {file ? file.name : disabled ? "Submissions are closed" : "Choose a file to analyze"}
          </span>
          <span className="text-xs text-muted">
            {file
              ? bytes(file.size)
              : `Up to ${maxMb} MB. Archives are extracted with the password “infected”.`}
          </span>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setFailure(null);
            }}
          />
        </label>

        <div className="mt-4 flex items-center gap-3">
          <Button disabled={disabled || !file || submitting} onClick={submit}>
            {submitting ? "Detonating…" : "Submit for analysis"}
          </Button>
          {file && !submitting && (
            <button
              type="button"
              className="text-[13px] text-muted underline underline-offset-2"
              onClick={() => {
                setFile(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
            >
              Clear
            </button>
          )}
        </div>

        {failure && <p className="mt-3 text-[13px] text-danger">{failure}</p>}

        <div className="mt-4 flex items-start gap-2.5 rounded-(--radius-input) bg-expired-soft p-3 text-[13px] leading-relaxed text-expired">
          <ShieldWarning size={17} className="mt-0.5 shrink-0" />
          Handle real malware only inside this module. Never download samples to
          your own machine.
        </div>
      </CardContent>
    </Card>
  );
}

function ReportsList({
  reports,
  selected,
  onSelect,
  notDeployed,
}: {
  reports: ReturnType<typeof useApi<SandboxReportOut[]>>;
  selected: string | null;
  onSelect: (id: string) => void;
  notDeployed: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Detonation queue</CardTitle>
        <CardDescription>Your submissions and shared team reports.</CardDescription>
      </CardHeader>
      <CardContent>
        {reports.loading && <Loading label="loading reports" />}
        {reports.error && !notDeployed && (
          <LoadFailed error={reports.error} retry={reports.refetch} />
        )}
        {reports.data && reports.data.length === 0 && (
          <Empty
            title="The detonation queue is empty"
            hint="Submit your first sample to see its behavior trace here."
          />
        )}
        {reports.data && reports.data.length > 0 && (
          <ul className="divide-y divide-border">
            {reports.data.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => onSelect(r.id)}
                  className={
                    "flex w-full items-center gap-3 py-2.5 text-left transition-colors " +
                    (selected === r.id ? "" : "hover:bg-surface-2/40")
                  }
                >
                  <VerdictGlyph verdict={r.verdict} state={r.state} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-[13px]">{r.filename}</p>
                    <p className="truncate font-mono text-[11px] text-muted">
                      {r.id} · {ago(r.created_at)}
                      {r.resubmission && " · resubmission"}
                    </p>
                  </div>
                  {LIVE_STATES.has(r.state) ? (
                    <Badge variant="provisioning">{r.state}</Badge>
                  ) : (
                    <Badge variant={verdictBadge[r.verdict]}>{r.verdict}</Badge>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function VerdictGlyph({
  verdict,
  state,
}: {
  verdict: SandboxVerdict;
  state: string;
}) {
  if (LIVE_STATES.has(state))
    return <Gear size={18} className="shrink-0 animate-spin text-provisioning" />;
  if (state === "failed") return <Warning size={18} className="shrink-0 text-expired" />;
  const Icon =
    verdict === "malicious"
      ? Skull
      : verdict === "suspicious"
        ? Warning
        : verdict === "clean"
          ? CheckCircle
          : Question;
  const color =
    verdict === "malicious"
      ? "text-expired"
      : verdict === "suspicious"
        ? "text-palestras"
        : verdict === "clean"
          ? "text-running"
          : "text-muted";
  return <Icon size={18} weight="fill" className={`shrink-0 ${color}`} />;
}

function ReportDetail({
  report,
  canExport,
  isOwner,
  onChanged,
}: {
  report: SandboxReportOut;
  canExport: boolean;
  isOwner: boolean;
  onChanged: () => void;
}) {
  const s = report.static;
  const live = LIVE_STATES.has(report.state);

  async function toggleShare() {
    try {
      await api.post(`/api/v1/sandbox/reports/${report.id}/share`, {
        shared: !report.shared,
      });
      onChanged();
    } catch {
      /* surfaced by the list refetch failing loudly elsewhere */
    }
  }

  return (
    <div className="space-y-6">
      <Card
        className={
          report.verdict === "malicious"
            ? "border-l-2 border-l-expired"
            : report.verdict === "suspicious"
              ? "border-l-2 border-l-palestras"
              : "border-l-2 border-l-running"
        }
      >
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="flex items-center gap-2">
                <span className="truncate">{report.filename}</span>
                {live ? (
                  <Badge variant="provisioning">{report.state}</Badge>
                ) : report.state === "failed" ? (
                  <Badge variant="failed">failed</Badge>
                ) : (
                  <Badge variant={verdictBadge[report.verdict]}>
                    {report.verdict}
                  </Badge>
                )}
                {report.resubmission && <Badge variant="neutral">resubmission</Badge>}
              </CardTitle>
              <p className="mt-1 break-all font-mono text-[11px] text-muted">
                sha256 {report.sample_sha256}
              </p>
            </div>
            {isOwner && !live && (
              <Button variant="outline" size="sm" onClick={toggleShare}>
                <ShareNetwork size={15} />
                {report.shared ? "Shared with team" : "Share with team"}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {report.state === "failed" ? (
            <p className="rounded-(--radius-input) bg-expired-soft px-4 py-3 text-[13px] text-expired">
              Analysis failed: {report.error ?? "unknown error"}
            </p>
          ) : (
            <>
              <ScoreMeter verdict={report.verdict} score={report.score} />
              {report.summary && (
                <p className="text-[13px] leading-relaxed text-muted">
                  {report.summary}
                </p>
              )}
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-3">
                <Field label="File type" value={s.file_type ?? "—"} />
                <Field label="Size" value={bytes(report.size)} />
                <Field
                  label="Entropy"
                  value={s.entropy != null ? `${s.entropy.toFixed(2)} b/B` : "—"}
                />
                <Field label="Family" value={report.family ?? "none"} />
                <Field label="Packed" value={s.packed ? "yes" : "no"} />
                <Field label="Detonator" value={report.detonator || "—"} />
              </dl>
              {report.mitre.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] text-muted">ATT&amp;CK</span>
                  {report.mitre.map((t) => (
                    <Badge key={t} variant="accent">
                      {t}
                    </Badge>
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {report.state !== "failed" && (
        <>
          <StaticFindings report={report} />
          <BehaviorTrace reportId={report.id} live={live} />
          <Artifacts reportId={report.id} canExport={canExport} />
        </>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-muted">{label}</dt>
      <dd className="truncate font-mono text-[13px]">{value}</dd>
    </div>
  );
}

function ScoreMeter({ verdict, score }: { verdict: SandboxVerdict; score: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[13px]">
        <span className="text-muted">Threat score</span>
        <span className="font-mono tabular-nums">{score}/100</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-2">
        <div
          className={`h-full rounded-full ${verdictBar[verdict]}`}
          style={{ width: `${Math.max(2, score)}%` }}
        />
      </div>
    </div>
  );
}

function StaticFindings({ report }: { report: SandboxReportOut }) {
  const iocs = report.iocs ?? {};
  const notes = report.static.notes ?? [];
  const hasIocs =
    (iocs.urls?.length ?? 0) + (iocs.ips?.length ?? 0) + (iocs.domains?.length ?? 0) >
    0;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Fingerprint size={15} className="text-accent" />
          Static pre-check
        </CardTitle>
        <CardDescription>
          Real analysis of the bytes, performed before any execution.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {notes.length > 0 && (
          <ul className="space-y-1.5">
            {notes.map((n, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px]">
                <Warning size={15} className="mt-0.5 shrink-0 text-palestras" />
                {n}
              </li>
            ))}
          </ul>
        )}
        {hasIocs ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <IocColumn title="URLs" items={iocs.urls ?? []} />
            <IocColumn title="IPs" items={iocs.ips ?? []} />
            <IocColumn title="Domains" items={iocs.domains ?? []} />
          </div>
        ) : (
          <p className="text-[13px] text-muted">No network indicators in the static image.</p>
        )}
      </CardContent>
    </Card>
  );
}

function IocColumn({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">
        {title} ({items.length})
      </p>
      {items.length === 0 ? (
        <p className="font-mono text-[12px] text-muted">—</p>
      ) : (
        <ul className="space-y-0.5">
          {items.slice(0, 12).map((v, i) => (
            <li key={i} className="truncate font-mono text-[12px]" title={v}>
              {v}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function BehaviorTrace({ reportId, live }: { reportId: string; live: boolean }) {
  const initial = useApi<SandboxEventOut[]>(
    `/api/v1/sandbox/reports/${reportId}/events`
  );
  const [streamed, setStreamed] = useState<SandboxEventOut[]>([]);

  // Follow the live stream while the run is still detonating; the one-shot
  // fetch above already carries everything for a settled run.
  useEffect(() => {
    setStreamed([]);
    if (!live) return;
    return streamSandboxEvents(reportId, {
      onEvent: (e) => setStreamed((prev) => [...prev, e]),
      onState: () => void initial.refetch(),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId, live]);

  const events = useMemo(() => {
    const bySeq = new Map<number, SandboxEventOut>();
    for (const e of initial.data ?? []) bySeq.set(e.seq, e);
    for (const e of streamed) bySeq.set(e.seq, e);
    return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
  }, [initial.data, streamed]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TreeStructure size={15} className="text-accent" />
          Behavior trace
        </CardTitle>
        <CardDescription>
          Process, file-system, network, and memory events in order.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {initial.loading && events.length === 0 && <Loading label="loading trace" />}
        {events.length === 0 && !initial.loading && (
          <Empty title="No events yet" hint="Events appear as the detonation proceeds." />
        )}
        {events.length > 0 && (
          <ol className="space-y-2">
            {events.map((e) => {
              const Icon = categoryIcon[e.category] ?? Gear;
              return (
                <li key={e.seq} className="flex items-start gap-3">
                  <Icon
                    size={15}
                    className={`mt-0.5 shrink-0 ${levelClass[e.level] ?? "text-muted"}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className={`text-[13px] leading-snug ${e.level === "alert" ? "text-expired" : ""}`}>
                      {e.msg}
                    </p>
                    {e.category !== "system" && (
                      <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
                        {e.category}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function Artifacts({
  reportId,
  canExport,
}: {
  reportId: string;
  canExport: boolean;
}) {
  const artifacts = useApi<SandboxArtifactOut[]>(
    `/api/v1/sandbox/reports/${reportId}/artifacts`
  );

  async function download(key: string) {
    // Authenticated fetch (the export route needs the bearer token), then hand
    // the blob to the browser's downloader.
    const token = readToken();
    const resp = await fetch(
      `${API_ORIGIN}/api/v1/sandbox/reports/${reportId}/artifacts/download?key=${encodeURIComponent(key)}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    );
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = key.split("/").pop() ?? "artifact";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Artifacts</CardTitle>
        <CardDescription>
          Archived report, capture, and dropped files.
          {!canExport && " Export is available to administrators only."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {artifacts.loading && <Loading label="loading artifacts" />}
        {artifacts.error && (
          <LoadFailed error={artifacts.error} retry={artifacts.refetch} />
        )}
        {artifacts.data && artifacts.data.length === 0 && (
          <Empty title="No artifacts archived" hint="Artifacts appear once analysis completes." />
        )}
        {artifacts.data && artifacts.data.length > 0 && (
          <ul className="divide-y divide-border">
            {artifacts.data.map((a) => (
              <li key={a.key} className="flex items-center gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-[13px]">
                    {a.key.split("/").pop()}
                  </p>
                  <p className="font-mono text-[11px] text-muted">{bytes(a.size)}</p>
                </div>
                {canExport && (
                  <Button variant="outline" size="sm" onClick={() => download(a.key)}>
                    <DownloadSimple size={14} />
                    Export
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
