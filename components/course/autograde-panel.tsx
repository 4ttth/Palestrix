"use client";

/*
 * Teacher setup for automated checking (docs/automated-checking.md).
 *
 * Pick one of your published lab templates, then either:
 * - diff mode: upload the finished system's archive — the checker diffs it
 *   against the template's own (unfinished) archive and every difference
 *   group becomes a weighted objective; or
 * - winfile mode: the server mints randomized win scripts to plant in the
 *   image; students must find and execute them.
 *
 * Weights must tally to exactly 100% before publishing; publishing locks
 * the rubric and turns grading on for every instance of the template.
 */

import { useMemo, useState } from "react";
import { CheckCircle, DownloadSimple, Scales } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { API_ORIGIN, api, ApiError, readToken } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { cn } from "@/lib/utils";
import type { GradingSchemeOut, LabTemplateOut } from "@/lib/api/types";

async function downloadWinfile(schemeId: string, itemId: string, filename: string) {
  const resp = await fetch(
    `${API_ORIGIN}/api/v1/grading/schemes/${schemeId}/winfiles/${itemId}`,
    { headers: { Authorization: `Bearer ${readToken() ?? ""}` } }
  );
  if (!resp.ok) throw new ApiError(resp.status, "download failed");
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function SchemeEditor({
  scheme,
  onChanged,
}: {
  scheme: GradingSchemeOut;
  onChanged: () => void;
}) {
  const [weights, setWeights] = useState<Record<string, number>>(
    Object.fromEntries(scheme.items.map((i) => [i.id, i.weight_percent]))
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const draft = scheme.status === "draft";
  const total = Object.values(weights).reduce((a, b) => a + (b || 0), 0);

  async function run(kind: string, fn: () => Promise<unknown>) {
    setBusy(kind);
    setNotice(null);
    try {
      await fn();
      onChanged();
    } catch (err) {
      setNotice({
        ok: false,
        text: err instanceof ApiError ? err.message : `${kind} failed.`,
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant={scheme.status === "published" ? "running" : "accent"}>
            {scheme.status}
          </Badge>
          <span className="text-[13px] text-muted">
            {scheme.kind === "diff"
              ? `${scheme.analysis.differences ?? scheme.items.length} differences found`
              : `${scheme.items.length} win files`}
          </span>
        </div>
        <span
          className={cn(
            "font-mono text-sm tabular-nums",
            total === 100 ? "text-running" : "text-expired"
          )}
        >
          {total}/100%
        </span>
      </div>

      <div className="space-y-2">
        {scheme.items.map((item) => (
          <div
            key={item.id}
            className="flex items-start justify-between gap-3 rounded-(--radius-input) border border-border px-3 py-2.5"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium">{item.title}</p>
              <p className="truncate font-mono text-[11px] text-muted" title={item.detail}>
                {item.win_filename ?? item.paths.join(", ")}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {item.win_filename && (
                <Button
                  variant="ghost"
                  size="sm"
                  title={`Download ${item.win_filename}`}
                  onClick={() =>
                    void downloadWinfile(scheme.id, item.id, item.win_filename!)
                  }
                >
                  <DownloadSimple size={15} />
                </Button>
              )}
              {draft ? (
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={weights[item.id] ?? 0}
                  onChange={(e) =>
                    setWeights((w) => ({
                      ...w,
                      [item.id]: Number(e.target.value),
                    }))
                  }
                  className="w-20 text-right font-mono"
                  aria-label={`Weight for ${item.title}`}
                />
              ) : (
                <span className="font-mono text-sm tabular-nums">
                  {item.weight_percent}%
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {draft && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null}
            onClick={() =>
              run("save", () =>
                api.patch(`/api/v1/grading/schemes/${scheme.id}/weights`, {
                  weights,
                })
              )
            }
          >
            {busy === "save" ? "Saving..." : "Save weights"}
          </Button>
          <Button
            size="sm"
            disabled={busy !== null || total !== 100}
            title={total !== 100 ? "Weights must tally to exactly 100%" : undefined}
            onClick={() =>
              run("publish", async () => {
                await api.patch(`/api/v1/grading/schemes/${scheme.id}/weights`, {
                  weights,
                });
                await api.post(`/api/v1/grading/schemes/${scheme.id}/publish`);
              })
            }
          >
            <CheckCircle size={15} />
            {busy === "publish" ? "Publishing..." : "Publish rubric"}
          </Button>
          {scheme.kind === "winfile" && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy !== null}
              title="Fresh tokens and filenames; previously downloaded scripts stop counting"
              onClick={() => {
                const form = new FormData();
                form.append("winfiles", String(scheme.items.length));
                void run("regenerate", () =>
                  api.postForm(`/api/v1/grading/schemes/${scheme.id}/regenerate`, form)
                );
              }}
            >
              {busy === "regenerate" ? "Regenerating..." : "Regenerate"}
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-expired"
            disabled={busy !== null}
            onClick={() =>
              run("discard", () => api.del(`/api/v1/grading/schemes/${scheme.id}`))
            }
          >
            {busy === "discard" ? "Discarding..." : "Discard"}
          </Button>
        </div>
      )}
      {!draft && (
        <p className="text-[13px] leading-relaxed text-muted">
          Published and locked. Every instance of this template is now graded
          at hand-in, stop, destroy, or TTL expiry — whichever comes first.
        </p>
      )}
      {notice && (
        <p role="alert" className="text-[13px] text-expired">
          {notice.text}
        </p>
      )}
    </div>
  );
}

function NewSchemeForm({
  template,
  onCreated,
}: {
  template: LabTemplateOut;
  onCreated: () => void;
}) {
  const [kind, setKind] = useState<"diff" | "winfile">(
    template.kind === "container" ? "diff" : "winfile"
  );
  const [finished, setFinished] = useState<File | null>(null);
  const [count, setCount] = useState(3);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setFailure(null);
    try {
      const form = new FormData();
      form.append("lab_template_id", template.id);
      form.append("kind", kind);
      if (kind === "diff") {
        if (!finished) throw new ApiError(0, "Upload the finished system's archive.");
        form.append("finished", finished);
      } else {
        form.append("winfiles", String(count));
      }
      await api.postForm("/api/v1/grading/schemes", form);
      onCreated();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Creation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(["diff", "winfile"] as const).map((k) => (
          <button
            key={k}
            type="button"
            disabled={k === "diff" && template.kind !== "container"}
            onClick={() => setKind(k)}
            className={cn(
              "rounded-full px-3 py-1 text-[12px] font-medium transition-colors",
              kind === k
                ? "bg-accent-soft text-accent"
                : "bg-surface-2 text-muted hover:text-foreground",
              k === "diff" && template.kind !== "container" && "opacity-40"
            )}
          >
            {k === "diff" ? "Finished vs unfinished" : "Win files"}
          </button>
        ))}
      </div>

      {kind === "diff" ? (
        <div className="grid gap-2">
          <Label htmlFor="finished-archive">
            Finished system archive (.tar.gz)
          </Label>
          <Input
            id="finished-archive"
            type="file"
            accept=".tar,.tar.gz,.tgz"
            onChange={(e) => setFinished(e.target.files?.[0] ?? null)}
          />
          <p className="text-[12px] leading-relaxed text-muted">
            Your published archive is the unfinished system students receive.
            The checker diffs the two and each difference group (SSH, MOTD,
            users, ...) becomes a weighted objective.
          </p>
        </div>
      ) : (
        <div className="grid gap-2">
          <Label htmlFor="winfile-count">Number of win files (1-10)</Label>
          <Input
            id="winfile-count"
            type="number"
            min={1}
            max={10}
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            className="w-24"
          />
          <p className="text-[12px] leading-relaxed text-muted">
            Randomized on every generation. Download each script, plant it in
            your image, and students must find and execute it — execution
            embeds a marker the checker verifies.
          </p>
        </div>
      )}

      <Button size="sm" disabled={busy} onClick={() => void create()}>
        {busy ? "Analyzing..." : "Create rubric"}
      </Button>
      {failure && (
        <p role="alert" className="text-[13px] text-expired">
          {failure}
        </p>
      )}
    </div>
  );
}

export function AutogradePanel() {
  const { user } = useSession();
  const templates = useApi<LabTemplateOut[]>("/api/v1/labs/templates");
  const [selectedId, setSelectedId] = useState<string>("");

  const mine = useMemo(
    () =>
      (templates.data ?? []).filter(
        (t) => t.owner_id === user.id || user.role === "superadmin"
      ),
    [templates.data, user]
  );
  const selected = mine.find((t) => t.id === selectedId) ?? mine[0] ?? null;

  const schemes = useApi<GradingSchemeOut[]>(
    selected ? `/api/v1/grading/schemes?lab_template_id=${selected.id}` : null
  );
  const scheme = schemes.data?.[0] ?? null;

  return (
    <div className="rounded-(--radius-card) border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex items-center gap-2.5">
          <Scales size={18} className="text-accent" />
          <div>
            <h3 className="text-sm font-semibold">Automated checking</h3>
            <p className="text-[12px] text-muted">
              Rubric-graded labs: the checker scores every instance against
              your finished system or win files.
            </p>
          </div>
        </div>
      </div>
      <div className="space-y-4 p-5">
        {mine.length === 0 ? (
          <p className="text-[13px] text-muted">
            Publish a live environment first — rubrics attach to your lab
            templates.
          </p>
        ) : (
          <>
            <div className="grid gap-2">
              <Label htmlFor="autograde-template">Lab template</Label>
              <select
                id="autograde-template"
                value={selected?.id ?? ""}
                onChange={(e) => setSelectedId(e.target.value)}
                className="h-9 rounded-(--radius-input) border border-border bg-surface px-3 text-sm"
              >
                {mine.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title} ({t.slug})
                  </option>
                ))}
              </select>
            </div>
            {selected && schemes.data && scheme === null && (
              <NewSchemeForm
                template={selected}
                onCreated={() => void schemes.refetch()}
              />
            )}
            {scheme && (
              <SchemeEditor scheme={scheme} onChanged={() => void schemes.refetch()} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
