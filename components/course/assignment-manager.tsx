"use client";

/*
 * What a teacher can do to an assignment after publishing it, which until
 * now was nothing.
 *
 * The courses page could create assignments and read a gradebook, and that
 * was the whole surface: a typo in a title, a due date set to the wrong
 * month, or a lab assignment pointed at the wrong environment could only be
 * worked around by filing a second assignment and leaving the mistake on
 * the students' page forever.
 *
 * The destructive action is deliberately the least reachable one. Closing
 * is what "stop accepting this" almost always means, so it is the primary
 * control; delete is behind a row-level confirmation that states how much
 * graded work it would destroy, because the API refuses that without an
 * explicit force and the UI should say why before asking again.
 */

import { useState } from "react";
import {
  Archive,
  ArrowCounterClockwise,
  Check,
  Lock,
  PencilSimple,
  Trash,
  X,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Empty } from "@/components/ui/async";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type {
  AssignmentKind,
  AssignmentOut,
  AssignmentStatus,
  LabTemplateOut,
} from "@/lib/api/types";

const KIND_LABEL: Record<AssignmentKind, string> = {
  file: "File",
  quiz: "Quiz",
  lab: "Live lab",
  writeup: "Write-up",
};

const STATUS_BADGE: Record<
  AssignmentStatus,
  { label: string; variant: "running" | "stopped" | "expired" }
> = {
  open: { label: "Open", variant: "running" },
  closed: { label: "Closed", variant: "stopped" },
  archived: { label: "Archived", variant: "expired" },
};

/** Turns the API's ISO timestamp into the value <input type="datetime-local">
 * expects, in the viewer's own timezone. Slicing the ISO string would show
 * a UTC wall-clock time as though it were local, which is how a due date
 * lands an hour off. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export function AssignmentManager({
  courseId,
  assignments,
  templates,
  onChanged,
}: {
  courseId: string;
  assignments: AssignmentOut[];
  templates: LabTemplateOut[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();

  async function run(
    id: string,
    label: string,
    work: () => Promise<unknown>,
    done: { title: string; detail?: string }
  ) {
    setBusy(id);
    try {
      await work();
      toast.success(done.title, done.detail);
      onChanged();
      setEditing(null);
      setConfirming(null);
    } catch (err) {
      toast.error(
        label,
        err instanceof ApiError ? err.message : "The request failed."
      );
    } finally {
      setBusy(null);
    }
  }

  function setStatus(a: AssignmentOut, status: AssignmentStatus) {
    const copy: Record<AssignmentStatus, { title: string; detail: string }> = {
      open: {
        title: `"${a.title}" reopened`,
        detail: "Students can submit again.",
      },
      closed: {
        title: `"${a.title}" closed`,
        detail: "No new submissions. Existing grades stay visible.",
      },
      archived: {
        title: `"${a.title}" archived`,
        detail: "Hidden from students. You can still reopen it.",
      },
    };
    return run(
      a.id,
      `Could not update "${a.title}"`,
      () =>
        api.patch(`/api/v1/courses/${courseId}/assignments/${a.id}`, {
          status,
        }),
      copy[status]
    );
  }

  if (assignments.length === 0) {
    return (
      <Empty
        title="No assignments yet"
        hint="Publish one with the panel above and it will appear here, ready to edit, close, or archive."
      />
    );
  }

  return (
    <ul className="plx-stagger divide-y divide-border">
      {assignments.map((a, i) => {
        const badge = STATUS_BADGE[a.status];
        const isEditing = editing === a.id;
        const isConfirming = confirming === a.id;
        return (
          <li
            key={a.id}
            style={{ ["--plx-index" as string]: i }}
            className={cn(
              "py-3 transition-opacity",
              a.status === "archived" && !isEditing && "opacity-60"
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-sm font-medium">{a.title}</p>
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                  <span className="text-[12px] text-muted">
                    {KIND_LABEL[a.kind]}
                  </span>
                </div>
                <p className="mt-0.5 text-[13px] text-muted">
                  {a.submissions} submission{a.submissions === 1 ? "" : "s"},{" "}
                  {a.graded} graded
                  {a.due_at &&
                    ` · due ${new Date(a.due_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}`}
                </p>
              </div>

              {!isEditing && !isConfirming && (
                <div className="flex shrink-0 flex-wrap gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditing(a.id)}
                  >
                    <PencilSimple className="size-4" aria-hidden />
                    Edit
                  </Button>
                  {a.status === "open" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={busy === a.id}
                      onClick={() => setStatus(a, "closed")}
                    >
                      <Lock className="size-4" aria-hidden />
                      Close
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={busy === a.id}
                      onClick={() => setStatus(a, "open")}
                    >
                      <ArrowCounterClockwise className="size-4" aria-hidden />
                      Reopen
                    </Button>
                  )}
                  {a.status !== "archived" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={busy === a.id}
                      onClick={() => setStatus(a, "archived")}
                    >
                      <Archive className="size-4" aria-hidden />
                      Archive
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-danger hover:bg-danger/10"
                    onClick={() => setConfirming(a.id)}
                  >
                    <Trash className="size-4" aria-hidden />
                    Delete
                  </Button>
                </div>
              )}
            </div>

            {isConfirming && (
              <div className="plx-rise mt-3 rounded-(--radius-input) border border-danger/40 bg-danger/5 p-3">
                <p className="text-[13px] leading-relaxed">
                  {a.submissions > 0 ? (
                    <>
                      This permanently deletes{" "}
                      <strong>
                        {a.submissions} submission
                        {a.submissions === 1 ? "" : "s"}
                      </strong>
                      {a.graded > 0 && <>, {a.graded} of them graded</>}. There
                      is no undo. Closing the assignment stops new submissions
                      without losing the work.
                    </>
                  ) : (
                    <>
                      Nothing has been submitted to this assignment, so nothing
                      is lost. This cannot be undone.
                    </>
                  )}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    variant="destructive"
                    size="sm"
                    loading={busy === a.id}
                    onClick={() =>
                      run(
                        a.id,
                        `Could not delete "${a.title}"`,
                        () =>
                          api.del(
                            `/api/v1/courses/${courseId}/assignments/${a.id}?force=true`
                          ),
                        {
                          title: `"${a.title}" deleted`,
                          detail:
                            a.submissions > 0
                              ? `${a.submissions} submission(s) removed with it.`
                              : undefined,
                        }
                      )
                    }
                  >
                    Delete permanently
                  </Button>
                  {a.submissions > 0 && a.status === "open" && (
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={busy === a.id}
                      onClick={() => setStatus(a, "closed")}
                    >
                      Close instead
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirming(null)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {isEditing && (
              <EditRow
                assignment={a}
                templates={templates}
                busy={busy === a.id}
                onCancel={() => setEditing(null)}
                onSave={(patch) =>
                  run(
                    a.id,
                    `Could not save "${a.title}"`,
                    () =>
                      api.patch(
                        `/api/v1/courses/${courseId}/assignments/${a.id}`,
                        patch
                      ),
                    { title: "Changes saved" }
                  )
                }
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

function EditRow({
  assignment,
  templates,
  busy,
  onCancel,
  onSave,
}: {
  assignment: AssignmentOut;
  templates: LabTemplateOut[];
  busy: boolean;
  onCancel: () => void;
  onSave: (patch: Record<string, unknown>) => void;
}) {
  const [title, setTitle] = useState(assignment.title);
  const [kind, setKind] = useState<AssignmentKind>(assignment.kind);
  const [due, setDue] = useState(toLocalInput(assignment.due_at));
  const [templateId, setTemplateId] = useState(assignment.lab_template_id ?? "");

  function save() {
    // Only send what actually changed: the API treats an explicit null as
    // "clear this", so sending the whole form would blank a due date the
    // teacher never touched.
    const patch: Record<string, unknown> = {};
    if (title.trim() !== assignment.title) patch.title = title.trim();
    if (kind !== assignment.kind) patch.kind = kind;
    const nextDue = due ? new Date(due).toISOString() : null;
    if (nextDue !== assignment.due_at) patch.due_at = nextDue;
    const nextTemplate = templateId || null;
    if (nextTemplate !== assignment.lab_template_id) {
      patch.lab_template_id = nextTemplate;
    }
    if (Object.keys(patch).length === 0) {
      onCancel();
      return;
    }
    onSave(patch);
  }

  return (
    <div className="plx-rise mt-3 grid gap-3 rounded-(--radius-input) border border-border bg-surface-2/40 p-3 sm:grid-cols-2">
      <div className="grid gap-1.5 sm:col-span-2">
        <Label htmlFor={`t-${assignment.id}`}>Title</Label>
        <Input
          id={`t-${assignment.id}`}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor={`k-${assignment.id}`}>Type</Label>
        <select
          id={`k-${assignment.id}`}
          value={kind}
          onChange={(e) => setKind(e.target.value as AssignmentKind)}
          className="h-10 rounded-(--radius-input) border border-border bg-surface px-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {(Object.keys(KIND_LABEL) as AssignmentKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor={`d-${assignment.id}`}>Due (optional)</Label>
        <Input
          id={`d-${assignment.id}`}
          type="datetime-local"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
      </div>

      {kind === "lab" && (
        <div className="grid gap-1.5 sm:col-span-2">
          <Label htmlFor={`l-${assignment.id}`}>Lab environment</Label>
          <select
            id={`l-${assignment.id}`}
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            className="h-10 rounded-(--radius-input) border border-border bg-surface px-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <option value="">None selected</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title} ({t.slug})
              </option>
            ))}
          </select>
          {templates.length === 0 && (
            <p className="text-[13px] text-muted">
              No lab environments published yet. Use the advanced panel above
              to publish one.
            </p>
          )}
        </div>
      )}

      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          <X className="size-4" aria-hidden />
          Cancel
        </Button>
        <Button size="sm" loading={busy} onClick={save}>
          <Check className="size-4" aria-hidden />
          Save changes
        </Button>
      </div>
    </div>
  );
}
