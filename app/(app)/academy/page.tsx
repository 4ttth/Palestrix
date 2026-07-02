import { CheckCircle, Circle, Lock, SealCheck } from "@phosphor-icons/react/dist/ssr";
import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { modules, paths } from "@/lib/mock";

export const metadata = { title: "Academy" };

const stateIcon = {
  done: <CheckCircle size={17} weight="fill" className="text-running" />,
  current: <Circle size={17} weight="bold" className="text-accent" />,
  locked: <Lock size={17} className="text-muted" />,
};

/* Academy: roadmaps, module walkthroughs, certification states. */
export default function AcademyPage() {
  return (
    <>
      <Topbar title="Academy" />
      <div className="space-y-6 p-6">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {paths.map((p) => (
            <Card key={p.slug}>
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle>{p.title}</CardTitle>
                  {p.certified && (
                    <Badge variant="running">
                      <SealCheck size={13} weight="fill" />
                      Certified
                    </Badge>
                  )}
                </div>
                <CardDescription>
                  {p.modules} modules, about {p.hours} hours
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between text-xs text-muted">
                  <span>Progress</span>
                  <span className="font-mono tabular-nums">
                    {p.done}/{p.modules}
                  </span>
                </div>
                <Progress
                  value={(p.done / p.modules) * 100}
                  label={`${p.title} completion`}
                  className="mt-2"
                />
                <Button
                  variant={p.done > 0 && !p.certified ? "primary" : "outline"}
                  size="sm"
                  className="mt-4 w-full"
                >
                  {p.certified ? "Review path" : p.done > 0 ? "Continue" : "Start path"}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>SOC Analyst roadmap</CardTitle>
            <CardDescription>
              Modules unlock in order. The capstone incident opens once every
              prior module is complete.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="divide-y divide-border">
              {modules.map((m) => (
                <li key={m.title} className="flex items-center gap-3.5 py-3">
                  {stateIcon[m.state]}
                  <div className="flex-1">
                    <p
                      className={
                        "text-sm " +
                        (m.state === "locked" ? "text-muted" : "font-medium")
                      }
                    >
                      {m.title}
                    </p>
                  </div>
                  <Badge variant="palestras">+{m.palestras} P</Badge>
                  {m.state === "current" ? (
                    <Button size="sm">Open walkthrough</Button>
                  ) : (
                    <span className="w-[132px]" />
                  )}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Card className="bg-accent-soft">
          <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5">
            <div>
              <p className="text-sm font-semibold tracking-tight">
                Certification state: 2 of 5 checkpoints passed
              </p>
              <p className="mt-1 text-[13px] text-muted">
                Finish the capstone incident to schedule your practical exam
                with your teacher.
              </p>
            </div>
            <Button variant="secondary" size="sm">
              View certification requirements
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
