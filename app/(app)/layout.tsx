import { Sidebar } from "@/components/shell/sidebar";
import { SessionProvider } from "@/lib/api/session";

/*
 * Product shell: dense surfaces (VARIANCE 4 / MOTION 2 / DENSITY 7-8).
 * These screens are deliberately outside the taste-skill scope (Section 13)
 * and use the customized shadcn-style primitives on the same locked theme.
 *
 * SessionProvider guards the whole group: it resolves the bearer token to a
 * user (GET /auth/me) and bounces to /login when the session is absent or
 * stale, so every page below can assume a signed-in viewer.
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SessionProvider>
      <div className="min-h-[100dvh]">
        <Sidebar />
        <div className="lg:pl-56">{children}</div>
      </div>
    </SessionProvider>
  );
}
