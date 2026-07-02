import { Sidebar } from "@/components/shell/sidebar";

/*
 * Product shell: dense surfaces (VARIANCE 4 / MOTION 2 / DENSITY 7-8).
 * These screens are deliberately outside the taste-skill scope (Section 13)
 * and use the customized shadcn-style primitives on the same locked theme.
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-[100dvh]">
      <Sidebar />
      <div className="lg:pl-56">{children}</div>
    </div>
  );
}
