import { Coins, Flame, MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";
import { Avatar } from "@/components/ui/avatar";
import { currentUser } from "@/lib/mock";

/*
 * Topbar: search, Palestras balance (amber is reserved for the currency),
 * streak, identity. All numbers render in mono per the theme lock.
 */
export function Topbar({ title }: { title: string }) {
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
        <div
          className="flex items-center gap-1.5 rounded-full bg-palestras-soft px-3 py-1 text-[13px] font-medium text-palestras"
          title="Palestras balance"
        >
          <Coins size={15} weight="fill" />
          <span className="font-mono tabular-nums">{currentUser.palestras.toLocaleString()}</span>
        </div>
        <div
          className="flex items-center gap-1 text-[13px] text-muted"
          title={`${currentUser.streakDays}-day learning streak`}
        >
          <Flame size={15} weight="fill" className="text-palestras" />
          <span className="font-mono tabular-nums">{currentUser.streakDays}d</span>
        </div>
        <Avatar handle={currentUser.handle} size="md" />
      </div>
    </header>
  );
}
