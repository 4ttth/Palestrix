import Link from "next/link";
import { Button } from "@/components/ui/button";

/*
 * Marketing navigation: single line, 64px, four links + auth actions.
 * The signup intent uses ONE label page-wide: "Create your account".
 */
export function MarketingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-6">
        <Link href="/" className="text-[17px] font-semibold tracking-tight">
          Palestr<span className="text-accent">IX</span>
        </Link>
        <nav className="hidden items-center gap-7 text-sm text-muted md:flex">
          <Link href="#labs" className="transition-colors hover:text-foreground">
            Labs
          </Link>
          <Link href="#academy" className="transition-colors hover:text-foreground">
            Academy
          </Link>
          <Link href="#compete" className="transition-colors hover:text-foreground">
            Compete
          </Link>
          <Link href="/docs" className="transition-colors hover:text-foreground">
            Docs
          </Link>
        </nav>
        <div className="flex items-center gap-2.5">
          <Link href="/login">
            <Button variant="ghost" size="sm">
              Sign in
            </Button>
          </Link>
          <Link href="/register" className="hidden sm:block">
            <Button size="sm">Create your account</Button>
          </Link>
        </div>
      </div>
    </header>
  );
}
