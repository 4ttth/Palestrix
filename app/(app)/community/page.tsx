import { ArrowFatUp, ChatCircle, PencilSimple } from "@phosphor-icons/react/dist/ssr";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { leaderboard, writeups } from "@/lib/mock";

export const metadata = { title: "Community" };

/*
 * Community hub: writeups, profiles, community score. Writeup prose is
 * capped at 65ch when opened; this index stays dense.
 */
export default function CommunityPage() {
  return (
    <>
      <Topbar title="Community" />
      <div className="grid gap-6 p-6 xl:grid-cols-[2fr_1fr]">
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
              <Button size="sm">
                <PencilSimple size={15} />
                Write one
              </Button>
            </CardHeader>
            <CardContent>
              <ul className="divide-y divide-border">
                {writeups.map((w) => (
                  <li key={w.title} className="flex items-center gap-4 py-3.5">
                    <Avatar handle={w.author} size="md" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{w.title}</p>
                      <p className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                        <span className="font-mono">{w.author}</span>
                        <span>{w.ago} ago</span>
                        {w.tags.map((t) => (
                          <Badge key={t} variant="neutral" className="text-[10px]">
                            {t}
                          </Badge>
                        ))}
                      </p>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted">
                      <span className="flex items-center gap-1 font-mono tabular-nums">
                        <ArrowFatUp size={13} />
                        {w.votes}
                      </span>
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

          {/* Empty state: drafts */}
          <Card>
            <CardHeader>
              <CardTitle>Your drafts</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-(--radius-input) border border-dashed border-border px-6 py-10 text-center">
                <p className="text-sm font-medium">Nothing in progress</p>
                <p className="mx-auto mt-1 max-w-[42ch] text-[13px] leading-relaxed text-muted">
                  Solved something recently? Start a writeup from any completed
                  challenge and it lands here until you publish.
                </p>
                <Button variant="outline" size="sm" className="mt-4">
                  Start from a solve
                </Button>
              </div>
            </CardContent>
          </Card>
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
              <ol className="space-y-3">
                {leaderboard.slice(0, 4).map((row) => (
                  <li key={row.handle} className="flex items-center gap-3">
                    <Avatar handle={row.handle} size="md" />
                    <span className="flex-1 font-mono text-[13px]">{row.handle}</span>
                    <span className="font-mono text-[13px] tabular-nums text-muted">
                      {Math.round(row.score / 5.3)}
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
                <Avatar handle="rafalmz" size="lg" />
                <div>
                  <p className="font-medium">Rafaela Almazan</p>
                  <p className="font-mono text-xs text-muted">rafalmz</p>
                </div>
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-4">
                <div>
                  <dt className="text-[11px] text-muted">Community</dt>
                  <dd className="font-mono text-sm tabular-nums">742</dd>
                </div>
                <div>
                  <dt className="text-[11px] text-muted">Writeups</dt>
                  <dd className="font-mono text-sm tabular-nums">6</dd>
                </div>
                <div>
                  <dt className="text-[11px] text-muted">Streak</dt>
                  <dd className="font-mono text-sm tabular-nums">11d</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
