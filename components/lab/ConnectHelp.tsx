"use client";

/*
 * "How do I connect?" — the help a student needs beside a lab endpoint.
 *
 * The address on the lab page (10.24.x.x) lives on an isolated tenant VLAN
 * with no route off it, so it is unreachable from a laptop until the student
 * joins the overlay network. Without this panel the endpoint reads like a
 * broken lab; with it, the address and the way to reach it sit together.
 *
 * Deployment-specific values come from GET /instances/access, so nothing
 * here is hardcoded to one site. When no overlay is configured the modal
 * says so instead of printing steps that cannot work.
 *
 * Built on <dialog>, which gives focus trapping, Escape-to-close and the
 * top layer for free — the codebase has no dialog primitive to reuse.
 */

import { useEffect, useRef, useState } from "react";
import { Check, Copy, Question, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/hooks";
import type { RemoteAccessOut } from "@/lib/api/types";

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden
        className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-[12px] font-semibold text-accent"
      >
        {n}
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <div className="mt-1 space-y-2 text-[13px] leading-relaxed text-muted">{children}</div>
      </div>
    </li>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="block overflow-x-auto rounded-md bg-surface-2 px-3 py-2 font-mono text-[12px] text-foreground">
      {children}
    </code>
  );
}

/* The one join command, with a copy button — this is the single step a
 * student actually has to perform, so it earns one-click copy and a
 * confirmation that the click landed. */
function CopyCode({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard blocked (insecure context / permissions): the text is
      // still selectable, so this is a convenience, not the only way.
    }
  }
  return (
    <div className="flex items-stretch gap-2">
      <code className="block flex-1 overflow-x-auto rounded-md bg-surface-2 px-3 py-2 font-mono text-[12px] text-foreground">
        {text}
      </code>
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy command"}
        className="shrink-0 rounded-md border border-border px-2.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        {copied ? (
          <Check className="size-4 text-running plx-pop" aria-hidden />
        ) : (
          <Copy className="size-4" aria-hidden />
        )}
      </button>
    </div>
  );
}

export function ConnectHelp({ endpoint }: { endpoint: string | null }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  // Only fetched once the student asks — this is help, not page-critical data.
  const access = useApi<RemoteAccessOut>(open ? "/api/v1/instances/access" : null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  const info = access.data;

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        <Question className="size-4" aria-hidden />
        How do I connect?
      </Button>

      <dialog
        ref={ref}
        onClose={() => setOpen(false)}
        onClick={(e) => {
          // Backdrop clicks land on the dialog element itself.
          if (e.target === ref.current) setOpen(false);
        }}
        aria-labelledby="connect-help-title"
        className="m-auto w-[min(34rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-0 text-foreground backdrop:bg-black/50"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h2 id="connect-help-title" className="text-base font-semibold">
              Connecting to your lab
            </h2>
            <p className="mt-1 text-[13px] text-muted">
              Lab machines run on an isolated network. You reach them through
              NetBird, not from the campus Wi-Fi.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="rounded-md p-1 text-muted hover:bg-surface-2 hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>

        <div className="px-5 py-4">
          {access.loading && <p className="text-sm text-muted">Loading…</p>}

          {!access.loading && info && !info.configured && (
            <p className="text-sm text-muted">
              Remote access has not been set up for this deployment yet, so
              this lab is reachable only from inside the lab network. Ask your
              instructor how to get on it.
            </p>
          )}

          {!access.loading && info?.configured && (
            <ol className="space-y-4">
              <Step n={1} title="Install the NetBird client">
                <p>
                  Available for Windows, macOS, Linux, iOS and Android.
                </p>
                {info.docs_url && (
                  <a
                    href={info.docs_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-accent underline underline-offset-2"
                  >
                    Install guide
                  </a>
                )}
              </Step>

              <Step n={2} title="Join this school's network">
                {info.join_command ? (
                  <>
                    <p>
                      Run this once. It signs you in against our own NetBird
                      with the class join key — no account of your own to set
                      up:
                    </p>
                    <CopyCode text={info.join_command} />
                  </>
                ) : (
                  <>
                    <p>Sign in against our own NetBird, not the public service:</p>
                    <Code>netbird up --management-url {info.management_url}</Code>
                    {info.setup_key_url && (
                      <p>
                        Need a setup key?{" "}
                        <a
                          href={info.setup_key_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-accent underline underline-offset-2"
                        >
                          Get one here
                        </a>
                        , then add{" "}
                        <code className="font-mono">--setup-key &lt;key&gt;</code>.
                      </p>
                    )}
                  </>
                )}
              </Step>

              <Step n={3} title="Check you are on the network">
                <p>
                  {info.network_name
                    ? `You should appear as a peer on "${info.network_name}".`
                    : "You should appear as a connected peer."}
                </p>
                <Code>netbird status</Code>
              </Step>

              <Step n={4} title="Open the lab">
                {endpoint ? (
                  <>
                    <p>With NetBird connected, this works from your terminal:</p>
                    <Code>{endpoint}</Code>
                  </>
                ) : (
                  <p>
                    The command appears on this page once provisioning
                    finishes.
                  </p>
                )}
              </Step>
            </ol>
          )}

          {access.error && (
            <p className="text-sm text-danger">
              Could not load connection details ({access.error.message}).
            </p>
          )}
        </div>

        <div className="flex items-center justify-between gap-4 border-t border-border px-5 py-3">
          <p className="text-[12px] text-muted">
            Still stuck? The lab dies at its TTL — relaunching gives a fresh
            address.
          </p>
          <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
            Got it
          </Button>
        </div>
      </dialog>
    </>
  );
}
