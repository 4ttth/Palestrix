"use client";

/*
 * Canvas LMS panel on the course manager (Phase 8). Renders only when the
 * backend reports an active Canvas adapter — the UI hides what a platform
 * cannot do (docs/integrations-canvas-lms.md). Teachers link the course by
 * Canvas course id, run roster syncs, and watch the grade-passback queue;
 * failures surface here with a retry, never silently.
 */

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { dateOnly } from "@/lib/format";
import type {
  CourseOut,
  ExternalLinkOut,
  GradePassbackOut,
  IntegrationPlatformOut,
  RosterSyncOut,
} from "@/lib/api/types";

const STATUS_BADGE: Record<GradePassbackOut["status"], "running" | "accent" | "expired"> = {
  delivered: "running",
  pending: "accent",
  failed: "expired",
};

export function CanvasPanel({ course }: { course: CourseOut }) {
  const platforms = useApi<IntegrationPlatformOut[]>("/api/v1/integrations/platforms");
  const links = useApi<ExternalLinkOut[]>(
    `/api/v1/integrations/links?course_id=${course.id}`
  );
  const canvas = platforms.data?.find((p) => p.id === "canvas-lms") ?? null;
  const link = links.data?.[0] ?? null;

  const [canvasCourseId, setCanvasCourseId] = useState("");
  const [busy, setBusy] = useState<"link" | "sync" | "unlink" | string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<RosterSyncOut | null>(null);

  const grades = useApi<GradePassbackOut[]>(
    link ? `/api/v1/integrations/links/${link.id}/grades` : null
  );

  if (!canvas) return null; // no active LMS: the feature does not exist here

  async function createLink() {
    if (!canvasCourseId.trim()) {
      setFailure("Enter the Canvas course id (the number in the course URL).");
      return;
    }
    setBusy("link");
    setFailure(null);
    try {
      await api.post<ExternalLinkOut>("/api/v1/integrations/links", {
        course_id: course.id,
        external_course_id: canvasCourseId.trim(),
      });
      setCanvasCourseId("");
      await links.refetch();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Linking failed.");
    } finally {
      setBusy(null);
    }
  }

  async function syncRoster() {
    if (!link) return;
    setBusy("sync");
    setFailure(null);
    setSyncResult(null);
    try {
      setSyncResult(
        await api.post<RosterSyncOut>(`/api/v1/integrations/links/${link.id}/sync`)
      );
      await links.refetch();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Roster sync failed.");
    } finally {
      setBusy(null);
    }
  }

  async function unlink() {
    if (!link) return;
    setBusy("unlink");
    setFailure(null);
    try {
      await api.del(`/api/v1/integrations/links/${link.id}`);
      setSyncResult(null);
      await links.refetch();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Unlink failed.");
    } finally {
      setBusy(null);
    }
  }

  async function retry(passbackId: string) {
    setBusy(passbackId);
    setFailure(null);
    try {
      await api.post<GradePassbackOut>(`/api/v1/integrations/grades/${passbackId}/retry`);
      await Promise.all([grades.refetch(), links.refetch()]);
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Retry failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Canvas LMS</CardTitle>
        <CardDescription>
          {link
            ? `Linked to Canvas course ${link.external_course_id}` +
              (link.context_title ? ` (${link.context_title})` : "")
            : "Link this course to sync enrollment and pass grades back."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!link && (
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid min-w-48 flex-1 gap-2">
              <Label htmlFor="canvas-course-id">Canvas course id</Label>
              <Input
                id="canvas-course-id"
                value={canvasCourseId}
                placeholder="e.g. 4127"
                onChange={(e) => setCanvasCourseId(e.target.value)}
              />
            </div>
            <Button size="sm" className="mb-0.5" disabled={busy !== null} onClick={createLink}>
              {busy === "link" ? "Linking..." : "Link course"}
            </Button>
          </div>
        )}

        {link && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={busy !== null} onClick={syncRoster}>
                {busy === "sync" ? "Syncing roster..." : "Sync roster"}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={busy !== null}
                onClick={unlink}
              >
                {busy === "unlink" ? "Unlinking..." : "Unlink"}
              </Button>
              <span className="text-xs text-muted">
                {link.last_synced_at
                  ? `Last synced ${dateOnly(link.last_synced_at)}`
                  : "Never synced"}
              </span>
            </div>

            {syncResult && (
              <p className="text-[13px] text-muted" role="status">
                Roster of {syncResult.roster}: {syncResult.added} enrolled,{" "}
                {syncResult.provisioned} accounts pre-provisioned,{" "}
                {syncResult.removed} dropped
                {syncResult.skipped > 0 && `, ${syncResult.skipped} skipped (no e-mail)`}.
              </p>
            )}

            <div className="flex gap-2">
              <Badge variant="running">{link.grades_delivered} grades delivered</Badge>
              {link.grades_pending > 0 && (
                <Badge variant="accent">{link.grades_pending} pending</Badge>
              )}
              {link.grades_failed > 0 && (
                <Badge variant="expired">{link.grades_failed} failed</Badge>
              )}
            </div>

            {grades.data && grades.data.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Student</TableHead>
                    <TableHead>Assignment</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead className="text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {grades.data.slice(0, 8).map((g) => (
                    <TableRow key={g.id}>
                      <TableCell className="font-mono text-xs">{g.student_handle}</TableCell>
                      <TableCell>{g.assignment_title}</TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {g.score_given}/{g.score_maximum}
                      </TableCell>
                      <TableCell className="text-right">
                        {g.status === "delivered" ? (
                          <Badge variant={STATUS_BADGE[g.status]}>Delivered</Badge>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busy !== null}
                            onClick={() => retry(g.id)}
                            title={g.error ?? undefined}
                          >
                            {busy === g.id
                              ? "Retrying..."
                              : g.status === "failed"
                                ? "Failed — retry"
                                : "Pending — send now"}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        )}

        {canvas.ephemeral_key && (
          <p className="text-[13px] text-muted">
            The backend is using an ephemeral Canvas signing key (development
            mode). Configure PALESTRIX_CANVAS_TOOL_PRIVATE_KEY before real use.
          </p>
        )}

        {failure && (
          <p role="alert" className="text-[13px] text-danger">
            {failure}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
