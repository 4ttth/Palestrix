"use client";

/*
 * CTF arena, live: events, the challenge board with per-caller solved
 * state, flag submission (30s cooldown surfaced from the API), the first
 * blood feed derived from the board's first_blood_at timestamps, and the
 * event leaderboard. The event countdown runs off the server's end
 * timestamp.
 */

import { useMemo, useState } from "react";
import { CheckFat, Drop, Trophy } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar } from "@/components/ui/avatar";
import { Countdown } from "@/components/lab/Countdown";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { AuthorPanel } from "@/components/compete/author-panel";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { useToast } from "@/components/ui/toast";
import { ago } from "@/lib/format";
import type {
  ChallengeOut,
  CtfEventOut,
  FlagResultOut,
  LeaderboardRowOut,
} from "@/lib/api/types";

function pickEvent(events: CtfEventOut[]): CtfEventOut | null {
  const now = Date.now();
  const running = events.find(
    (e) =>
      new Date(e.starts_at).getTime() <= now &&
      now <= new Date(e.ends_at).getTime()
  );
  return running ?? events[0] ?? null;
}

export function CompeteView() {
  const { user, refreshSummary } = useSession();
  const toast = useToast();
  const events = useApi<CtfEventOut[]>("/api/v1/compete/events");
  const event = useMemo(
    () => (events.data ? pickEvent(events.data) : null),
    [events.data]
  );
  const challenges = useApi<ChallengeOut[]>(
    event ? `/api/v1/compete/events/${event.id}/challenges` : null
  );
  const leaderboard = useApi<LeaderboardRowOut[]>(
    event ? `/api/v1/compete/events/${event.id}/leaderboard` : null
  );

  const [challengeId, setChallengeId] = useState("");
  const [flag, setFlag] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<FlagResultOut | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const now = Date.now();
  const eventRunning =
    event != null &&
    new Date(event.starts_at).getTime() <= now &&
    now <= new Date(event.ends_at).getTime();

  const feed = useMemo(
    () =>
      (challenges.data ?? [])
        .filter((c) => c.first_blood && c.first_blood_at)
        .sort(
          (a, b) =>
            new Date(b.first_blood_at!).getTime() -
            new Date(a.first_blood_at!).getTime()
        ),
    [challenges.data]
  );

  const myRank = leaderboard.data?.find((r) => r.handle === user.handle)?.rank;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!challengeId || flag.trim().length === 0) {
      setFailure("Pick a challenge and paste the flag, braces included.");
      return;
    }
    setSubmitting(true);
    setFailure(null);
    setResult(null);
    try {
      const outcome = await api.post<FlagResultOut>(
        `/api/v1/compete/challenges/${challengeId}/submit`,
        { flag: flag.trim() }
      );
      setResult(outcome);
      if (outcome.correct) {
        // First blood is the rarest thing that happens on this page and
        // used to be a line of 13px text next to the input.
        toast.success(
          outcome.first_blood
            ? `First blood! +${outcome.points} pts`
            : `Correct — +${outcome.points} pts`,
          outcome.palestras > 0
            ? `+${outcome.palestras} Palestras. The board is updated.`
            : "The board is updated."
        );
        setFlag("");
        setChallengeId("");
        void challenges.refetch();
        void leaderboard.refetch();
        void refreshSummary();
      } else {
        toast.error(
          "Wrong flag",
          "A 30-second cooldown is running before you can try again."
        );
      }
    } catch (err) {
      const text =
        err instanceof ApiError ? err.message : "Submission failed.";
      setFailure(text);
      toast.error("Could not submit that flag", text);
    } finally {
      setSubmitting(false);
    }
  }

  const isAuthor =
    user.role === "teacher" || user.role === "admin" || user.role === "superadmin";

  return (
    <>
      <Topbar title="CTF arena" />
      <div className="space-y-6 p-4 sm:p-6">
        {events.loading && <Loading label="loading events" />}
        {events.error && <LoadFailed error={events.error} retry={events.refetch} />}

        {isAuthor && (
          <AuthorPanel
            event={event}
            onChanged={() => {
              void events.refetch();
              void challenges.refetch();
            }}
          />
        )}

        {events.data && !event && (
          <Empty
            title="No CTF events yet"
            hint={
              isAuthor
                ? "Schedule one from the authoring panel above."
                : "Events appear here once a teacher schedules one."
            }
          />
        )}

        {event && (
          <>
            {/* Event header */}
            <Card className="border-l-2 border-l-palestras">
              <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5">
                <div>
                  <p className="text-sm font-semibold tracking-tight">
                    {event.title}
                  </p>
                  <p className="mt-0.5 text-[13px] text-muted">
                    Individual, jeopardy style. Flags earn points and Palestras.
                  </p>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <p className="text-[11px] text-muted">
                      {eventRunning
                        ? "Ends in"
                        : new Date(event.starts_at).getTime() > now
                          ? "Starts in"
                          : "Ended"}
                    </p>
                    {eventRunning ? (
                      <Countdown until={event.ends_at} className="text-lg" />
                    ) : new Date(event.starts_at).getTime() > now ? (
                      <Countdown until={event.starts_at} className="text-lg" />
                    ) : (
                      <p className="font-mono text-lg tabular-nums text-muted">
                        00:00:00
                      </p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] text-muted">Your rank</p>
                    <p className="font-mono text-lg tabular-nums">
                      {myRank ? `${myRank}` : "—"}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
              <div className="space-y-6">
                {/* Challenge board */}
                <Card>
                  <CardHeader>
                    <CardTitle>Challenge board</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {challenges.loading && <Loading label="loading board" />}
                    {challenges.error && (
                      <LoadFailed
                        error={challenges.error}
                        retry={challenges.refetch}
                      />
                    )}
                    {challenges.data && challenges.data.length === 0 && (
                      <Empty title="The board is empty" hint="Challenges appear when the authors publish them." />
                    )}
                    <div className="plx-stagger grid gap-3 md:grid-cols-2">
                      {(challenges.data ?? []).map((c, ci) => (
                        <div
                          key={c.id}
                          style={{ ["--plx-index" as string]: ci }}
                          className={
                            "rounded-(--radius-input) border p-4 " +
                            (c.solved
                              ? "border-border bg-surface-2/50"
                              : "border-border bg-surface")
                          }
                        >
                          <div className="flex items-start justify-between gap-2">
                            <p
                              className={
                                "text-sm font-medium " + (c.solved ? "text-muted" : "")
                              }
                            >
                              {c.title}
                            </p>
                            {c.solved && (
                              <CheckFat
                                size={16}
                                weight="fill"
                                className="shrink-0 text-running"
                              />
                            )}
                          </div>
                          <div className="mt-2.5 flex items-center gap-2 text-xs">
                            <Badge variant="neutral">{c.category}</Badge>
                            <span className="font-mono tabular-nums text-muted">
                              {c.points} pts
                            </span>
                            <span className="font-mono tabular-nums text-muted">
                              {c.solves} solve{c.solves === 1 ? "" : "s"}
                            </span>
                          </div>
                          <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
                            <Drop size={12} weight="fill" className="text-expired" />
                            {c.first_blood ? (
                              <>
                                first blood{" "}
                                <span className="font-mono">{c.first_blood}</span>
                              </>
                            ) : (
                              "first blood still open"
                            )}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* Flag submission */}
                <Card>
                  <CardHeader>
                    <CardTitle>Submit a flag</CardTitle>
                    <CardDescription>
                      Wrong submissions apply a 30-second cooldown per challenge.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
                      <div className="grid min-w-48 gap-2">
                        <Label htmlFor="challenge">Challenge</Label>
                        <select
                          id="challenge"
                          value={challengeId}
                          onChange={(e) => setChallengeId(e.target.value)}
                          className="h-10 rounded-(--radius-input) border border-border bg-surface px-3 text-sm"
                        >
                          <option value="">Pick one...</option>
                          {(challenges.data ?? [])
                            .filter((c) => !c.solved)
                            .map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.title}
                              </option>
                            ))}
                        </select>
                      </div>
                      <div className="grid min-w-64 flex-1 gap-2">
                        <Label htmlFor="flag">Flag</Label>
                        <Input
                          id="flag"
                          placeholder="CLCTF{...}"
                          className="font-mono"
                          value={flag}
                          onChange={(e) => setFlag(e.target.value)}
                          aria-describedby="flag-help"
                        />
                      </div>
                      <Button type="submit" disabled={submitting || !eventRunning}>
                        {submitting ? "Checking..." : "Submit flag"}
                      </Button>
                    </form>
                    <div aria-live="polite" className="mt-3 space-y-1">
                      {!eventRunning && (
                        <p className="text-[13px] text-muted">
                          Submissions open only while the event is running.
                        </p>
                      )}
                      {result && result.correct && (
                        <p className="plx-pop text-[13px] font-medium text-running">
                          Correct! +{result.points} pts
                          {result.palestras > 0 && `, +${result.palestras} P`}
                          {result.first_blood && " — first blood!"}
                        </p>
                      )}
                      {result && !result.correct && (
                        <p className="plx-shake text-[13px] text-danger">
                          Wrong flag. The 30-second cooldown is now running.
                        </p>
                      )}
                      {failure && (
                        <p className="text-[13px] text-danger">{failure}</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-6">
                {/* First blood feed */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Drop size={15} weight="fill" className="text-expired" />
                      First blood feed
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {feed.length === 0 ? (
                      <Empty
                        title="No first bloods yet"
                        hint="The first correct solve of each challenge lands here."
                      />
                    ) : (
                      <ul className="space-y-3">
                        {feed.map((c) => (
                          <li key={c.id} className="flex items-center gap-3 text-sm">
                            <Avatar handle={c.first_blood!} size="sm" />
                            <span className="min-w-0 flex-1 truncate">
                              <span className="font-mono text-[13px]">
                                {c.first_blood}
                              </span>{" "}
                              <span className="text-muted">drew first blood on</span>{" "}
                              {c.title}
                            </span>
                            <span className="font-mono text-xs text-muted">
                              {ago(c.first_blood_at!)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>

                {/* Leaderboard */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Trophy size={15} weight="fill" className="text-palestras" />
                      Leaderboard
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {leaderboard.loading && <Loading label="ranking" />}
                    {leaderboard.error && (
                      <LoadFailed
                        error={leaderboard.error}
                        retry={leaderboard.refetch}
                      />
                    )}
                    {leaderboard.data && leaderboard.data.length === 0 && (
                      <Empty
                        title="No solves yet"
                        hint="The board fills as flags land."
                      />
                    )}
                    {leaderboard.data && leaderboard.data.length > 0 && (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>#</TableHead>
                            <TableHead>Handle</TableHead>
                            <TableHead className="text-right">Score</TableHead>
                            <TableHead className="text-right">FB</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {leaderboard.data.map((row) => (
                            <TableRow key={row.handle}>
                              <TableCell className="font-mono text-xs tabular-nums text-muted">
                                {row.rank}
                              </TableCell>
                              <TableCell className="font-mono text-[13px]">
                                {row.handle}
                              </TableCell>
                              <TableCell className="text-right font-mono text-[13px] tabular-nums">
                                {row.score.toLocaleString()}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs tabular-nums text-muted">
                                {row.first_bloods}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
