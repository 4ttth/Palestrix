"use client";

/*
 * Teacher roster management (courses:write): who is enrolled in the
 * selected course, enroll a student by handle, remove one. Students can
 * still self-enroll via POST /courses/{id}/enroll; this panel is the
 * teacher-driven path so a class can be set up before day one.
 */

import { useState, type FormEvent } from "react";
import { UsersThree, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { dateOnly } from "@/lib/format";
import type { CourseOut, RosterRowOut } from "@/lib/api/types";

export function RosterPanel({
  course,
  onChanged,
}: {
  course: CourseOut;
  onChanged?: () => void;
}) {
  const roster = useApi<RosterRowOut[]>(`/api/v1/courses/${course.id}/roster`);
  const [handle, setHandle] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);

  async function enroll(e: FormEvent) {
    e.preventDefault();
    if (!handle.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.post(`/api/v1/courses/${course.id}/enrollments`, {
        handle: handle.trim(),
      });
      setNotice({ ok: true, text: `Enrolled ${handle.trim()}.` });
      setHandle("");
      void roster.refetch();
      onChanged?.();
    } catch (err) {
      setNotice({
        ok: false,
        text: err instanceof ApiError ? err.message : "Enrollment failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: RosterRowOut) {
    if (!window.confirm(`Remove ${row.handle} from ${course.code}?`)) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.del(`/api/v1/courses/${course.id}/enrollments/${row.user_id}`);
      setNotice({ ok: true, text: `Removed ${row.handle}.` });
      void roster.refetch();
      onChanged?.();
    } catch (err) {
      setNotice({
        ok: false,
        text: err instanceof ApiError ? err.message : "Removal failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UsersThree size={15} className="text-accent" />
          Roster: {course.code}
        </CardTitle>
        <CardDescription>
          Enroll students by their handle (they choose it at registration; the
          users console lists everyone).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={enroll} className="mb-4 flex gap-2">
          <Input
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            placeholder="student handle, e.g. rafalmz"
            aria-label="Student handle"
            className="h-9 font-mono text-[13px]"
          />
          <Button type="submit" size="sm" disabled={busy || !handle.trim()}>
            Enroll
          </Button>
        </form>

        {notice && (
          <p
            aria-live="polite"
            className={
              "mb-3 rounded-(--radius-input) px-3 py-2 font-mono text-[11px] " +
              (notice.ok ? "bg-accent-soft text-accent" : "bg-expired-soft text-expired")
            }
          >
            {notice.text}
          </p>
        )}

        {roster.loading && <Loading label="loading roster" />}
        {roster.error && <LoadFailed error={roster.error} retry={roster.refetch} />}
        {roster.data && roster.data.length === 0 && (
          <Empty
            title="Nobody is enrolled yet"
            hint="Enroll students above, or have them self-enroll from their account."
          />
        )}
        <ul className="divide-y divide-border">
          {(roster.data ?? []).map((row) => (
            <li key={row.user_id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">{row.name}</p>
                <p className="truncate font-mono text-[11px] text-muted">
                  {row.handle} · {row.email} · since {dateOnly(row.enrolled_at)}
                </p>
              </div>
              <button
                type="button"
                title={`Remove ${row.handle}`}
                aria-label={`Remove ${row.handle}`}
                disabled={busy}
                onClick={() => void remove(row)}
                className="rounded-(--radius-input) p-1.5 text-muted transition-colors hover:bg-expired-soft hover:text-expired"
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
