import { Topbar } from "@/components/shell/topbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { UploadPanel } from "@/components/course/upload-panel";
import { assignments, courses } from "@/lib/mock";

export const metadata = { title: "Courses" };

/* Course and assignment manager (Teacher role view). */
export default function CoursesPage() {
  return (
    <>
      <Topbar title="Course manager" />
      <div className="space-y-6 p-6">
        <div className="grid gap-4 lg:grid-cols-3">
          {courses.map((c) => (
            <Card key={c.code}>
              <CardHeader>
                <CardTitle>{c.title}</CardTitle>
                <CardDescription>
                  <span className="font-mono">{c.code}</span> for {c.section}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex gap-6 text-sm">
                <div>
                  <p className="font-mono text-lg tabular-nums">{c.students}</p>
                  <p className="text-xs text-muted">students</p>
                </div>
                <div>
                  <p className="font-mono text-lg tabular-nums">{c.assignments}</p>
                  <p className="text-xs text-muted">assignments</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
          <Card>
            <CardHeader>
              <CardTitle>Assignments: Defensive Operations 201</CardTitle>
              <CardDescription>
                Submission counts update live once the API lands.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Due</TableHead>
                    <TableHead className="text-right">Submitted</TableHead>
                    <TableHead className="text-right">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {assignments.map((a) => (
                    <TableRow key={a.title}>
                      <TableCell className="font-medium">{a.title}</TableCell>
                      <TableCell className="text-muted">{a.type}</TableCell>
                      <TableCell className="font-mono text-xs">{a.due}</TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">
                        {a.submitted}/{a.total}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge variant={a.state === "graded" ? "running" : "accent"}>
                          {a.state === "graded" ? "Graded" : "Open"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <UploadPanel />
        </div>
      </div>
    </>
  );
}
