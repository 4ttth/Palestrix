import { ShieldWarning, UploadSimple } from "@phosphor-icons/react/dist/ssr";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fsEvents, netEvents, sandboxAnalyses } from "@/lib/mock";

export const metadata = { title: "Sandbox" };

const verdictVariant = {
  malicious: "expired",
  suspicious: "palestras",
  clean: "running",
} as const;

const flagClass: Record<string, string> = {
  malicious: "text-expired",
  suspicious: "text-palestras",
  info: "text-muted",
};

/*
 * Malware sandbox module: submissions detonate on the isolated Docker host
 * (sandbox-01, no route to tenant or campus networks; see
 * docs/sandbox-security.md). The template shows a finished analysis.
 */
export default function SandboxPage() {
  return (
    <>
      <Topbar title="Malware sandbox" />
      <div className="space-y-6 p-6">
        <div className="grid gap-6 xl:grid-cols-[1fr_1.6fr]">
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Detonate a sample</CardTitle>
                <CardDescription>
                  Runs on an isolated host with no route to lab or campus
                  networks. Analyses are private to your account.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <label
                  htmlFor="sample"
                  className="flex cursor-pointer flex-col items-center gap-2 rounded-(--radius-input) border border-dashed border-border bg-surface-2/50 px-6 py-10 text-center transition-colors hover:border-accent"
                >
                  <UploadSimple size={26} className="text-muted" />
                  <span className="text-sm font-medium">Drop a file to analyze</span>
                  <span className="text-xs text-muted">
                    Up to 100 MB. Archives are extracted with a password of
                    "infected".
                  </span>
                </label>
                <input id="sample" type="file" className="sr-only" />
                <div className="mt-4 flex items-start gap-2.5 rounded-(--radius-input) bg-expired-soft p-3 text-[13px] leading-relaxed text-expired">
                  <ShieldWarning size={17} className="mt-0.5 shrink-0" />
                  Handle real malware only inside this module. Never download
                  samples to your own machine.
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recent analyses</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-border">
                  {sandboxAnalyses.map((a) => (
                    <li key={a.id} className="flex items-center gap-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-mono text-[13px]">{a.file}</p>
                        <p className="font-mono text-[11px] text-muted">
                          {a.id} at {a.submitted}
                        </p>
                      </div>
                      <Badge variant={verdictVariant[a.verdict as keyof typeof verdictVariant]}>
                        {a.verdict}
                      </Badge>
                    </li>
                  ))}
                </ul>
                {/* Empty state, shown when the account has no analyses yet */}
                {sandboxAnalyses.length === 0 && (
                  <div className="rounded-(--radius-input) border border-dashed border-border px-6 py-10 text-center">
                    <p className="text-sm font-medium">The detonation queue is empty</p>
                    <p className="mt-1 text-[13px] text-muted">
                      Submit your first sample above to see behavior traces here.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="font-mono">invoice_scan.pdf.exe</CardTitle>
                  <CardDescription className="font-mono">
                    sha256 9f86d081884c7d65... | det-0917 | 214 fs events, 12 net events
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="expired">malicious</Badge>
                  <Button variant="outline" size="sm">Export report</Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <h4 className="text-[13px] font-medium text-muted">File system</h4>
                <Table className="mt-2">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>PID</TableHead>
                      <TableHead>Operation</TableHead>
                      <TableHead>Path</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {fsEvents.map((e) => (
                      <TableRow key={e.time}>
                        <TableCell className="font-mono text-xs text-muted">{e.time}</TableCell>
                        <TableCell className="font-mono text-xs">{e.pid}</TableCell>
                        <TableCell className={`font-mono text-xs ${flagClass[e.flag]}`}>
                          {e.op}
                        </TableCell>
                        <TableCell className="max-w-[280px] truncate font-mono text-xs">
                          {e.path}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div>
                <h4 className="text-[13px] font-medium text-muted">Network</h4>
                <Table className="mt-2">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Proto</TableHead>
                      <TableHead>Destination</TableHead>
                      <TableHead className="text-right">Port</TableHead>
                      <TableHead className="text-right">Bytes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {netEvents.map((e) => (
                      <TableRow key={e.time}>
                        <TableCell className="font-mono text-xs text-muted">{e.time}</TableCell>
                        <TableCell className="font-mono text-xs">{e.proto}</TableCell>
                        <TableCell className={`font-mono text-xs ${flagClass[e.flag]}`}>
                          {e.dest}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">{e.port}</TableCell>
                        <TableCell className="text-right font-mono text-xs">{e.bytes}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
