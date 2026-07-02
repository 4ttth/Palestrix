"use client";

/*
 * Teacher upload workflow with progressive disclosure.
 *
 * Basic mode: one file input for quiz/assignment assets (stored in MinIO/S3).
 * Advanced mode: the same form grows into environment publishing, either a
 * Dockerfile/compose archive or a Proxmox VM template, plus GUI choice,
 * TTL, and tenant isolation. Phase 4 wires this to
 * POST /api/v1/labs/templates (multipart) and the orchestration queue.
 */

import { useState } from "react";
import { CloudArrowUp, FileArchive, HardDrive } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const vmTemplates = [
  "kali-web:2.1 (Kali Linux, 2 vCPU, 4 GB)",
  "forensics-win11:3.0 (Windows 11, 4 vCPU, 8 GB)",
  "pwn-arena:1.9 (Debian, 1 vCPU, 1 GB)",
];

export function UploadPanel() {
  const [advanced, setAdvanced] = useState(false);
  const [envKind, setEnvKind] = useState<"container" | "vm">("container");
  const [gui, setGui] = useState<"gui" | "no-gui">("no-gui");

  return (
    <div className="rounded-(--radius-card) border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">New assignment material</h3>
          <p className="text-[13px] text-muted">
            Start with a file. Toggle advanced to publish a live environment.
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2.5 text-[13px] font-medium">
          Advanced: live environment
          <button
            type="button"
            role="switch"
            aria-checked={advanced}
            onClick={() => setAdvanced((v) => !v)}
            className={cn(
              "relative h-5.5 w-10 rounded-full transition-colors duration-150",
              advanced ? "bg-accent" : "bg-surface-2 border border-border"
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 size-4.5 rounded-full bg-surface shadow-sm transition-transform duration-150",
                advanced ? "translate-x-5" : "translate-x-0.5"
              )}
            />
          </button>
        </label>
      </div>

      <div className="space-y-5 p-5">
        {/* Basic mode: always visible */}
        <div className="grid gap-2">
          <Label htmlFor="asset">Assignment file</Label>
          <label
            htmlFor="asset"
            className="flex cursor-pointer flex-col items-center gap-2 rounded-(--radius-input) border border-dashed border-border bg-surface-2/50 px-6 py-8 text-center transition-colors hover:border-accent"
          >
            <CloudArrowUp size={26} className="text-muted" />
            <span className="text-sm font-medium">
              Drop a PDF, quiz export, or archive here
            </span>
            <span className="text-xs text-muted">Up to 200 MB, stored in object storage</span>
          </label>
          <input id="asset" type="file" className="sr-only" />
        </div>

        {advanced && (
          <div className="space-y-5 rounded-(--radius-input) border border-border bg-surface-2/40 p-4">
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
                <Label htmlFor="vm-template">VM template</Label>
                <select
                  id="vm-template"
                  className="h-10 w-full rounded-(--radius-input) border border-border bg-surface px-3 text-sm"
                >
                  {vmTemplates.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                  <option>Request a new template from an administrator</option>
                </select>
              </div>
            )}

            {envKind === "container" && (
              <div className="grid gap-2">
                <Label htmlFor="archive">Environment archive</Label>
                <Input id="archive" type="file" className="pt-2" />
                <p className="text-[13px] text-muted">
                  A .zip or .tar.gz containing a Dockerfile or docker-compose.yml
                  at the root.
                </p>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-3">
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
                <Input id="ttl" type="number" defaultValue={90} min={15} max={480} />
              </div>
              <div className="grid content-start gap-2">
                <Label htmlFor="tenant">Tenant isolation</Label>
                <select
                  id="tenant"
                  className="h-10 w-full rounded-(--radius-input) border border-border bg-surface px-3 text-sm"
                >
                  <option>Per section (hau-bscs-3a)</option>
                  <option>Per student</option>
                  <option>Shared event network</option>
                </select>
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button variant="ghost" size="sm">
            Save draft
          </Button>
          <Button size="sm">
            {advanced ? "Publish environment" : "Attach file"}
          </Button>
        </div>
      </div>
    </div>
  );
}
