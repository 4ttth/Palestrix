import { MarketingNav } from "@/components/marketing/nav";
import { MarketingFooter } from "@/components/marketing/footer";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-[100dvh]">
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  );
}
