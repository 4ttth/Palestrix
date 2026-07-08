"use client";

/*
 * Writeup reader: the full body (Markdown, rendered safely), voting,
 * comments, and moderation. Reached from the community hub list — every
 * writeup title links here.
 */

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowFatUp, ArrowLeft, ChatCircle, Trash } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { Markdown } from "@/components/ui/markdown";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { ago } from "@/lib/format";
import type { CommentOut, WriteupOut } from "@/lib/api/types";

export function WriteupView({ id }: { id: string }) {
  const router = useRouter();
  const { user } = useSession();
  const writeup = useApi<WriteupOut>(`/api/v1/community/writeups/${id}`);
  const comments = useApi<CommentOut[]>(`/api/v1/community/writeups/${id}/comments`);
  const [failure, setFailure] = useState<string | null>(null);

  const w = writeup.data;
  const isModerator =
    user.role === "teacher" || user.role === "admin" || user.role === "superadmin";

  async function vote() {
    if (!w) return;
    setFailure(null);
    try {
      await api.post(`/api/v1/community/writeups/${w.id}/vote?value=1`);
      void writeup.refetch();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Vote failed.");
    }
  }

  async function unpublish() {
    if (!w) return;
    if (
      !window.confirm(
        `Unpublish "${w.title}"? It disappears from the board; the author keeps the draft.`
      )
    ) {
      return;
    }
    setFailure(null);
    try {
      await api.del(`/api/v1/community/writeups/${w.id}`);
      router.push("/community");
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Moderation failed.");
    }
  }

  return (
    <>
      <Topbar title="Writeup" />
      <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
        <Link
          href="/community"
          className="inline-flex items-center gap-1.5 text-[13px] text-muted transition-colors hover:text-foreground"
        >
          <ArrowLeft size={14} />
          Back to community
        </Link>

        {writeup.loading && <Loading label="loading writeup" />}
        {writeup.error && (
          <LoadFailed error={writeup.error} retry={writeup.refetch} />
        )}

        {failure && (
          <p role="alert" className="rounded-(--radius-input) bg-expired-soft px-4 py-3 text-[13px] text-expired">
            {failure}
          </p>
        )}

        {w && (
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <CardTitle className="text-lg leading-snug">{w.title}</CardTitle>
                  <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <Avatar handle={w.author_handle} size="sm" />
                    <span className="font-mono">{w.author_handle}</span>
                    <span>{ago(w.created_at)} ago</span>
                    {!w.published && <Badge variant="expired">unpublished</Badge>}
                    {w.tags.map((t) => (
                      <Badge key={t} variant="neutral" className="text-[10px]">
                        {t}
                      </Badge>
                    ))}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {w.author_handle === user.handle ? (
                    <span
                      className="flex items-center gap-1.5 rounded-(--radius-input) border border-border px-2.5 py-1.5 font-mono text-xs tabular-nums text-muted"
                      title="Your writeup"
                    >
                      <ArrowFatUp size={14} />
                      {w.votes}
                    </span>
                  ) : (
                    <Button variant="outline" size="sm" onClick={() => void vote()}>
                      <ArrowFatUp size={14} />
                      <span className="font-mono tabular-nums">{w.votes}</span>
                    </Button>
                  )}
                  {isModerator && w.published && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void unpublish()}
                      title="Unpublish (moderation)"
                    >
                      <Trash size={14} />
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {w.body_md.trim() === "" ? (
                <p className="text-[13px] text-muted">
                  This writeup has no body text.
                </p>
              ) : (
                <Markdown source={w.body_md} />
              )}
            </CardContent>
          </Card>
        )}

        {w && w.published && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ChatCircle size={15} className="text-accent" />
                Comments
              </CardTitle>
              <CardDescription>
                Questions and refinements. Be the reviewer you wish you had.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {comments.loading && <Loading label="loading comments" />}
              {comments.error && (
                <LoadFailed error={comments.error} retry={comments.refetch} />
              )}
              {comments.data && comments.data.length === 0 && (
                <Empty title="No comments yet" hint="Start the thread below." />
              )}
              <ul className="space-y-4">
                {(comments.data ?? []).map((c) => (
                  <li key={c.id} className="flex items-start gap-3">
                    <Avatar handle={c.author_handle} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-muted">
                        <span className="font-mono">{c.author_handle}</span> ·{" "}
                        {ago(c.created_at)} ago
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
                        {c.body}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
              <CommentComposer
                writeupId={w.id}
                onPosted={() => {
                  void comments.refetch();
                  void writeup.refetch(); // comment count on the card
                }}
              />
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}

function CommentComposer({
  writeupId,
  onPosted,
}: {
  writeupId: string;
  onPosted: () => void;
}) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function post(e: FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    setFailure(null);
    try {
      await api.post(`/api/v1/community/writeups/${writeupId}/comments`, {
        body: body.trim(),
      });
      setBody("");
      onPosted();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Posting failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={post} className="space-y-2 border-t border-border pt-4">
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={3}
        placeholder="Add a comment..."
        aria-label="Comment"
        className="w-full rounded-(--radius-input) border border-border bg-surface px-3 py-2 text-sm leading-relaxed placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
      />
      {failure && (
        <p role="alert" className="text-[13px] text-danger">
          {failure}
        </p>
      )}
      <div className="flex justify-end">
        <Button type="submit" size="sm" disabled={busy || !body.trim()}>
          {busy ? "Posting..." : "Post comment"}
        </Button>
      </div>
    </form>
  );
}
