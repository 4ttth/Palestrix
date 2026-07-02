import Link from "next/link";
import { ArrowRight, Cube, Trophy } from "@phosphor-icons/react/dist/ssr";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Avatar } from "@/components/ui/avatar";
import { Countdown } from "@/components/lab/Countdown";
import {
  activeInstance,
  currentUser,
  leaderboard,
  modules,
  paths,
  stateLabel,
} from "@/lib/mock";

export const metadata = { title: "Dashboard" };

/* Student dashboard (density 8): active instance first, then progress. */
export default function DashboardPage() {
  const current = modules.find((m) => m.state === "current");

  return (
    <>
      <Topbar title="Dashboard" />
      <div className="space-y-6 p-6">
        {/* Active instance strip: the most time-critical object on screen */}
        <Card className="border-l-2 border-l-accent">
          <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5">
            <div className="flex items-center gap-4">
              <Cube size={22} className="text-accent" />
              <div>
                <p className="text-sm font-semibold tracking-tight">
                  {activeInstance.name}
                </p>
                <p className="mt-0.5 font-mono text-xs text-muted">
                  {activeInstance.id} on {activeInstance.node} via{" "}
                  {activeInstance.access.proto} {activeInstance.access.host}:
                  {activeInstance.access.port}
                </p>
              </div>
              <Badge variant={activeInstance.state}>
                {stateLabel[activeInstance.state]}
              </Badge>
            </div>
            <div className="flex items-center gap-5">
              <div className="text-right">
                <p className="text-[11px] text-muted">TTL remaining</p>
                <Countdown seconds={activeInstance.ttlRemainingSec} className="text-lg" />
              </div>
              <Link href={`/labs/${activeInstance.id}`}>
                <Button size="sm">
                  Open lab
                  <ArrowRight size={14} />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
          <div className="space-y-6">
            {/* Continue learning */}
            <Card>
              <CardHeader>
                <CardTitle>Continue learning</CardTitle>
                <CardDescription>
                  Pick up where you stopped in the SOC Analyst path.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {current && (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-(--radius-input) bg-surface-2/70 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium">{current.title}</p>
                      <p className="text-xs text-muted">{current.path}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant="palestras">+{current.palestras} P</Badge>
                      <Link href="/academy">
                        <Button variant="outline" size="sm">Resume</Button>
                      </Link>
                    </div>
                  </div>
                )}
                <ul className="mt-4 space-y-3">
                  {paths.map((p) => (
                    <li key={p.slug} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1">
                      <p className="text-sm font-medium">{p.title}</p>
                      <p className="font-mono text-xs tabular-nums text-muted">
                        {p.done}/{p.modules} modules
                      </p>
                      <Progress
                        value={(p.done / p.modules) * 100}
                        label={`${p.title} completion`}
                        className="col-span-2"
                      />
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {/* Recent activity */}
            <Card>
              <CardHeader>
                <CardTitle>This week</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-border text-sm">
                  <li className="flex items-center justify-between py-2.5">
                    <span>Captured the flag on Repeating Pad</span>
                    <span className="font-mono text-xs text-palestras">+200 P</span>
                  </li>
                  <li className="flex items-center justify-between py-2.5">
                    <span>Finished Sigma rules from scratch</span>
                    <span className="font-mono text-xs text-palestras">+55 P</span>
                  </li>
                  <li className="flex items-center justify-between py-2.5">
                    <span>Spent on hint: GraphQL Overshare</span>
                    <span className="font-mono text-xs text-expired">-75 P</span>
                  </li>
                  <li className="flex items-center justify-between py-2.5">
                    <span>Published writeup: Log triage runbook</span>
                    <span className="font-mono text-xs text-palestras">+30 P</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>

          {/* Leaderboard mini */}
          <Card className="self-start">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Trophy size={16} className="text-palestras" weight="fill" />
                CLCTF 2026 qualifiers
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2.5">
                {leaderboard.map((row) => (
                  <li
                    key={row.handle}
                    className={
                      "flex items-center gap-3 rounded-(--radius-input) px-2 py-1.5 " +
                      (row.handle === currentUser.handle ? "bg-accent-soft" : "")
                    }
                  >
                    <span className="w-5 font-mono text-xs tabular-nums text-muted">
                      {row.rank}
                    </span>
                    <Avatar handle={row.handle} size="sm" />
                    <span className="flex-1 truncate font-mono text-[13px]">
                      {row.handle}
                    </span>
                    <span className="font-mono text-[13px] tabular-nums">
                      {row.score.toLocaleString()}
                    </span>
                  </li>
                ))}
              </ol>
              <Link
                href="/compete"
                className="mt-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-accent hover:underline"
              >
                Full leaderboard
                <ArrowRight size={13} />
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
