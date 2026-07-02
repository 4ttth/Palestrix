import { ArrowClockwise, Power, Trash } from "@phosphor-icons/react/dist/ssr";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Countdown } from "@/components/lab/Countdown";
import { ProvisioningLog } from "@/components/lab/ProvisioningLog";
import { activeInstance, provisioningSample, stateLabel } from "@/lib/mock";

export const metadata = { title: "Active lab" };

/*
 * Active ephemeral lab view. GUI labs render the noVNC console in the main
 * region; headless labs (like this template's mock) surface the connection
 * endpoint. Phase 4 replaces the sample log with the live SSE stream.
 */
export default async function LabPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const instance = { ...activeInstance, id };

  return (
    <>
      <Topbar title="Active lab" />
      <div className="space-y-6 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold tracking-tight">{instance.name}</h2>
              <Badge variant={instance.state}>{stateLabel[instance.state]}</Badge>
            </div>
            <p className="mt-1 font-mono text-xs text-muted">
              {instance.id} | tenant {instance.tenant} | node {instance.node} |{" "}
              {instance.course}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" title="Costs 150 Palestras">
              <ArrowClockwise size={15} />
              Extend 30 min
            </Button>
            <Button variant="outline" size="sm">
              <Power size={15} />
              Stop
            </Button>
            <Button variant="destructive" size="sm">
              <Trash size={15} />
              Destroy
            </Button>
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
          <div className="space-y-6">
            {/* Console region: noVNC iframe mounts here for GUI labs */}
            <Card>
              <CardHeader>
                <CardTitle>Connection</CardTitle>
                <CardDescription>
                  This lab is headless. Connect over {instance.access.proto} from
                  the campus network or the event VPN.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-center gap-3">
                  <code className="rounded-(--radius-input) bg-surface-2 px-4 py-2.5 font-mono text-sm">
                    ssh student@{instance.access.host} -p {instance.access.port}
                  </code>
                  <Button variant="outline" size="sm">
                    Copy command
                  </Button>
                </div>
                <p className="mt-3 text-[13px] text-muted">
                  Credentials were issued when the instance started and die with
                  it. GUI labs replace this panel with the noVNC console.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Provisioning log</CardTitle>
                <CardDescription>
                  Every line is a real event from the orchestration worker.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ProvisioningLog lines={provisioningSample} replay={false} />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Time to live</CardTitle>
              </CardHeader>
              <CardContent>
                <Countdown seconds={instance.ttlRemainingSec} className="text-3xl" />
                <p className="mt-2 text-[13px] leading-relaxed text-muted">
                  Started {instance.startedAt.slice(11, 16)} with a{" "}
                  {instance.ttlTotalMin}-minute budget. At zero the reaper stops
                  and destroys this instance and releases your tenant quota.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Objectives</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="space-y-2.5 text-sm">
                  <li className="flex gap-2.5">
                    <span className="font-mono text-xs text-running">done</span>
                    <span className="text-muted line-through">
                      Locate the brute-force source in auth.log
                    </span>
                  </li>
                  <li className="flex gap-2.5">
                    <span className="font-mono text-xs text-accent">now</span>
                    <span>Identify the compromised account</span>
                  </li>
                  <li className="flex gap-2.5">
                    <span className="font-mono text-xs text-muted">next</span>
                    <span className="text-muted">Submit the attacker's persistence path</span>
                  </li>
                </ol>
                <div className="mt-4 border-t border-border pt-4">
                  <Button variant="outline" size="sm" className="w-full" title="Costs 75 Palestras">
                    Reveal a hint for 75 P
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
