import Image from "next/image";
import Link from "next/link";

/*
 * Auth gateway: split screen. Form left, photographic panel right
 * (picsum seed palestrix-server-racks; swap for a real photo of the
 * on-campus rack before launch). Same locked theme as every surface.
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
      <div className="relative hidden lg:block">
        <Image
          src="https://picsum.photos/seed/palestrix-server-racks/1200/1600"
          alt="Server racks in the campus datacenter"
          fill
          sizes="50vw"
          priority
          className="object-cover"
        />
        <div className="absolute inset-0 bg-[#0d0d10]/72" />
        <div className="absolute inset-x-0 bottom-0 p-12">
          <p className="max-w-[36ch] text-2xl font-semibold leading-snug tracking-tight text-[#ebebf0]">
            The range is real hardware. Your session is a passkey away.
          </p>
        </div>
      </div>
    </div>
  );
}
