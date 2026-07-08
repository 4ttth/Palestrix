"use client";

/*
 * Topbar: search, Palestras balance (amber is reserved for the currency),
 * streak, identity — all live from the session (GET /auth/me +
 * /gamification/summary). All numbers render in mono per the theme lock.
 * Below lg a hamburger opens the navigation drawer (nav-context).
 */

import Link from "next/link";
import { Coins, Flame, List, MagnifyingGlass, SignOut } from "@phosphor-icons/react";
import { Avatar } from "@/components/ui/avatar";
import { useSession } from "@/lib/api/session";
import { useNav } from "./nav-context";

export function Topbar({ title }: { title: string }) {
  const { user, summary, logout } = useSession();
  const { setOpen } = useNav();
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-border bg-background/85 px-4 backdrop-blur-sm sm:px-6">
      <div className="flex min-w-0 items-center gap-2.5">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          className="-ml-1 rounded-(--radius-input) p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground lg:hidden"
        >
          <List size={18} />
        </button>
        <h1 className="truncate text-[15px] font-semibold tracking-tight">{title}</h1>
      </div>
      <div className="flex items-center gap-2.5 sm:gap-4">
        <label className="relative hidden md:block">
          <MagnifyingGlass
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
          />
          <input
            type="search"
            placeholder="Search labs, courses, writeups"
            aria-label="Search"
            className="h-8 w-64 rounded-(--radius-input) border border-border bg-surface pl-8 pr-3 text-[13px] placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
          />
        </label>
        {summary && (
          <div
            className="flex items-center gap-1.5 rounded-full bg-palestras-soft px-3 py-1 text-[13px] font-medium text-palestras"
            title="Palestras balance"
          >
            <Coins size={15} weight="fill" />
            <span className="font-mono tabular-nums">
              {summary.palestras.toLocaleString()}
            </span>
          </div>
        )}
        {summary && (
          <div
            className="hidden items-center gap-1 text-[13px] text-muted sm:flex"
            title={`${summary.streak_days}-day learning streak`}
          >
            <Flame size={15} weight="fill" className="text-palestras" />
            <span className="font-mono tabular-nums">{summary.streak_days}d</span>
          </div>
        )}
        <Link href="/settings" title="Profile settings" aria-label="Profile settings">
          <Avatar handle={user.handle} size="md" />
        </Link>
        <button
          type="button"
          onClick={logout}
          title="Sign out"
          aria-label="Sign out"
          className="rounded-(--radius-input) p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <SignOut size={16} />
        </button>
      </div>
    </header>
  );
}
