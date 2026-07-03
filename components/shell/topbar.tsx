"use client";

/*
 * Topbar: search, Palestras balance (amber is reserved for the currency),
 * streak, identity — all live from the session (GET /auth/me +
 * /gamification/summary). All numbers render in mono per the theme lock.
 */

import { Coins, Flame, MagnifyingGlass, SignOut } from "@phosphor-icons/react";
import { Avatar } from "@/components/ui/avatar";
import { useSession } from "@/lib/api/session";

export function Topbar({ title }: { title: string }) {
  const { user, summary, logout } = useSession();
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-border bg-background/85 px-6 backdrop-blur-sm">
      <h1 className="text-[15px] font-semibold tracking-tight">{title}</h1>
      <div className="flex items-center gap-4">
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
            className="flex items-center gap-1 text-[13px] text-muted"
            title={`${summary.streak_days}-day learning streak`}
          >
            <Flame size={15} weight="fill" className="text-palestras" />
            <span className="font-mono tabular-nums">{summary.streak_days}d</span>
          </div>
        )}
        <Avatar handle={user.handle} size="md" />
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
