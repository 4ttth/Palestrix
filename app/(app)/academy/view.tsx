"use client";

/*
 * Academy, live: paths from GET /academy/paths, each roadmap from
 * GET /academy/paths/{slug}/modules with per-caller completion. Module
 * states derive from the completion flags: done = completed, current =
 * first incomplete, locked = everything after (modules unlock in order).
 * Completing the current module posts to the API and refreshes the
 * Palestras balance in the topbar.
 */

import { useEffect, useState } from "react";
import { CheckCircle, Circle, Lock, SealCheck } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { Markdown } from "@/components/ui/markdown";
import type { ModuleDetailOut, ModuleOut, PathOut } from "@/lib/api/types";

type ModuleState = "done" | "current" | "locked";

const stateIcon: Record<ModuleState, React.ReactNode> = {
  done: <CheckCircle size={17} weight="fill" className="text-running" />,
  current: <Circle size={17} weight="bold" className="text-accent" />,
  locked: <Lock size={17} className="text-muted" />,
};

function deriveStates(modules: ModuleOut[]): ModuleState[] {
  let currentSeen = false;
  return modules.map((m) => {
    if (m.completed) return "done";
    if (!currentSeen) {
      currentSeen = true;
      return "current";
    }
    return "locked";
  });
}

type PathWithModules = { path: PathOut; modules: ModuleOut[] };

export function AcademyView() {
  const { refreshSummary } = useSession();
  const paths = useApi<PathOut[]>("/api/v1/academy/paths");
  const [byPath, setByPath] = useState<PathWithModules[] | null>(null);
  const [reading, setReading] = useState<ModuleDetailOut | null>(null);
  const [readingId, setReadingId] = useState<string | null>(null);
  const [modulesError, setModulesError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [completing, setCompleting] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    if (!paths.data) return;
    let cancelled = false;
    (async () => {
      try {
        const modules = await Promise.all(
          paths.data!.map((p) =>
            api.get<ModuleOut[]>(`/api/v1/academy/paths/${p.slug}/modules`)
          )
        );
        if (cancelled) return;
        setByPath(paths.data!.map((path, i) => ({ path, modules: modules[i] })));
        setSelected((s) => s ?? paths.data![0]?.slug ?? null);
      } catch (err) {
        if (!cancelled)
          setModulesError(
            err instanceof ApiError ? err : new ApiError(0, String(err))
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [paths.data]);

  const active = byPath?.find((p) => p.path.slug === selected) ?? null;
  const activeStates = active ? deriveStates(active.modules) : [];
  const activeDone = active
    ? active.modules.filter((m) => m.completed).length
    : 0;

  // The list carries enough to decide what to show; the body and the
  // caller's standing against the lab cost a query each, so they are
  // fetched only when a module is actually opened.
  async function open(moduleId: string) {
    setReadingId(moduleId);
    setReading(null);
    setFailure(null);
    try {
      setReading(
        await api.get<ModuleDetailOut>(`/api/v1/academy/modules/${moduleId}`)
      );
    } catch (err) {
      setReadingId(null);
      setFailure(
        err instanceof ApiError ? err.message : "Could not open that module."
      );
    }
  }

  async function complete(moduleId: string) {
    setCompleting(moduleId);
    setFailure(null);
    try {
      await api.post(`/api/v1/academy/modules/${moduleId}/complete`);
      // Refresh this path's modules and the topbar balance.
      if (active) {
        const fresh = await api.get<ModuleOut[]>(
          `/api/v1/academy/paths/${active.path.slug}/modules`
        );
        setByPath((rows) =>
          (rows ?? []).map((r) =>
            r.path.slug === active.path.slug ? { ...r, modules: fresh } : r
          )
        );
      }
      void refreshSummary();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Completion failed.");
    } finally {
      setCompleting(null);
    }
  }

  return (
    <>
      <Topbar title="Academy" />
      <div className="space-y-6 p-4 sm:p-6">
        {paths.loading && <Loading label="loading paths" />}
        {paths.error && <LoadFailed error={paths.error} retry={paths.refetch} />}
        {modulesError && <LoadFailed error={modulesError} />}
        {paths.data && paths.data.length === 0 && (
          <Empty
            title="No learning paths published"
            hint="The academy catalog is empty. Seed the development data (python -m palestrix.seed) or publish paths through the API."
          />
        )}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {(byPath ?? []).map(({ path, modules }) => {
            const done = modules.filter((m) => m.completed).length;
            const certified = modules.length > 0 && done === modules.length;
            return (
              <Card key={path.slug}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle>{path.title}</CardTitle>
                    {certified && (
                      <Badge variant="running">
                        <SealCheck size={13} weight="fill" />
                        Complete
                      </Badge>
                    )}
                  </div>
                  <CardDescription>
                    {modules.length} modules, about {path.hours} hours
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between text-xs text-muted">
                    <span>Progress</span>
                    <span className="font-mono tabular-nums">
                      {done}/{modules.length}
                    </span>
                  </div>
                  <Progress
                    value={modules.length ? (done / modules.length) * 100 : 0}
                    label={`${path.title} completion`}
                    className="mt-2"
                  />
                  <Button
                    variant={
                      path.slug === selected
                        ? "secondary"
                        : done > 0 && !certified
                          ? "primary"
                          : "outline"
                    }
                    size="sm"
                    className="mt-4 w-full"
                    onClick={() => setSelected(path.slug)}
                  >
                    {path.slug === selected
                      ? "Viewing roadmap"
                      : certified
                        ? "Review path"
                        : done > 0
                          ? "Continue"
                          : "Start path"}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {readingId && (
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <CardTitle>{reading?.title ?? "Loading lesson"}</CardTitle>
                  {reading?.summary && (
                    <CardDescription>{reading.summary}</CardDescription>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setReadingId(null);
                    setReading(null);
                  }}
                >
                  Back to roadmap
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {!reading ? (
                <Loading />
              ) : (
                <>
                  {reading.lab && (
                    <div className="mb-5 rounded-(--radius-card) border border-border bg-surface-2/50 px-4 py-3 text-[13px]">
                      <p className="font-medium">
                        Hands-on: {reading.lab.title || reading.lab.slug}
                      </p>
                      <p className="mt-1 leading-relaxed text-muted">
                        {!reading.lab.available
                          ? "This lab has not been imported on this deployment yet, so the module can be completed without it."
                          : !reading.lab.scheme_published
                            ? "Grading for this lab is still in draft, so the module can be completed without passing it."
                            : reading.lab.passed
                              ? `Passed with ${reading.lab.best_percent}% (${reading.lab.pass_percent}% required).`
                              : reading.lab.best_percent === null
                                ? `Launch the lab and pass the automated check — ${reading.lab.pass_percent}% required.`
                                : `Best check so far ${reading.lab.best_percent}%; ${reading.lab.pass_percent}% required.`}
                      </p>
                    </div>
                  )}
                  {reading.body ? (
                    <div className="max-w-[72ch]">
                      <Markdown source={reading.body} />
                    </div>
                  ) : (
                    <Empty
                      title="This lesson has not been written yet"
                      hint="The module still counts toward the path; the material is on its way."
                    />
                  )}

                  <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-border pt-4">
                    {reading.completed ? (
                      <Badge variant="running">Completed</Badge>
                    ) : (
                      <Button
                        onClick={() => complete(reading.id)}
                        disabled={completing !== null || Boolean(reading.locked_reason)}
                      >
                        {completing === reading.id
                          ? "Recording..."
                          : `Mark complete (+${reading.palestras_award} P)`}
                      </Button>
                    )}
                    {!reading.completed && reading.locked_reason && (
                      <p className="text-[13px] text-muted">{reading.locked_reason}</p>
                    )}
                  </div>
                </>
              )}
              {failure && (
                <p role="alert" className="mt-3 text-[13px] text-danger">
                  {failure}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {active && !readingId && (
          <Card>
            <CardHeader>
              <CardTitle>{active.path.title} roadmap</CardTitle>
              <CardDescription>
                Modules unlock in order. Completing one records it against your
                account and mints its Palestras (daily caps apply).
              </CardDescription>
            </CardHeader>
            <CardContent>
              {active.modules.length === 0 && (
                <Empty title="This path has no modules yet" />
              )}
              <ol className="divide-y divide-border">
                {active.modules.map((m, i) => {
                  const state = activeStates[i];
                  return (
                    <li key={m.id} className="flex items-center gap-3.5 py-3">
                      {stateIcon[state]}
                      <div className="min-w-0 flex-1">
                        {m.has_body && state !== "locked" ? (
                          <button
                            type="button"
                            onClick={() => open(m.id)}
                            className="text-left text-sm font-medium underline-offset-2 hover:underline"
                          >
                            {m.title}
                          </button>
                        ) : (
                          <p
                            className={
                              "text-sm " +
                              (state === "locked" ? "text-muted" : "font-medium")
                            }
                          >
                            {m.title}
                          </p>
                        )}
                        {m.summary && state !== "locked" && (
                          <p className="mt-0.5 text-[13px] leading-snug text-muted">
                            {m.summary}
                          </p>
                        )}
                        {!m.has_body && state !== "locked" && (
                          <p className="mt-0.5 text-[13px] text-muted">
                            Lesson not written yet.
                          </p>
                        )}
                      </div>
                      {m.gated && (
                        <Badge variant="neutral">lab</Badge>
                      )}
                      <Badge variant="palestras">+{m.palestras_award} P</Badge>
                      {state === "current" ? (
                        m.has_body ? (
                          <Button size="sm" variant="outline" onClick={() => open(m.id)}>
                            Open
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => complete(m.id)}
                            disabled={completing !== null}
                          >
                            {completing === m.id ? "Recording..." : "Mark complete"}
                          </Button>
                        )
                      ) : (
                        <span className="w-[132px]" />
                      )}
                    </li>
                  );
                })}
              </ol>
              {failure && (
                <p role="alert" className="mt-3 text-[13px] text-danger">
                  {failure}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {active && active.modules.length > 0 && (
          <Card className="bg-accent-soft">
            <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5">
              <div>
                <p className="text-sm font-semibold tracking-tight">
                  Certification state: {activeDone} of {active.modules.length}{" "}
                  checkpoints passed
                </p>
                <p className="mt-1 text-[13px] text-muted">
                  {activeDone === active.modules.length
                    ? "Path complete. Schedule your practical exam with your teacher."
                    : "Finish every module to schedule your practical exam with your teacher."}
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
