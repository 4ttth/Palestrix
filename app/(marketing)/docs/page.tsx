import Link from "next/link";
import { ArrowSquareOut } from "@phosphor-icons/react/dist/ssr";

export const metadata = { title: "Documentation" };

/*
 * Documentation index. The documents live as Markdown in the repository's
 * docs/ folder; this page is the map. Phase 5 can render them in-app.
 */
const docs = [
  {
    file: "architecture.md",
    title: "Architecture",
    body: "System map: services, orchestration abstraction, storage, build order.",
  },
  {
    file: "usecase-a-baremetal.md",
    title: "Use case A: Baremetal",
    body: "Proxmox VE with OpenNebula or CloudStack, ZFS, MinIO, and edge TLS behind your public IP or domain.",
  },
  {
    file: "usecase-b-cloud-aws.md",
    title: "Use case B: Cloud",
    body: "Every service named generically and in AWS terms: EKS, S3, RDS, SQS, Lambda, and the rest.",
  },
  {
    file: "ephemeral-lifecycle.md",
    title: "Ephemeral lifecycle",
    body: "The instance state machine, TTL reaper, and multitenancy invariants.",
  },
  {
    file: "rbac-matrix.md",
    title: "RBAC matrix",
    body: "What Students, Teachers, Administrators, and Superadministrators can do.",
  },
  {
    file: "sandbox-security.md",
    title: "Sandbox security",
    body: "How the malware sandbox stays contained when a sample escapes its container.",
  },
  {
    file: "public-api.md",
    title: "Public API",
    body: "The /api/v1 surface, API keys and OAuth2 scopes, and the webhook catalog.",
  },
  {
    file: "plugin-development.md",
    title: "Plugin development",
    body: "Manifest, lifecycle hooks, UI slots, and capability sandboxing for third-party plugins.",
  },
  {
    file: "integrations-canvas-lms.md",
    title: "Canvas LMS integration",
    body: "The ExternalPlatform adapter layer: roster sync, deep-linked labs, grade passback.",
  },
];

export default function DocsPage() {
  return (
    <div className="mx-auto max-w-[1200px] px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
        Documentation
      </h1>
      <p className="mt-4 max-w-[65ch] text-base leading-relaxed text-muted">
        Everything needed to deploy and extend PalestrIX. Each entry links to
        the Markdown source in the repository's docs folder.
      </p>
      <ul className="mt-10 grid gap-x-10 gap-y-2 md:grid-cols-2">
        {docs.map((d) => (
          <li key={d.file} className="border-b border-border py-5">
            <Link
              href={`https://github.com/palestrix/palestrix/blob/main/docs/${d.file}`}
              className="group flex items-start justify-between gap-4"
            >
              <span>
                <span className="font-medium group-hover:text-accent">
                  {d.title}
                </span>
                <span className="mt-1 block max-w-[52ch] text-sm leading-relaxed text-muted">
                  {d.body}
                </span>
              </span>
              <ArrowSquareOut
                size={16}
                className="mt-1 shrink-0 text-muted group-hover:text-accent"
              />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
