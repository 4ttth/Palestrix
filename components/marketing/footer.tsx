import Link from "next/link";
import { BrandLockup } from "@/components/brand/logo";

export function MarketingFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-14 md:grid-cols-[2fr_1fr_1fr_1fr]">
        <div>
          <BrandLockup textSize={17} />
          <p className="mt-3 max-w-[38ch] text-sm leading-relaxed text-muted">
            A cyber range for classrooms, built entirely on open-source
            infrastructure. Run it on your own metal or in your cloud account.
          </p>
        </div>
        <div className="text-sm">
          <p className="font-medium">Platform</p>
          <ul className="mt-3 space-y-2 text-muted">
            <li><Link href="/academy" className="hover:text-foreground">Academy</Link></li>
            <li><Link href="/compete" className="hover:text-foreground">CTF arena</Link></li>
            <li><Link href="/sandbox" className="hover:text-foreground">Malware sandbox</Link></li>
            <li><Link href="/community" className="hover:text-foreground">Community</Link></li>
          </ul>
        </div>
        <div className="text-sm">
          <p className="font-medium">Deploy</p>
          <ul className="mt-3 space-y-2 text-muted">
            <li><Link href="/docs" className="hover:text-foreground">Architecture</Link></li>
            <li><Link href="/docs" className="hover:text-foreground">Baremetal runbook</Link></li>
            <li><Link href="/docs" className="hover:text-foreground">Cloud runbook</Link></li>
            <li><Link href="/docs" className="hover:text-foreground">Public API</Link></li>
          </ul>
        </div>
        <div className="text-sm">
          <p className="font-medium">Project</p>
          <ul className="mt-3 space-y-2 text-muted">
            <li><Link href="/docs" className="hover:text-foreground">Plugin development</Link></li>
            <li><Link href="/docs" className="hover:text-foreground">Security model</Link></li>
            <li><Link href="/docs" className="hover:text-foreground">Canvas LMS integration</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-border">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-6 py-5 text-[13px] text-muted">
          <p>PalestrIX, a capstone platform. Built on open source.</p>
          <p>2026</p>
        </div>
      </div>
    </footer>
  );
}
