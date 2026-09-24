"use client";

/*
 * Community hub, live: writeups with votes and comment counts from
 * GET /community/writeups, upvoting (no self-votes — the API refuses and
 * the button hides), an inline composer that publishes through
 * POST /community/writeups (earning Palestras and streak credit), the
 * community-score leaderboard, and the caller's own gamification card.
 */

import { useState } from "react";
import Link from "next/link";
import { ArrowFatUp, ChatCircle, PencilSimple } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar } from "@/components/ui/avatar";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { ago } from "@/lib/format";
import type { LeaderboardEntryOut, WriteupOut } from "@/lib/api/types";

function Composer({
  onPublished,
  onClose,
}: {
  onPublished: () => void;
  onClose: () => void;
}) {
  const { refreshSummary } = useSession();
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function publish(e: React.FormEvent) {
    e.preventDefault();
    if (title.trim().length < 4) {
      setFailure("Give it a title (at least 4 characters).");
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      await api.post<WriteupOut>("/api/v1/community/writeups", {
        title: title.trim(),
        body_md: body,
        tags: tags
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean),
        published: true,
      });
      void refreshSummary(); // publishing earns Palestras
      onPublished();
      onClose();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Publishing failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New writeup</CardTitle>
        <CardDescription>
          Markdown body. Publishing earns Palestras (daily cap applies) and
          counts toward your streak and community score.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={publish} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="wu-title">Title</Label>
            <Input
              id="wu-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Repeating Pad: XOR is not a vault"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wu-tags">Tags</Label>
            <Input
              id="wu-tags"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="crypto, xor"
              className="font-mono"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wu-body">Body (Markdown)</Label>
            <textarea
              id="wu-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={8}
              className="rounded-(--radius-input) border border-border bg-surface px-3 py-2 font-mono text-sm leading-relaxed placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
              placeholder="# How I solved it..."
            />
          </div>
          {failure && (
            <p role="alert" className="text-[13px] text-danger">
              {failure}
            </p>
          )}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={busy}>
              {busy ? "Publishing..." : "Publish"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function CommunityView() {
  const { user, summary } = useSession();
  const writeups = useApi<WriteupOut[]>("/api/v1/community/writeups");
  const contributors = useApi<LeaderboardEntryOut[]>(
    "/api/v1/gamification/leaderboard?board=community&limit=4"
  );
  const [composing, setComposing] = useState(false);
  const [voteFailure, setVoteFailure] = useState<string | null>(null);

  async function vote(writeup: WriteupOut) {
    setVoteFailure(null);
    try {
      await api.post(`/api/v1/community/writeups/${writeup.id}/vote?value=1`);
      void writeups.refetch();
    } catch (err) {
      setVoteFailure(err instanceof ApiError ? err.message : "Vote failed.");
    }
  }

  return (
    <>
      <Topbar title="Community" />
      <div className="grid gap-6 p-4 sm:p-6 xl:grid-cols-[2fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Latest writeups</CardTitle>
                <CardDescription>
                  Publishing a writeup after a solve earns Palestras and
                  community score.
                </CardDescription>
              </div>
              <Button size="sm" onClick={() => setComposing((v) => !v)}>
                <PencilSimple size={15} />
                Write one
              </Button>
            </CardHeader>
            <CardContent>
              {writeups.loading && <Loading label="loading writeups" />}
              {writeups.error && (
                <LoadFailed error={writeups.error} retry={writeups.refetch} />
              )}
              {writeups.data && writeups.data.length === 0 && (
                <Empty
                  title="Nothing published yet"
                  hint="Solved something recently? Yours could be the first writeup on the board."
                />
              )}
              {voteFailure && (
                <p role="alert" className="mb-2 text-[13px] text-danger">
                  {voteFailure}
                </p>
              )}
              <ul className="plx-stagger divide-y divide-border">
                {(writeups.data ?? []).map((w, wi) => (
                  <li
                    key={w.id}
                    style={{ ["--plx-index" as string]: wi }}
                    className="flex items-center gap-4 py-3.5"
                  >
                    <Avatar handle={w.author_handle} size="md" />
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/community/${w.id}`}
                        className="block truncate text-sm font-medium underline-offset-2 transition-colors hover:text-accent hover:underline"
                      >
                        {w.title}
                      </Link>
                      <p className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                        <span className="font-mono">{w.author_handle}</span>
                        <span>{ago(w.created_at)} ago</span>
                        {w.tags.map((t) => (
                          <Badge key={t} variant="neutral" className="text-[10px]">
                            {t}
                          </Badge>
                        ))}
                      </p>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted">
                      {w.author_handle === user.handle ? (
                        <span
                          className="flex items-center gap-1 font-mono tabular-nums"
                          title="Your writeup"
                        >
                          <ArrowFatUp size={13} />
                          {w.votes}
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => vote(w)}
                          title="Upvote"
                          className="flex items-center gap-1 rounded-(--radius-input) px-1.5 py-1 font-mono tabular-nums transition-colors hover:bg-surface-2 hover:text-foreground"
                        >
                          <ArrowFatUp size={13} />
                          {w.votes}
                        </button>
                      )}
                      <span className="flex items-center gap-1 font-mono tabular-nums">
                        <ChatCircle size={13} />
                        {w.comments}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {composing && (
            <Composer
              onPublished={() => void writeups.refetch()}
              onClose={() => setComposing(false)}
            />
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Top contributors</CardTitle>
              <CardDescription>
                Community score weighs writeups, answers, and votes. It decays,
                so ranks reward showing up, not hoarding.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {contributors.loading && <Loading label="ranking" />}
              {contributors.error && (
                <LoadFailed error={contributors.error} retry={contributors.refetch} />
              )}
              {contributors.data && contributors.data.length === 0 && (
                <Empty
                  title="No contributors ranked yet"
                  hint="Publish a writeup to appear here."
                />
              )}
              <ol className="space-y-3">
                {(contributors.data ?? []).map((row) => (
                  <li key={row.handle} className="flex items-center gap-3">
                    <Avatar handle={row.handle} size="md" />
                    <span className="flex-1 font-mono text-[13px]">{row.handle}</span>
                    <span className="font-mono text-[13px] tabular-nums text-muted">
                      {row.score.toLocaleString()}
                    </span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Your profile</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">
              <div className="flex items-center gap-3">
                <Avatar handle={user.handle} size="lg" />
                <div>
                  <p className="font-medium">{user.name}</p>
                  <p className="font-mono text-xs text-muted">{user.handle}</p>
                </div>
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-4">
                <div>
                  <dt className="text-[11px] text-muted">Community</dt>
                  <dd className="font-mono text-sm tabular-nums">
                    {summary?.community_score ?? 0}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] text-muted">First bloods</dt>
                  <dd className="font-mono text-sm tabular-nums">
                    {summary?.first_bloods ?? 0}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] text-muted">Streak</dt>
                  <dd className="font-mono text-sm tabular-nums">
                    {summary?.streak_days ?? 0}d
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
