"use client";

/*
 * Student view of an auto-graded lab: the rubric they are scored on
 * (objective titles and weights — never file paths, markers, or expected
 * values) and their latest result. "Submit for grading" checks the live
 * system right now and is re-runnable until the instance is gone; stop,
 * destroy, and the TTL reaper also grade automatically, so time up is a
 * hand-in, never a zero by forfeit.
 */

import { useState } from "react";
import { CheckCircle, Circle, Exam, XCircle } from "@phosphor-icons/react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import type { GradeCheckOut, InstanceGradingOut } from "@/lib/api/types";

export function GradingCard({
  instanceId,
  running,
}: {
  instanceId: string;
  running: boolean;
}) {
  const grading = useApi<InstanceGradingOut>(
    `/api/v1/instances/${instanceId}/grading`
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  if (!grading.data || grading.data.scheme_kind === null) return null;
  const { scheme_kind, rubric, result } = grading.data;

  async function submit() {
    setBusy(true);
    setFailure(null);
    try {
      await api.post<GradeCheckOut>(`/api/v1/instances/${instanceId}/grade`);
      await grading.refetch();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Grading failed.");
    } finally {
      setBusy(false);
    }
  }

  const passed = new Map(result?.items.map((i) => [i.key, i.passed]) ?? []);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Exam size={16} className="text-accent" />
            Automated grading
          </CardTitle>
          {result && (
            <Badge variant={result.total_percent === 100 ? "running" : "accent"}>
              {result.total_percent}%
            </Badge>
          )}
        </div>
        <CardDescription>
          {scheme_kind === "winfile"
            ? "Find and execute the win files hidden on this system; each one you run scores its share."
            : "Configure this system to match the objectives; the checker verifies the real files."}
          {" "}Graded automatically when time runs out — submit any time before
          that to record your progress.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="space-y-2">
          {rubric.map((item) => {
            const state = passed.get(item.key);
            return (
              <li
                key={item.key}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2">
                  {state === true ? (
                    <CheckCircle size={16} weight="fill" className="shrink-0 text-running" />
                  ) : state === false ? (
                    <XCircle size={16} weight="fill" className="shrink-0 text-expired" />
                  ) : (
                    <Circle size={16} className="shrink-0 text-muted" />
                  )}
                  <span className={cn("truncate", state === true && "text-running")}>
                    {item.title}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-[13px] tabular-nums text-muted">
                  {item.weight_percent}%
                </span>
              </li>
            );
          })}
        </ul>

        <Button
          size="sm"
          className="w-full"
          disabled={!running || busy}
          onClick={() => void submit()}
        >
          {busy
            ? "Checking the live system..."
            : result
              ? "Re-check my work"
              : "Submit for grading"}
        </Button>
        {!running && !result && (
          <p className="text-[12px] text-muted">
            The instance is not running; grading needs the live system.
          </p>
        )}
        {result && (
          <p className="text-[12px] leading-relaxed text-muted">
            Last checked {new Date(result.created_at).toLocaleTimeString()} (
            {result.trigger === "student" ? "your hand-in" : result.trigger}).
            The latest check is the grade of record.
          </p>
        )}
        {failure && (
          <p role="alert" className="text-[13px] text-expired">
            {failure}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
