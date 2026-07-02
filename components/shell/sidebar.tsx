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
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { activeInstance } from "@/lib/mock";

/*
 * Product sidebar. Role-gating note: the Admin group renders only for
 * Administrator / Superadministrator once RBAC lands in Phase 2; the
 * template shows the superadmin view so every screen is reachable.
 */
const learn = [
  { href: "/dashboard", label: "Dashboard", icon: SquaresFour },
  { href: "/academy", label: "Academy", icon: GraduationCap },
  { href: "/courses", label: "Courses", icon: Books },
  { href: `/labs/${activeInstance.id}`, label: "Active lab", icon: Cube },
];

const range = [
  { href: "/sandbox", label: "Sandbox", icon: Bug },
  { href: "/community", label: "Community", icon: UsersThree },
  { href: "/compete", label: "Compete", icon: Flag },
];

const admin = [
  { href: "/admin/infrastructure", label: "Infrastructure", icon: HardDrives },
];

function NavGroup({
  title,
  items,
  pathname,
}: {
  title: string;
  items: typeof learn;
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
        <NavGroup title="Admin" items={admin} pathname={pathname} />
      </nav>
      <div className="border-t border-border px-5 py-4 text-[11px] leading-relaxed text-muted">
        Tenant <span className="font-mono text-foreground">hau-bscs-3a</span>
        <br />
        Quota <span className="font-mono text-foreground">2/3</span> instances
      </div>
    </aside>
  );
}
