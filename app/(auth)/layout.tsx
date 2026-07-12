import Link from "next/link";

/*
 * Auth gateway: split screen. Form left, decorative panel right. The panel is
 * fully self-contained (CSS gradients + a grid motif, no external image host)
 * so the login/register path has zero third-party runtime dependencies — this
 * platform is meant to run self-hosted, sometimes on isolated networks, where
 * an external CDN for a login backdrop would just be a way to break sign-in.
 * Same locked theme as every surface.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-[100dvh] lg:grid-cols-[1fr_1fr]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <Link href="/" className="text-[17px] font-semibold tracking-tight">
          Palestr<span className="text-accent">IX</span>
        </Link>
        <div className="flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-sm">{children}</div>
        </div>
        <p className="text-[13px] text-muted">
          Accounts are provisioned for enrolled students and faculty.
        </p>
      </div>
      <div
        className="relative hidden overflow-hidden bg-[#0d0d10] lg:block"
        aria-hidden
      >
        {/* Depth: two accent-tinted radial glows over near-black. */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 50% at 78% 18%, oklch(0.55 0.13 255 / 0.35), transparent 70%), " +
              "radial-gradient(55% 45% at 12% 88%, oklch(0.5 0.12 265 / 0.28), transparent 70%)",
          }}
        />
        {/* A faint engineering grid — the "range is real hardware" motif. */}
        <div
          className="absolute inset-0 opacity-[0.16]"
          style={{
            backgroundImage:
              "linear-gradient(oklch(0.8 0.02 255 / 0.6) 1px, transparent 1px), " +
              "linear-gradient(90deg, oklch(0.8 0.02 255 / 0.6) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
            maskImage:
              "radial-gradient(70% 70% at 50% 40%, black, transparent 100%)",
          }}
        />
        <div className="absolute inset-x-0 bottom-0 p-12">
          <p className="max-w-[36ch] text-2xl font-semibold leading-snug tracking-tight text-[#ebebf0]">
            The range is real hardware. Your session is a passkey away.
          </p>
        </div>
      </div>
    </div>
  );
}
