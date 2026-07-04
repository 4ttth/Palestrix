"use client";

/*
 * Per-assignment gradebook for the course manager. Every submission row
 * shows the grade of record; auto-graded lab rows carry the checker's
 * objective-by-objective breakdown behind it. Manual grading posts through
 * the same endpoint teachers always had (and re-queues Canvas passback),
 * so a teacher can override an automated grade.
 */

import { useState } from "react";
import { CheckCircle, XCircle } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
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
import type { AssignmentOut, CourseOut, GradebookRowOut } from "@/lib/api/types";

function GradeCell({
  courseId,
  assignmentId,
  row,
  onGraded,
}: {
  courseId: string;
  assignmentId: string;
  row: GradebookRowOut;
  onGraded: () => void;
}) {
  const [value, setValue] = useState<string>(row.grade?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  const dirty = value !== (row.grade?.toString() ?? "");

  async function save() {
    const grade = Number(value);
    if (!Number.isInteger(grade) || grade < 0 || grade > 100) return;
    setBusy(true);
    try {
      await api.post(
        `/api/v1/courses/${courseId}/assignments/${assignmentId}/submissions/${row.submission_id}/grade`,
        { grade }
      );
      onGraded();
    } catch (err) {
      setValue(row.grade?.toString() ?? "");
      if (!(err instanceof ApiError)) throw err;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-end gap-1.5">
      <Input
        type="number"
        min={0}
        max={100}
        value={value}
        placeholder="—"
        onChange={(e) => setValue(e.target.value)}
        className="w-16 text-right font-mono"
        aria-label={`Grade for ${row.handle}`}
      />
      {dirty && (
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void save()}>
          {busy ? "..." : "Save"}
        </Button>
      )}
    </div>
  );
}

export function Gradebook({
  course,
  assignments,
}: {
  course: CourseOut;
  assignments: AssignmentOut[];
}) {
  const [assignmentId, setAssignmentId] = useState<string>("");
  const selected =
    assignments.find((a) => a.id === assignmentId) ?? assignments[0] ?? null;
  const rows = useApi<GradebookRowOut[]>(
    selected
      ? `/api/v1/courses/${course.id}/assignments/${selected.id}/submissions`
      : null
  );

  if (assignments.length === 0) return null;

  return (
    <div className="rounded-(--radius-card) border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold">Gradebook</h3>
          <p className="text-[12px] text-muted">
            Grades of record for {course.code}; automated checks show their
            breakdown.
          </p>
        </div>
        <select
          value={selected?.id ?? ""}
          onChange={(e) => setAssignmentId(e.target.value)}
          className="h-9 rounded-(--radius-input) border border-border bg-surface px-3 text-sm"
          aria-label="Assignment"
        >
          {assignments.map((a) => (
            <option key={a.id} value={a.id}>
              {a.title}
            </option>
          ))}
        </select>
      </div>
      <div className="p-5">
        {rows.loading && <Loading label="loading submissions" />}
        {rows.error && <LoadFailed error={rows.error} retry={rows.refetch} />}
        {rows.data && rows.data.length === 0 && (
          <Empty
            title="No submissions yet"
            hint="Rows appear when students submit — or when the automated checker grades a lab hand-in."
          />
        )}
        {rows.data && rows.data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student</TableHead>
                <TableHead>Automated check</TableHead>
                <TableHead className="text-right">Grade</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.data.map((row) => (
                <TableRow key={row.submission_id}>
                  <TableCell>
                    <p className="font-medium">{row.name}</p>
                    <p className="font-mono text-[11px] text-muted">@{row.handle}</p>
                  </TableCell>
                  <TableCell>
                    {row.auto ? (
                      <div className="space-y-1">
                        <Badge
                          variant={row.auto.total_percent === 100 ? "running" : "accent"}
                        >
                          {row.auto.total_percent}% · {row.auto.trigger}
                        </Badge>
                        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                          {row.auto.items.map((item) => (
                            <span
                              key={item.key}
                              className="inline-flex items-center gap-1 text-[11px] text-muted"
                              title={`${item.title}: ${item.weight_percent}%`}
                            >
                              {item.passed ? (
                                <CheckCircle size={12} weight="fill" className="text-running" />
                              ) : (
                                <XCircle size={12} weight="fill" className="text-expired" />
                              )}
                              {item.key}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <span className="text-[12px] text-muted">manual</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <GradeCell
                      courseId={course.id}
                      assignmentId={selected!.id}
                      row={row}
                      onGraded={() => void rows.refetch()}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
