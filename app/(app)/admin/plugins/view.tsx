"use client";

/*
 * Plugin console (Superadministrator only — plugins:manage is the one
 * capability no machine scope covers). Renders the discovered registry
 * honestly: state, requested scopes, config contract. Enabling walks the
 * manifest: fill required/optional config, approve the scopes, go. The API
 * refuses enables with missing config (422) or unapproved scopes (409) and
 * those messages surface verbatim.
 */

import { useState, type FormEvent } from "react";
import { PuzzlePiece } from "@phosphor-icons/react";
import { Topbar } from "@/components/shell/topbar";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Empty, LoadFailed, Loading } from "@/components/ui/async";
import { api, ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import type { PluginOut } from "@/lib/api/types";

// Registry states: discovered | enabled | unsupported | error
const STATE_BADGE: Record<string, "running" | "neutral" | "failed" | "palestras"> = {
  enabled: "running",
  discovered: "neutral",
  error: "failed",
  unsupported: "palestras",
};

export function PluginsView() {
  const { user } = useSession();
  const plugins = useApi<PluginOut[]>("/api/v1/plugins");
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);

  if (user.role !== "superadmin") {
    return (
      <>
        <Topbar title="Plugins" />
        <div className="p-4 sm:p-6">
          <Empty
            title="Superadministrators only"
            hint="Plugin management requires the plugins:manage capability (docs/rbac-matrix.md)."
          />
        </div>
      </>
    );
  }

  return (
    <>
      <Topbar title="Plugins" />
      <div className="space-y-6 p-4 sm:p-6">
        <p className="flex max-w-[80ch] items-start gap-2.5 rounded-(--radius-card) border border-border bg-surface px-5 py-4 text-[13px] leading-relaxed text-muted">
          <PuzzlePiece size={17} className="mt-0.5 shrink-0 text-accent" />
          Plugins are discovered from installed packages and
          PALESTRIX_PLUGIN_PATHS. Enabling grants exactly the scopes you
          approve — a plugin can never exceed them (docs/plugin-development.md).
        </p>

        {notice && (
          <p
            aria-live="polite"
            className={
              "rounded-(--radius-input) px-4 py-3 font-mono text-xs " +
              (notice.ok ? "bg-accent-soft text-accent" : "bg-expired-soft text-expired")
            }
          >
            {notice.text}
          </p>
        )}

        {plugins.loading && <Loading label="loading registry" />}
        {plugins.error && <LoadFailed error={plugins.error} retry={plugins.refetch} />}
        {plugins.data && plugins.data.length === 0 && (
          <Empty
            title="No plugins discovered"
            hint="Install a plugin package, or point PALESTRIX_PLUGIN_PATHS at a development plugin directory, and restart the API."
          />
        )}

        <div className="grid gap-6 xl:grid-cols-2">
          {(plugins.data ?? []).map((p) => (
            <PluginCard
              key={p.id}
              plugin={p}
              onChanged={(text, ok) => {
                setNotice({ ok, text });
                void plugins.refetch();
              }}
            />
          ))}
        </div>
      </div>
    </>
  );
}

function PluginCard({
  plugin,
  onChanged,
}: {
  plugin: PluginOut;
  onChanged: (text: string, ok: boolean) => void;
}) {
  const [config, setConfig] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [showEnable, setShowEnable] = useState(false);

  const enabled = plugin.state === "enabled";
  const configFields = [
    ...plugin.config_required.map((k) => ({ key: k, required: true })),
    ...plugin.config_optional.map((k) => ({ key: k, required: false })),
  ];

  async function enable(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = {
        config: Object.fromEntries(
          Object.entries(config).filter(([, v]) => v.trim() !== "")
        ),
        approve_scopes: plugin.scopes,
      };
      await api.post<PluginOut>(`/api/v1/plugins/${plugin.id}/enable`, body);
      setShowEnable(false);
      setConfig({});
      onChanged(`Plugin ${plugin.id} enabled.`, true);
    } catch (err) {
      onChanged(
        err instanceof ApiError ? err.message : `Enabling ${plugin.id} failed.`,
        false
      );
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    try {
      await api.post<PluginOut>(`/api/v1/plugins/${plugin.id}/disable`);
      onChanged(`Plugin ${plugin.id} disabled.`, true);
    } catch (err) {
      onChanged(
        err instanceof ApiError ? err.message : `Disabling ${plugin.id} failed.`,
        false
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{plugin.id}</span>
            <Badge variant={STATE_BADGE[plugin.state] ?? "neutral"}>
              {plugin.state}
            </Badge>
          </CardTitle>
          <CardDescription>
            {plugin.name} v{plugin.version} · API {plugin.api} ·{" "}
            <span className="font-mono">{plugin.source}</span>
          </CardDescription>
        </div>
        {enabled ? (
          <Button variant="outline" size="sm" disabled={busy} onClick={disable}>
            Disable
          </Button>
        ) : (
          <Button
            size="sm"
            disabled={busy || plugin.state === "unsupported"}
            onClick={() => setShowEnable((v) => !v)}
          >
            Enable...
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {plugin.error && (
          <p className="rounded-(--radius-input) bg-expired-soft px-3 py-2 font-mono text-[11px] text-expired">
            {plugin.error}
          </p>
        )}

        <div>
          <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted">
            {enabled ? "Granted scopes" : "Requested scopes"}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {(enabled ? plugin.granted_scopes : plugin.scopes).length === 0 && (
              <span className="text-[13px] text-muted">none</span>
            )}
            {(enabled ? plugin.granted_scopes : plugin.scopes).map((s) => (
              <Badge key={s} variant="accent" className="font-mono text-[10px]">
                {s}
              </Badge>
            ))}
          </div>
        </div>

        {showEnable && !enabled && (
          <form
            onSubmit={enable}
            className="space-y-3 rounded-(--radius-input) border border-border bg-surface-2/40 p-4"
          >
            {configFields.length === 0 ? (
              <p className="text-[13px] text-muted">
                No configuration needed. Enabling approves the scopes above.
              </p>
            ) : (
              configFields.map(({ key, required }) => (
                <div key={key} className="grid gap-1.5">
                  <Label htmlFor={`cfg-${plugin.id}-${key}`}>
                    <span className="font-mono">{key}</span>
                    {!required && (
                      <span className="ml-1.5 text-[11px] text-muted">(optional)</span>
                    )}
                    {plugin.config_secret.includes(key) && (
                      <span className="ml-1.5 text-[11px] text-palestras">secret</span>
                    )}
                  </Label>
                  <Input
                    id={`cfg-${plugin.id}-${key}`}
                    type={plugin.config_secret.includes(key) ? "password" : "text"}
                    required={required}
                    value={config[key] ?? ""}
                    onChange={(e) =>
                      setConfig((c) => ({ ...c, [key]: e.target.value }))
                    }
                    className="h-9 font-mono text-[13px]"
                  />
                </div>
              ))
            )}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={busy}>
                {busy ? "Enabling..." : "Approve scopes and enable"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowEnable(false)}
              >
                Cancel
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
