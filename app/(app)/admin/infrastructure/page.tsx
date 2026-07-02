import { HardDrives, UploadSimple } from "@phosphor-icons/react/dist/ssr";
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
import {
  instanceRegistry,
  isoLibrary,
  nodes,
  stateLabel,
  tenants,
} from "@/lib/mock";

export const metadata = { title: "Infrastructure" };

/*
 * Admin infrastructure console (Administrator / Superadministrator only).
 * Everything here reads from the Proxmox and orchestration adapters in
 * Phase 4; the template shows the target composition at density 8.
 */
export default function InfrastructurePage() {
  return (
    <>
      <Topbar title="Infrastructure" />
      <div className="space-y-6 p-6">
        {/* Hypervisor nodes */}
        <div className="grid gap-4 lg:grid-cols-3">
          {nodes.map((n) => (
            <Card key={n.name}>
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle className="font-mono">{n.name}</CardTitle>
                  <CardDescription>{n.role}</CardDescription>
                </div>
                <Badge variant="running">online</Badge>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <dt className="text-[11px] text-muted">CPU</dt>
                    <dd className="font-mono tabular-nums">{n.cpu}%</dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-muted">Memory</dt>
                    <dd className="font-mono tabular-nums">
                      {n.memUsedGb}/{n.memTotalGb}G
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-muted">Guests</dt>
                    <dd className="font-mono tabular-nums">{n.vms}</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
          {/* Instance registry */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Instance registry</CardTitle>
                <CardDescription>
                  Every ephemeral instance across all tenants, live from the
                  orchestration service.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm">
                Run reaper now
              </Button>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Owner</TableHead>
                    <TableHead>Template</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead>Node</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead className="text-right">TTL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {instanceRegistry.map((i) => (
                    <TableRow key={i.id}>
                      <TableCell className="font-mono text-xs">{i.id}</TableCell>
                      <TableCell className="font-mono text-xs">{i.owner}</TableCell>
                      <TableCell className="font-mono text-xs">{i.template}</TableCell>
                      <TableCell className="font-mono text-xs text-muted">{i.kind}</TableCell>
                      <TableCell className="font-mono text-xs text-muted">{i.node}</TableCell>
                      <TableCell>
                        <Badge variant={i.state}>{stateLabel[i.state]}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {i.ttl}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <div className="space-y-6">
            {/* ISO library */}
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle>ISO library</CardTitle>
                  <CardDescription>
                    Consumed by the Proxmox API when building VM templates.
                  </CardDescription>
                </div>
                <Button size="sm">
                  <UploadSimple size={15} />
                  Upload ISO
                </Button>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-border">
                  {isoLibrary.map((iso) => (
                    <li key={iso.name} className="py-2.5">
                      <p className="truncate font-mono text-[13px]">{iso.name}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted">
                        {iso.size} | {iso.uploaded} | {iso.by}
                      </p>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {/* Tenants */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HardDrives size={15} className="text-accent" />
                  Tenants and quotas
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tenant</TableHead>
                      <TableHead className="text-right">Instances</TableHead>
                      <TableHead className="text-right">Network</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tenants.map((t) => (
                      <TableRow key={t.name}>
                        <TableCell className="font-mono text-xs">{t.name}</TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {t.instances}/{t.quota}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs text-muted">
                          {t.network}
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
