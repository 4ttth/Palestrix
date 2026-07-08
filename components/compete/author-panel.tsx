"use client";

/*
 * CTF authoring (compete:author — teachers, admins, superadmins): schedule
 * an event and publish challenges onto its board. Flags are hashed at rest
 * server-side and never returned, so what you type here is the one time the
 * platform sees the plaintext.
 */

import { useState, type FormEvent } from "react";
import { Flag, Plus } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { api, ApiError } from "@/lib/api/client";
import type { ChallengeOut, CtfEventOut } from "@/lib/api/types";

const NEW_CHALLENGE = {
  title: "",
  category: "Web",
  points: "250",
  flag: "",
  palestras_award: "100",
};

export function AuthorPanel({
  event,
  onChanged,
}: {
  event: CtfEventOut | null;
  onChanged: () => void;
}) {
  const [showEvent, setShowEvent] = useState(false);
  const [showChallenge, setShowChallenge] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Flag size={15} className="text-accent" />
            Authoring
          </CardTitle>
          <CardDescription>
            {event
              ? `Publishing onto "${event.title}".`
              : "No event yet — schedule the first one."}
          </CardDescription>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setShowEvent((v) => !v);
              setShowChallenge(false);
            }}
          >
            <Plus size={14} />
            Event
          </Button>
          {event && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowChallenge((v) => !v);
                setShowEvent(false);
              }}
            >
              <Plus size={14} />
              Challenge
            </Button>
          )}
        </div>
      </CardHeader>
      {(showEvent || showChallenge || note) && (
        <CardContent className="space-y-4">
          {note && (
            <p
              aria-live="polite"
              className={
                "rounded-(--radius-input) px-3 py-2 font-mono text-[11px] " +
                (note.ok
                  ? "bg-accent-soft text-accent"
                  : "bg-expired-soft text-expired")
              }
            >
              {note.text}
            </p>
          )}
          {showEvent && (
            <EventForm
              onDone={(text, ok) => {
                setNote({ ok, text });
                if (ok) {
                  setShowEvent(false);
                  onChanged();
                }
              }}
            />
          )}
          {showChallenge && event && (
            <ChallengeForm
              event={event}
              onDone={(text, ok) => {
                setNote({ ok, text });
                if (ok) onChanged();
              }}
            />
          )}
        </CardContent>
      )}
    </Card>
  );
}

/** datetime-local value -> ISO with the browser's zone applied. */
function toIso(local: string): string {
  return new Date(local).toISOString();
}

function EventForm({ onDone }: { onDone: (text: string, ok: boolean) => void }) {
  const [title, setTitle] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (new Date(startsAt) >= new Date(endsAt)) {
      onDone("The event must end after it starts.", false);
      return;
    }
    setBusy(true);
    try {
      const created = await api.post<CtfEventOut>("/api/v1/compete/events", {
        title: title.trim(),
        starts_at: toIso(startsAt),
        ends_at: toIso(endsAt),
      });
      setTitle("");
      setStartsAt("");
      setEndsAt("");
      onDone(`Event "${created.title}" scheduled.`, true);
    } catch (err) {
      onDone(err instanceof ApiError ? err.message : "Scheduling failed.", false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={create}
      className="grid gap-3 rounded-(--radius-input) border border-border bg-surface-2/40 p-4 sm:grid-cols-3"
    >
      <div className="grid gap-1.5 sm:col-span-3">
        <Label htmlFor="ev-title">Event title</Label>
        <Input
          id="ev-title"
          value={title}
          required
          minLength={4}
          placeholder="CLCTF 2026 Qualifier Round 3"
          onChange={(e) => setTitle(e.target.value)}
          className="h-9 text-[13px]"
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="ev-start">Starts</Label>
        <Input
          id="ev-start"
          type="datetime-local"
          value={startsAt}
          required
          onChange={(e) => setStartsAt(e.target.value)}
          className="h-9 font-mono text-[13px]"
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="ev-end">Ends</Label>
        <Input
          id="ev-end"
          type="datetime-local"
          value={endsAt}
          required
          onChange={(e) => setEndsAt(e.target.value)}
          className="h-9 font-mono text-[13px]"
        />
      </div>
      <div className="flex items-end">
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? "Scheduling..." : "Schedule event"}
        </Button>
      </div>
    </form>
  );
}

function ChallengeForm({
  event,
  onDone,
}: {
  event: CtfEventOut;
  onDone: (text: string, ok: boolean) => void;
}) {
  const [draft, setDraft] = useState(NEW_CHALLENGE);
  const [busy, setBusy] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const created = await api.post<ChallengeOut>(
        `/api/v1/compete/events/${event.id}/challenges`,
        {
          title: draft.title.trim(),
          category: draft.category.trim(),
          points: Number(draft.points),
          flag: draft.flag.trim(),
          palestras_award: Number(draft.palestras_award),
        }
      );
      setDraft(NEW_CHALLENGE);
      onDone(`Challenge "${created.title}" is on the board.`, true);
    } catch (err) {
      onDone(err instanceof ApiError ? err.message : "Publishing failed.", false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={create}
      className="grid gap-3 rounded-(--radius-input) border border-border bg-surface-2/40 p-4 sm:grid-cols-2"
    >
      <div className="grid gap-1.5">
        <Label htmlFor="ch-title">Title</Label>
        <Input
          id="ch-title"
          value={draft.title}
          required
          placeholder="Cookie Monster's Bakery"
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          className="h-9 text-[13px]"
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="ch-category">Category</Label>
        <Input
          id="ch-category"
          value={draft.category}
          required
          placeholder="Web, Crypto, OSINT..."
          onChange={(e) => setDraft({ ...draft, category: e.target.value })}
          className="h-9 text-[13px]"
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="ch-points">Points (1-1000)</Label>
        <Input
          id="ch-points"
          type="number"
          min={1}
          max={1000}
          value={draft.points}
          required
          onChange={(e) => setDraft({ ...draft, points: e.target.value })}
          className="h-9 font-mono text-[13px]"
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="ch-award">Palestras award (0-1000)</Label>
        <Input
          id="ch-award"
          type="number"
          min={0}
          max={1000}
          value={draft.palestras_award}
          required
          onChange={(e) => setDraft({ ...draft, palestras_award: e.target.value })}
          className="h-9 font-mono text-[13px]"
        />
      </div>
      <div className="grid gap-1.5 sm:col-span-2">
        <Label htmlFor="ch-flag">Flag (exact, braces included)</Label>
        <Input
          id="ch-flag"
          value={draft.flag}
          required
          minLength={4}
          placeholder="CLCTF{...}"
          onChange={(e) => setDraft({ ...draft, flag: e.target.value })}
          className="h-9 font-mono text-[13px]"
        />
        <p className="text-[11px] text-muted">
          Stored as a SHA-256 hash; it cannot be read back after publishing.
        </p>
      </div>
      <div className="sm:col-span-2">
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? "Publishing..." : "Publish challenge"}
        </Button>
      </div>
    </form>
  );
}
