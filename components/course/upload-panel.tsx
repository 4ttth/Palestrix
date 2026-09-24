"use client";

/*
 * Teacher upload workflow with progressive disclosure, live (Phase 5).
 *
 * Basic mode: creates an assignment on the selected course
 * (POST /courses/{id}/assignments) and attaches the file to object storage
 * (POST .../attachment).
 *
 * Advanced mode: publishes a live environment through
 * POST /labs/templates (multipart) — a Dockerfile/compose archive for
 * container labs or a Proxmox template name for VM labs — and, when a
 * course is selected, files a matching "lab" assignment so students see it.
 */

import { useEffect, useState } from "react";
import { CloudArrowUp, FileArchive, HardDrive } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type {
  AssignmentOut,
  CourseOut,
  LabTemplateOut,
  VmTemplateOut,
} from "@/lib/api/types";

/* "Blue Team: Log Triage Under Fire" -> "blue-team-log-triage-under-fire".
 * The slug field required name:version typed by hand and rejected the
 * form on a regex most teachers met only by failing it. */
function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

export function UploadPanel({
  course,
  onPublished,
}: {
  course: CourseOut | null;
  onPublished?: () => void;
}) {
  const [advanced, setAdvanced] = useState(false);
  const [envKind, setEnvKind] = useState<"container" | "vm">("container");
  const [gui, setGui] = useState<"gui" | "no-gui">("no-gui");
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [vmTemplate, setVmTemplate] = useState("");
  const [ttl, setTtl] = useState(90);
  const [file, setFile] = useState<File | null>(null);
  const [archive, setArchive] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [slugTouched, setSlugTouched] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const toast = useToast();
  // Only asked for once the teacher is actually publishing a VM lab.
  const vmTemplates = useApi<VmTemplateOut[]>(
    advanced && envKind === "vm" ? "/api/v1/labs/vm-templates" : null
  );
  const vmOptions = vmTemplates.data ?? [];

  // Keep the slug tracking the title until the teacher edits it by hand.
  useEffect(() => {
    if (slugTouched) return;
    const base = slugify(title);
    setSlug(base ? `${base}:1.0` : "");
  }, [title, slugTouched]);

  async function publish() {
    setNotice(null);
    if (title.trim().length < 4) {
      setNotice({ ok: false, text: "Give it a title (at least 4 characters)." });
      return;
    }
    setBusy(true);
    try {
      if (!advanced) {
        if (!course) throw new ApiError(0, "Select a course first.");
        if (!file) throw new ApiError(0, "Pick a file to attach.");
        const assignment = await api.post<AssignmentOut>(
          `/api/v1/courses/${course.id}/assignments`,
          { title: title.trim(), kind: "file" }
        );
        const form = new FormData();
        form.append("file", file);
        await api.postForm(
          `/api/v1/courses/${course.id}/assignments/${assignment.id}/attachment`,
          form
        );
        toast.success(
          `"${title.trim()}" published`,
          `${file.name} attached. Students in ${course.code} can see it now.`
        );
      } else {
        if (!/^[a-z0-9-]+:[0-9.]+$/.test(slug)) {
          throw new ApiError(0, 'Slug must look like "name:version", e.g. log-triage:1.4.');
        }
        const form = new FormData();
        form.append("slug", slug);
        form.append("title", title.trim());
        form.append("kind", envKind);
        form.append("access_mode", gui);
        form.append("ttl_minutes_default", String(ttl));
        form.append("ttl_minutes_max", String(Math.max(ttl, 240)));
        if (envKind === "container") {
          if (!archive)
            throw new ApiError(0, "Container labs need a Dockerfile/compose archive.");
          form.append("archive", archive);
        } else {
          if (!vmTemplate.trim())
            throw new ApiError(0, "VM labs need the Proxmox template name.");
          form.append("vm_template", vmTemplate.trim());
        }
        const template = await api.postForm<LabTemplateOut>(
          "/api/v1/labs/templates",
          form
        );
        if (course) {
          await api.post(`/api/v1/courses/${course.id}/assignments`, {
            title: title.trim(),
            kind: "lab",
            lab_template_id: template.id,
          });
        }
        toast.success(
          `${template.title} published`,
          course
            ? `Published as ${template.slug} and assigned to ${course.code}.`
            : `Published as ${template.slug}. Assign it from any course.`
        );
      }
      setTitle("");
      setSlug("");
      setSlugTouched(false);
      setFile(null);
      setArchive(null);
      onPublished?.();
    } catch (err) {
      const text =
        err instanceof ApiError ? err.message : "Publishing failed.";
      setNotice({ ok: false, text });
      toast.error(
        advanced ? "Could not publish that environment" : "Could not publish that assignment",
        text
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-(--radius-card) border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">New assignment material</h3>
          <p className="text-[13px] text-muted">
            {course
              ? `Publishing to ${course.code}. Toggle advanced for a live environment.`
              : "Select a course, or publish a live environment platform-wide."}
          </p>
        </div>
        {/* Not a <label> wrapper: a button nested in its own label double-
            fires activation in some browsers, making the switch appear to
            snap back. The whole row is one explicit toggle button instead. */}
        <button
          type="button"
          role="switch"
          aria-checked={advanced}
          onClick={() => setAdvanced((v) => !v)}
          className="group flex cursor-pointer items-center gap-2.5 text-[13px] font-medium"
        >
          Advanced: live environment
          <span
            aria-hidden
            className={cn(
              "relative inline-block h-6 w-11 shrink-0 rounded-full border transition-colors duration-150",
              advanced
                ? "border-accent bg-accent"
                : "border-border bg-surface-2 group-hover:border-accent/50"
            )}
          >
            <span
              className={cn(
                "absolute left-0.5 top-1/2 size-4.5 -translate-y-1/2 rounded-full bg-surface shadow-sm transition-transform duration-150",
                advanced ? "translate-x-5" : "translate-x-0"
              )}
            />
          </span>
        </button>
      </div>

      <div className="space-y-5 p-5">
        <div className="grid gap-2">
          <Label htmlFor="material-title">Title</Label>
          <Input
            id="material-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={advanced ? "Blue Team: Log Triage Under Fire" : "Quiz: TCP fundamentals"}
          />
        </div>

        {!advanced && (
          <div className="grid gap-2">
            <Label htmlFor="asset">Assignment file</Label>
            <label
              htmlFor="asset"
              className="flex cursor-pointer flex-col items-center gap-2 rounded-(--radius-input) border border-dashed border-border bg-surface-2/50 px-6 py-8 text-center transition-colors hover:border-accent"
            >
              <CloudArrowUp size={26} className="text-muted" />
              <span className="text-sm font-medium">
                {file ? file.name : "Drop a PDF, quiz export, or archive here"}
              </span>
              <span className="text-xs text-muted">
                Up to 200 MB, stored in object storage
              </span>
            </label>
            <input
              id="asset"
              type="file"
              className="sr-only"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
        )}

        {advanced && (
          <div className="space-y-5 rounded-(--radius-input) border border-border bg-surface-2/40 p-4">
            <div className="grid gap-2">
              <Label htmlFor="env-slug">Template slug</Label>
              <Input
                id="env-slug"
                value={slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setSlug(e.target.value);
                }}
                placeholder="log-triage:1.4"
                className="font-mono"
              />
              <p className="text-[13px] text-muted">
                Filled in from the title; edit it if you want a different
                name or version. Bump the version to publish a revision
                without disturbing labs already running.
              </p>
            </div>

            <fieldset>
              <legend className="text-[13px] font-medium">Environment source</legend>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setEnvKind("container")}
                  aria-pressed={envKind === "container"}
                  className={cn(
                    "flex items-start gap-3 rounded-(--radius-input) border p-3.5 text-left transition-colors",
                    envKind === "container"
                      ? "border-accent bg-accent-soft"
                      : "border-border bg-surface hover:bg-surface-2"
                  )}
                >
                  <FileArchive size={20} className="mt-0.5 text-accent" />
                  <span>
                    <span className="block text-sm font-medium">
                      Dockerfile or compose archive
                    </span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                      We build the image and run it as an isolated container.
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setEnvKind("vm")}
                  aria-pressed={envKind === "vm"}
                  className={cn(
                    "flex items-start gap-3 rounded-(--radius-input) border p-3.5 text-left transition-colors",
                    envKind === "vm"
                      ? "border-accent bg-accent-soft"
                      : "border-border bg-surface hover:bg-surface-2"
                  )}
                >
                  <HardDrive size={20} className="mt-0.5 text-accent" />
                  <span>
                    <span className="block text-sm font-medium">Proxmox VM template</span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                      Clone from a template built off an admin-uploaded ISO.
                    </span>
                  </span>
                </button>
              </div>
            </fieldset>

            {envKind === "vm" && (
              <div className="grid gap-2">
                <Label htmlFor="vm-template">Base template</Label>
                {/* Read from the hypervisor rather than typed from memory:
                    a mistyped name used to pass validation here and fail
                    minutes later, during provisioning, on a student's
                    screen. Free text stays available as the fallback when
                    the cluster cannot be reached. */}
                {vmOptions.length > 0 ? (
                  <select
                    id="vm-template"
                    value={vmTemplate}
                    onChange={(e) => setVmTemplate(e.target.value)}
                    className="h-10 rounded-(--radius-input) border border-border bg-surface px-3 font-mono text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  >
                    <option value="">Choose a template…</option>
                    {vmOptions.map((t) => (
                      <option key={t.vmid} value={t.name}>
                        {t.name}
                        {t.ram_mb > 0 &&
                          ` — ${t.cpu} vCPU, ${Math.round(t.ram_mb / 1024)} GB`}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    id="vm-template"
                    value={vmTemplate}
                    onChange={(e) => setVmTemplate(e.target.value)}
                    placeholder="debian12-min"
                    className="font-mono"
                  />
                )}
                <p className="text-[13px] text-muted">
                  {vmTemplates.loading
                    ? "Reading templates from the hypervisor…"
                    : vmOptions.length > 0
                      ? `${vmOptions.length} template${
                          vmOptions.length === 1 ? "" : "s"
                        } on the cluster. Each launch clones the one you pick.`
                      : "No templates readable from the hypervisor — type the name as it appears in Proxmox, or ask an administrator to build one from the ISO library."}
                </p>
              </div>
            )}

            {envKind === "container" && (
              <div className="grid gap-2">
                <Label htmlFor="archive">Environment archive</Label>
                <Input
                  id="archive"
                  type="file"
                  className="pt-2"
                  onChange={(e) => setArchive(e.target.files?.[0] ?? null)}
                />
                <p className="text-[13px] text-muted">
                  A .zip or .tar.gz containing a Dockerfile or docker-compose.yml
                  at the root.
                </p>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <fieldset>
                <legend className="text-[13px] font-medium">Student access</legend>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => setGui("gui")}
                    aria-pressed={gui === "gui"}
                    className={cn(
                      "flex-1 rounded-(--radius-input) border px-3 py-2 text-[13px] transition-colors",
                      gui === "gui"
                        ? "border-accent bg-accent-soft font-medium text-accent"
                        : "border-border bg-surface text-muted hover:bg-surface-2"
                    )}
                  >
                    GUI (noVNC)
                  </button>
                  <button
                    type="button"
                    onClick={() => setGui("no-gui")}
                    aria-pressed={gui === "no-gui"}
                    className={cn(
                      "flex-1 rounded-(--radius-input) border px-3 py-2 text-[13px] transition-colors",
                      gui === "no-gui"
                        ? "border-accent bg-accent-soft font-medium text-accent"
                        : "border-border bg-surface text-muted hover:bg-surface-2"
                    )}
                  >
                    IP and port
                  </button>
                </div>
              </fieldset>
              <div className="grid content-start gap-2">
                <Label htmlFor="ttl">TTL (minutes)</Label>
                <Input
                  id="ttl"
                  type="number"
                  value={ttl}
                  min={15}
                  max={480}
                  onChange={(e) => setTtl(Number(e.target.value) || 90)}
                />
              </div>
            </div>
          </div>
        )}

        <div aria-live="polite">
          {notice && (
            <p
              className={cn(
                "text-[13px]",
                notice.ok ? "text-running" : "text-danger"
              )}
            >
              {notice.text}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-3">
          <Button
            size="sm"
            onClick={publish}
            loading={busy}
            loadingLabel="Publishing"
          >
            {advanced ? "Publish environment" : "Attach file"}
          </Button>
        </div>
      </div>
    </div>
  );
}
