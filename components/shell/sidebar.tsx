"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  SquaresFour,
  GraduationCap,
  Books,
  Cube,
  Bug,
  UsersThree,
  Flag,
  HardDrives,
  type Icon,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { useApi } from "@/lib/api/hooks";
import { useSession } from "@/lib/api/session";
import type { InstanceOut } from "@/lib/api/types";

/*
 * Product sidebar, live: the Active lab entry tracks the caller's newest
 * still-alive instance, the Admin group renders only for Administrator /
 * Superadministrator (RBAC, Phase 2), and the footer reports the session's
 * tenant and how many instances the caller is holding.
 */

type NavItem = { href: string; label: string; icon: Icon };

const ALIVE = new Set(["requested", "provisioning", "running", "stopped"]);

function NavGroup({
  title,
  items,
  pathname,
}: {
  title: string;
  items: NavItem[];
  pathname: string;
}) {
  return (
    <div>
      <p className="px-3 text-[11px] font-medium text-muted">{title}</p>
      <ul className="mt-1.5 space-y-0.5">
        {items.map((item) => {
          const active = pathname.startsWith(item.href.split("/").slice(0, 2).join("/"));
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
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

export function Sidebar() {
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

  const admin: NavItem[] = [
    { href: "/admin/infrastructure", label: "Infrastructure", icon: HardDrives },
  ];

  const isAdmin = user.role === "admin" || user.role === "superadmin";

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 flex-col border-r border-border bg-surface lg:flex">
      <div className="flex h-14 items-center border-b border-border px-5">
        <Link href="/dashboard" className="text-[15px] font-semibold tracking-tight">
          Palestr<span className="text-accent">IX</span>
        </Link>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-2.5 py-5">
        <NavGroup title="Learn" items={learn} pathname={pathname} />
        <NavGroup title="Range" items={range} pathname={pathname} />
        {isAdmin && <NavGroup title="Admin" items={admin} pathname={pathname} />}
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
    </aside>
  );
}
