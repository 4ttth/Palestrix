"use client";

/*
 * Student dashboard (density 8), live: active instance first (or the launch
 * panel when none), then academy progress, the caller's ledger, and the
 * global Palestras leaderboard. Every number on screen is an API response.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Cube, RocketLaunch, Trophy } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Avatar } from "@/components/ui/avatar";
import { Countdown } from "@/components/lab/Countdown";
import { PluginSlot } from "@/components/plugins/PluginSlot";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { StateBadge } from "@/components/ui/state-badge";
import type {
  InstanceOut,
  LabTemplateOut,
  LeaderboardEntryOut,
  LedgerEntryOut,
  ModuleOut,
  PathOut,
} from "@/lib/api/types";

const ALIVE = new Set(["requested", "provisioning", "running", "stopped"]);

const REASON_LABEL: Record<string, string> = {
  "module.completed": "Finished a module",
  "flag.captured": "Captured a flag",
  "first_blood.bonus": "First blood bonus",
  "writeup.published": "Published a writeup",
  "streak.weekly": "Weekly streak checkpoint",
  "instance.extended": "Extended an instance TTL",
  "hint.unlocked": "Unlocked a hint",
  "seed.grant": "Starting grant",
};

type PathWithModules = { path: PathOut; modules: ModuleOut[] };

function usePathProgress() {
  const [data, setData] = useState<PathWithModules[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const paths = await api.get<PathOut[]>("/api/v1/academy/paths");
        const modules = await Promise.all(
          paths.map((p) =>
            api.get<ModuleOut[]>(`/api/v1/academy/paths/${p.slug}/modules`)
          )
        );
        if (!cancelled)
          setData(paths.map((path, i) => ({ path, modules: modules[i] })));
      } catch (err) {
        if (!cancelled)
          setError(err instanceof ApiError ? err : new ApiError(0, String(err)));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  return { data, error };
}

function LaunchPanel() {
  const router = useRouter();
  const { data: templates, error, loading, refetch } = useApi<LabTemplateOut[]>(
    "/api/v1/labs/templates"
  );
  const toast = useToast();
  const [launching, setLaunching] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function launch(template: LabTemplateOut) {
    setLaunching(template.id);
    setFailure(null);
    try {
      const instance = await api.post<InstanceOut>("/api/v1/instances", {
        template_id: template.id,
      });
      toast.success(
        `${template.title} is provisioning`,
        "Taking you to the lab page — the address appears when it is ready."
      );
      router.push(`/labs/${instance.id}`);
    } catch (err) {
      const text = err instanceof ApiError ? err.message : "Launch failed.";
      setFailure(text);
      // Quota denials name the quota that blocked; that detail is the
      // difference between a student waiting and a student asking for help.
      toast.error(`Could not launch ${template.title}`, text);
      setLaunching(null);
    }
  }

  return (
    <Card className="border-l-2 border-l-accent">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RocketLaunch size={18} className="text-accent" />
          Start a lab
        </CardTitle>
        <CardDescription>
          No instance is running. Launch a published environment — it arrives
          with a TTL and dies on schedule.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading && <Loading label="loading templates" />}
        {error && <LoadFailed error={error} retry={refetch} />}
        {templates && templates.length === 0 && (
          <Empty
            title="Nothing published yet"
            hint="Ask a teacher to publish a lab environment from the course manager."
          />
        )}
        {templates && templates.length > 0 && (
          <ul className="divide-y divide-border">
            {templates.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{t.title}</p>
                  <p className="mt-0.5 font-mono text-xs text-muted">
                    {t.slug} | {t.kind} | {t.access_mode} | TTL{" "}
                    {t.ttl_minutes_default}min
                  </p>
                </div>
                <Button
                  size="sm"
                  onClick={() => launch(t)}
                  disabled={launching !== null}
                >
                  {launching === t.id ? "Provisioning..." : "Launch"}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {failure && (
          <p role="alert" className="mt-3 text-[13px] text-danger">
            {failure}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardView() {
  const { user } = useSession();
  const instances = useApi<InstanceOut[]>("/api/v1/instances");
  const ledger = useApi<LedgerEntryOut[]>("/api/v1/gamification/ledger?limit=6");
  const leaderboard = useApi<LeaderboardEntryOut[]>(
    "/api/v1/gamification/leaderboard?limit=5"
  );
  const progress = usePathProgress();

  const active = (instances.data ?? []).find((i) => ALIVE.has(i.state));
  const flat = (progress.data ?? []).flatMap((p) =>
    p.modules.map((m) => ({ ...m, pathTitle: p.path.title }))
  );
  const current = flat.find((m) => !m.completed);

  return (
    <>
      <Topbar title="Dashboard" />
      <div className="space-y-6 p-4 sm:p-6">
        {/* Active instance strip: the most time-critical object on screen */}
        {instances.loading && <Loading label="checking instances" />}
        {instances.error && (
          <LoadFailed error={instances.error} retry={instances.refetch} />
        )}
        {instances.data && !active && <LaunchPanel />}
        {active && (
          <Card className="border-l-2 border-l-accent">
            <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5">
              <div className="flex items-center gap-4">
                <Cube size={22} className="text-accent" />
                <div>
                  <p className="text-sm font-semibold tracking-tight">
                    {active.template_title || active.template_slug}
                  </p>
                  <p className="mt-0.5 font-mono text-xs text-muted">
                    {active.id} on {active.node || "queue"}
                    {active.host ? ` via ${active.proto} ${active.host}:${active.port}` : ""}
                  </p>
                </div>
                <StateBadge state={active.state} />
              </div>
              <div className="flex items-center gap-5">
                {active.expires_at && (
                  <div className="text-right">
                    <p className="text-[11px] text-muted">TTL remaining</p>
                    <Countdown until={active.expires_at} className="text-lg" />
                  </div>
                )}
                <Link href={`/labs/${active.id}`}>
                  <Button size="sm">
                    Open lab
                    <ArrowRight size={14} />
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
          <div className="space-y-6">
            {/* Continue learning */}
            <Card>
              <CardHeader>
                <CardTitle>Continue learning</CardTitle>
                <CardDescription>
                  {current
                    ? `Pick up where you stopped in the ${current.pathTitle} path.`
                    : "Your academy progress across every path."}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {progress.error && <LoadFailed error={progress.error} />}
                {!progress.data && !progress.error && (
                  <Loading label="loading paths" />
                )}
                {current && (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-(--radius-input) bg-surface-2/70 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium">{current.title}</p>
                      <p className="text-xs text-muted">{current.pathTitle}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant="palestras">+{current.palestras_award} P</Badge>
                      <Link href="/academy">
                        <Button variant="outline" size="sm">Resume</Button>
                      </Link>
                    </div>
                  </div>
                )}
                {progress.data && progress.data.length === 0 && (
                  <Empty
                    title="No learning paths yet"
                    hint="Paths appear here once the academy catalog is published."
                  />
                )}
                <ul className="mt-4 space-y-3">
                  {(progress.data ?? []).map(({ path, modules }) => {
                    const done = modules.filter((m) => m.completed).length;
                    return (
                      <li
                        key={path.slug}
                        className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1"
                      >
                        <p className="text-sm font-medium">{path.title}</p>
                        <p className="font-mono text-xs tabular-nums text-muted">
                          {done}/{modules.length} modules
                        </p>
                        <Progress
                          value={modules.length ? (done / modules.length) * 100 : 0}
                          label={`${path.title} completion`}
                          className="col-span-2"
                        />
                      </li>
                    );
                  })}
                </ul>
              </CardContent>
            </Card>

            {/* Recent ledger activity */}
            <Card>
              <CardHeader>
                <CardTitle>Recent Palestras activity</CardTitle>
              </CardHeader>
              <CardContent>
                {ledger.loading && <Loading label="loading ledger" />}
                {ledger.error && (
                  <LoadFailed error={ledger.error} retry={ledger.refetch} />
                )}
                {ledger.data && ledger.data.length === 0 && (
                  <Empty
                    title="No transactions yet"
                    hint="Finish a module, capture a flag, or publish a writeup to start earning."
                  />
                )}
                {ledger.data && ledger.data.length > 0 && (
                  <ul className="divide-y divide-border text-sm">
                    {ledger.data.map((entry, i) => (
                      <li
                        key={`${entry.created_at}-${i}`}
                        className="flex items-center justify-between py-2.5"
                      >
                        <span>
                          {REASON_LABEL[entry.reason] ?? entry.reason}
                          {entry.ref && (
                            <span className="ml-2 font-mono text-xs text-muted">
                              {entry.ref}
                            </span>
                          )}
                        </span>
                        <span
                          className={
                            "font-mono text-xs " +
                            (entry.delta >= 0 ? "text-palestras" : "text-expired")
                          }
                        >
                          {entry.delta >= 0 ? "+" : ""}
                          {entry.delta} P
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6 self-start">
            {/* Leaderboard mini */}
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Trophy size={16} className="text-palestras" weight="fill" />
                  Palestras leaderboard
                </CardTitle>
              </CardHeader>
              <CardContent>
                {leaderboard.loading && <Loading label="ranking" />}
                {leaderboard.error && (
                  <LoadFailed error={leaderboard.error} retry={leaderboard.refetch} />
                )}
                {leaderboard.data && leaderboard.data.length === 0 && (
                  <Empty
                    title="Nobody on the board yet"
                    hint="Ranks appear as students start earning."
                  />
                )}
                <ol className="space-y-2.5">
                  {(leaderboard.data ?? []).map((row) => (
                    <li
                      key={row.handle}
                      className={
                        "flex items-center gap-3 rounded-(--radius-input) px-2 py-1.5 " +
                        (row.handle === user.handle ? "bg-accent-soft" : "")
                      }
                    >
                      <span className="w-5 font-mono text-xs tabular-nums text-muted">
                        {row.rank}
                      </span>
                      <Avatar handle={row.handle} size="sm" />
                      <span className="flex-1 truncate font-mono text-[13px]">
                        {row.handle}
                      </span>
                      <span className="font-mono text-[13px] tabular-nums">
                        {row.score.toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ol>
                <Link
                  href="/compete"
                  className="mt-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-accent hover:underline"
                >
                  CTF arena
                  <ArrowRight size={13} />
                </Link>
              </CardContent>
            </Card>

            {/* UI plugin slot: every installed plugin that registers a
                dashboard widget mounts here (docs/plugin-development.md). */}
            <PluginSlot
              slot="dashboard.widgets"
              viewer={{
                handle: user.handle,
                name: user.name,
                role: roleLabel(user.role),
              }}
            />
          </div>
        </div>
      </div>
    </>
  );
}

function roleLabel(role: string): "Student" | "Teacher" | "Admin" | "Superadmin" {
  switch (role) {
    case "teacher":
      return "Teacher";
    case "admin":
      return "Admin";
    case "superadmin":
      return "Superadmin";
    default:
      return "Student";
  }
}
