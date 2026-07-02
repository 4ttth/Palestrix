import { CheckFat, Drop, Trophy } from "@phosphor-icons/react/dist/ssr";
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
import { challenges, firstBloodFeed, leaderboard } from "@/lib/mock";

export const metadata = { title: "Compete" };

/* CTF arena: live event view with challenge board and flag submission. */
export default function CompetePage() {
  return (
    <>
      <Topbar title="CTF arena" />
      <div className="space-y-6 p-6">
        {/* Event header */}
        <Card className="border-l-2 border-l-palestras">
          <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5">
            <div>
              <p className="text-sm font-semibold tracking-tight">
                CLCTF 2026 Qualifier Round 2
              </p>
              <p className="mt-0.5 text-[13px] text-muted">
                Individual, jeopardy style. Flags earn points and Palestras.
              </p>
            </div>
            <div className="flex items-center gap-6">
              <div className="text-right">
                <p className="text-[11px] text-muted">Ends in</p>
                <Countdown seconds={9840} className="text-lg" />
              </div>
              <div className="text-right">
                <p className="text-[11px] text-muted">Your rank</p>
                <p className="font-mono text-lg tabular-nums">4th</p>
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
                <div className="grid gap-3 md:grid-cols-2">
                  {challenges.map((c) => (
                    <div
                      key={c.id}
                      className={
                        "rounded-(--radius-input) border p-4 " +
                        (c.solved
                          ? "border-border bg-surface-2/50"
                          : "border-border bg-surface")
                      }
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className={"text-sm font-medium " + (c.solved ? "text-muted" : "")}>
                          {c.title}
                        </p>
                        {c.solved && (
                          <CheckFat size={16} weight="fill" className="shrink-0 text-running" />
                        )}
                      </div>
                      <div className="mt-2.5 flex items-center gap-2 text-xs">
                        <Badge variant="neutral">{c.category}</Badge>
                        <span className="font-mono tabular-nums text-muted">
                          {c.points} pts
                        </span>
                        <span className="font-mono tabular-nums text-muted">
                          {c.solves} solves
                        </span>
                      </div>
                      <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
                        <Drop size={12} weight="fill" className="text-expired" />
                        first blood <span className="font-mono">{c.firstBlood}</span>
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
                <form className="flex flex-wrap items-end gap-3">
                  <div className="grid min-w-64 flex-1 gap-2">
                    <Label htmlFor="flag">Flag</Label>
                    <Input
                      id="flag"
                      placeholder="CLCTF{...}"
                      className="font-mono"
                      aria-describedby="flag-help"
                    />
                    <p id="flag-help" className="text-[13px] text-muted">
                      Paste the exact flag, braces included.
                    </p>
                  </div>
                  <Button type="submit" className="mb-7">
                    Submit flag
                  </Button>
                </form>
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
                <ul className="space-y-3">
                  {firstBloodFeed.map((f) => (
                    <li key={f.challenge} className="flex items-center gap-3 text-sm">
                      <Avatar handle={f.handle} size="sm" />
                      <span className="min-w-0 flex-1 truncate">
                        <span className="font-mono text-[13px]">{f.handle}</span>{" "}
                        <span className="text-muted">drew first blood on</span>{" "}
                        {f.challenge}
                      </span>
                      <span className="font-mono text-xs text-muted">{f.ago}</span>
                    </li>
                  ))}
                </ul>
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
                    {leaderboard.map((row) => (
                      <TableRow key={row.handle}>
                        <TableCell className="font-mono text-xs tabular-nums text-muted">
                          {row.rank}
                        </TableCell>
                        <TableCell className="font-mono text-[13px]">{row.handle}</TableCell>
                        <TableCell className="text-right font-mono text-[13px] tabular-nums">
                          {row.score.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums text-muted">
                          {row.firstBloods}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
