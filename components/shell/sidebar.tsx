"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import {
  SquaresFour,
  GraduationCap,
  Books,
  Cube,
  Bug,
  UsersThree,
  Flag,
  HardDrives,
  IdentificationCard,
  PuzzlePiece,
  GearSix,
  X,
  type Icon,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import { useNav } from "./nav-context";
import type { InstanceOut } from "@/lib/api/types";

/*
 * Product sidebar, live: the Active lab entry tracks the caller's newest
 * still-alive instance, the Admin group renders only for the roles that hold
 * its capabilities (RBAC, Phase 2), and the footer reports the session's
 * tenant and how many instances the caller is holding. Below lg it becomes
 * a slide-over drawer driven by the Topbar hamburger (nav-context).
 */

type NavItem = { href: string; label: string; icon: Icon };

const ALIVE = new Set(["requested", "provisioning", "running", "stopped"]);

function NavGroup({
  title,
  items,
  pathname,
  onNavigate,
}: {
  title: string;
  items: NavItem[];
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <div>
      <p className="px-3 text-[11px] font-medium text-muted">{title}</p>
      <ul className="mt-1.5 space-y-0.5">
        {items.map((item) => {
          const active = pathname.startsWith(item.href.split("/").slice(0, 3).join("/"));
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  "flex items-center gap-2.5 rounded-(--radius-input) px-3 py-2 text-[13px] transition-colors duration-150",
                  active
                    ? "bg-accent-soft font-medium text-accent"
                    : "text-muted hover:bg-surface-2 hover:text-foreground"
                )}
              >
                <Icon size={17} weight={active ? "fill" : "regular"} />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useSession();
  const { data: instances } = useApi<InstanceOut[]>("/api/v1/instances");

  const alive = (instances ?? []).filter((i) => ALIVE.has(i.state));
  const current = alive[0]; // newest first from the API

  const learn: NavItem[] = [
    { href: "/dashboard", label: "Dashboard", icon: SquaresFour },
    { href: "/academy", label: "Academy", icon: GraduationCap },
    { href: "/courses", label: "Courses", icon: Books },
    ...(current
      ? [{ href: `/labs/${current.id}`, label: "Active lab", icon: Cube }]
      : []),
  ];

  const range: NavItem[] = [
    { href: "/sandbox", label: "Sandbox", icon: Bug },
    { href: "/community", label: "Community", icon: UsersThree },
    { href: "/compete", label: "Compete", icon: Flag },
  ];

  const account: NavItem[] = [
    { href: "/settings", label: "Settings", icon: GearSix },
  ];

  const isAdmin = user.role === "admin" || user.role === "superadmin";
  const admin: NavItem[] = [
    { href: "/admin/infrastructure", label: "Infrastructure", icon: HardDrives },
    { href: "/admin/users", label: "Users", icon: IdentificationCard },
    ...(user.role === "superadmin"
      ? [{ href: "/admin/plugins", label: "Plugins", icon: PuzzlePiece }]
      : []),
  ];

  return (
    <>
      <nav className="flex-1 space-y-6 overflow-y-auto px-2.5 py-5">
        <NavGroup title="Learn" items={learn} pathname={pathname} onNavigate={onNavigate} />
        <NavGroup title="Range" items={range} pathname={pathname} onNavigate={onNavigate} />
        {isAdmin && (
          <NavGroup title="Admin" items={admin} pathname={pathname} onNavigate={onNavigate} />
        )}
        <NavGroup title="Account" items={account} pathname={pathname} onNavigate={onNavigate} />
      </nav>
      <div className="border-t border-border px-5 py-4 text-[11px] leading-relaxed text-muted">
        Tenant{" "}
        <span className="font-mono text-foreground">
          {user.tenant_id ?? "unassigned"}
        </span>
        <br />
        Holding{" "}
        <span className="font-mono text-foreground">{alive.length}</span>{" "}
        instance{alive.length === 1 ? "" : "s"}
      </div>
    </>
  );
}

function Wordmark() {
  return (
    <Link href="/dashboard" className="text-[15px] font-semibold tracking-tight">
      Palestr<span className="text-accent">IX</span>
    </Link>
  );
}

export function Sidebar() {
  const { open, setOpen } = useNav();

  // The drawer must never survive into desktop widths or leave scroll locked.
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  return (
    <>
      {/* Desktop rail */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 flex-col border-r border-border bg-surface lg:flex">
        <div className="flex h-14 items-center border-b border-border px-5">
          <Wordmark />
        </div>
        <SidebarContent />
      </aside>

      {/* Mobile slide-over */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
          />
          <aside className="absolute inset-y-0 left-0 flex w-64 max-w-[85vw] flex-col border-r border-border bg-surface shadow-xl">
            <div className="flex h-14 items-center justify-between border-b border-border px-5">
              <Wordmark />
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="rounded-(--radius-input) p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
              >
                <X size={16} />
              </button>
            </div>
            <SidebarContent onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
    </>
  );
}
