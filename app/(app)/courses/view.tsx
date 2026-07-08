"use client";

/*
 * Course manager, live and role-aware: teachers see their own courses with
 * live enrollment/submission counts and the publishing panel; students see
 * the courses they're enrolled in. GET /courses already scopes rows by
 * role, so this view renders whatever the caller may see.
 */

import { useMemo, useState } from "react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
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
import { UploadPanel } from "@/components/course/upload-panel";
import { AutogradePanel } from "@/components/course/autograde-panel";
import { CanvasPanel } from "@/components/course/canvas-panel";
import { Gradebook } from "@/components/course/gradebook";
import { RosterPanel } from "@/components/course/roster-panel";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { dateOnly } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AssignmentOut, CourseOut } from "@/lib/api/types";

const KIND_LABEL: Record<AssignmentOut["kind"], string> = {
  file: "File",
  quiz: "Quiz",
  lab: "Ephemeral lab",
  writeup: "Writeup",
};

function NewCourseForm({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState({ code: "", title: "", section: "" });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!form.code.trim() || !form.title.trim()) {
      setFailure("A course needs at least a code and a title.");
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      await api.post<CourseOut>("/api/v1/courses", form);
      setForm({ code: "", title: "", section: "" });
      onCreated();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Creation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={create} className="flex flex-wrap items-end gap-3">
      <div className="grid gap-2">
        <Label htmlFor="course-code">Code</Label>
        <Input
          id="course-code"
          value={form.code}
          placeholder="CS 3712"
          onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
        />
      </div>
      <div className="grid min-w-56 flex-1 gap-2">
        <Label htmlFor="course-title">Title</Label>
        <Input
          id="course-title"
          value={form.title}
          placeholder="Defensive Operations 201"
          onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="course-section">Section</Label>
        <Input
          id="course-section"
          value={form.section}
          placeholder="BSCS 3A"
          onChange={(e) => setForm((f) => ({ ...f, section: e.target.value }))}
        />
      </div>
      <Button type="submit" size="sm" className="mb-0.5" disabled={busy}>
        {busy ? "Creating..." : "Create course"}
      </Button>
      {failure && (
        <p role="alert" className="w-full text-[13px] text-danger">
          {failure}
        </p>
      )}
    </form>
  );
}

export function CoursesView() {
  const { user } = useSession();
  const courses = useApi<CourseOut[]>("/api/v1/courses");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = useMemo(() => {
    const rows = courses.data ?? [];
    return rows.find((c) => c.id === selectedId) ?? rows[0] ?? null;
  }, [courses.data, selectedId]);

  const assignments = useApi<AssignmentOut[]>(
    selected ? `/api/v1/courses/${selected.id}/assignments` : null
  );

  const isTeacher = user.role === "teacher" || user.role === "superadmin";

  return (
    <>
      <Topbar title="Course manager" />
      <div className="space-y-6 p-4 sm:p-6">
        {courses.loading && <Loading label="loading courses" />}
        {courses.error && <LoadFailed error={courses.error} retry={courses.refetch} />}
        {courses.data && courses.data.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>
                {isTeacher ? "Create your first course" : "No courses yet"}
              </CardTitle>
              <CardDescription>
                {isTeacher
                  ? "Courses carry your assignments and lab publications."
                  : "You aren't enrolled anywhere yet. Your teacher enrolls you, or shares a course to join."}
              </CardDescription>
            </CardHeader>
            {isTeacher && (
              <CardContent>
                <NewCourseForm onCreated={() => void courses.refetch()} />
              </CardContent>
            )}
          </Card>
        )}

        {isTeacher && (courses.data?.length ?? 0) > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>New course</CardTitle>
              <CardDescription>
                Courses carry your assignments, roster, and lab publications.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <NewCourseForm onCreated={() => void courses.refetch()} />
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(courses.data ?? []).map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setSelectedId(c.id)}
              className="text-left"
            >
              <Card
                className={cn(
                  "h-full transition-colors",
                  selected?.id === c.id ? "border-accent" : "hover:bg-surface-2/40"
                )}
              >
                <CardHeader>
                  <CardTitle>{c.title}</CardTitle>
                  <CardDescription>
                    <span className="font-mono">{c.code}</span>
                    {c.section && <> for {c.section}</>}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex gap-6 text-sm">
                  <div>
                    <p className="font-mono text-lg tabular-nums">{c.students}</p>
                    <p className="text-xs text-muted">students</p>
                  </div>
                  <div>
                    <p className="font-mono text-lg tabular-nums">{c.assignments}</p>
                    <p className="text-xs text-muted">assignments</p>
                  </div>
                </CardContent>
              </Card>
            </button>
          ))}
        </div>

        {selected && (
          <div className={cn("grid gap-6", isTeacher && "xl:grid-cols-[1.2fr_1fr]")}>
            <Card>
              <CardHeader>
                <CardTitle>Assignments: {selected.title}</CardTitle>
                <CardDescription>
                  Submission counts are live from the API.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {assignments.loading && <Loading label="loading assignments" />}
                {assignments.error && (
                  <LoadFailed error={assignments.error} retry={assignments.refetch} />
                )}
                {assignments.data && assignments.data.length === 0 && (
                  <Empty
                    title="No assignments yet"
                    hint={
                      isTeacher
                        ? "Publish one from the panel on the right."
                        : "Your teacher hasn't posted anything for this course."
                    }
                  />
                )}
                {assignments.data && assignments.data.length > 0 && (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Title</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Due</TableHead>
                        <TableHead className="text-right">Submitted</TableHead>
                        <TableHead className="text-right">Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {assignments.data.map((a) => {
                        const graded =
                          a.submissions > 0 && a.graded === a.submissions;
                        return (
                          <TableRow key={a.id}>
                            <TableCell className="font-medium">{a.title}</TableCell>
                            <TableCell className="text-muted">
                              {KIND_LABEL[a.kind] ?? a.kind}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {a.due_at ? dateOnly(a.due_at) : "—"}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs tabular-nums">
                              {a.submissions}/{selected.students}
                            </TableCell>
                            <TableCell className="text-right">
                              <Badge variant={graded ? "running" : "accent"}>
                                {graded ? "Graded" : "Open"}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            {isTeacher && (
              <div className="space-y-6">
                <UploadPanel
                  course={selected}
                  onPublished={() => {
                    void assignments.refetch();
                    void courses.refetch();
                  }}
                />
                <RosterPanel
                  course={selected}
                  onChanged={() => void courses.refetch()}
                />
                <AutogradePanel />
                <CanvasPanel course={selected} />
              </div>
            )}
          </div>
        )}

        {selected && isTeacher && assignments.data && (
          <Gradebook course={selected} assignments={assignments.data} />
        )}
      </div>
    </>
  );
}
