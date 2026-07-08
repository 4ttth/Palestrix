import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Coins,
  FlagCheckered,
  GraduationCap,
  ShieldCheck,
  Timer,
  UsersThree,
} from "@phosphor-icons/react/dist/ssr";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { HeroVisual } from "@/components/marketing/hero-visual";
import { Reveal } from "@/components/marketing/reveal";
import { ProvisioningLog } from "@/components/lab/ProvisioningLog";
import { provisioningSample } from "@/lib/mock";

/*
 * Landing page. Dials: VARIANCE 6 / MOTION 4 (hero spikes higher via the
 * 3D scene) / DENSITY 3. One locked theme, calm electric blue accent.
 *
 * Image plan (per section, no cropped reuse):
 *  - Hero: live Three.js wireframe topology (components/three/HeroModel.tsx)
 *  - Built-on wall: real SVG marks from Simple Icons CDN
 *  - Bento "sandbox" cell: picsum seed palestrix-sandbox-tracewall (4:3)
 *  - Academy split: picsum seed palestrix-academy-terminal (4:3)
 *  - Compete band: picsum seed palestrix-ctf-arena-dark (12:5, full-bleed)
 * Swap picsum seeds for real photography of the HAU lab before launch.
 */

const stack = [
  { slug: "proxmox", name: "Proxmox VE" },
  { slug: "docker", name: "Docker" },
  { slug: "kubernetes", name: "Kubernetes" },
  { slug: "postgresql", name: "PostgreSQL" },
  { slug: "redis", name: "Redis" },
  { slug: "fastapi", name: "FastAPI" },
  { slug: "minio", name: "MinIO" },
  { slug: "nextdotjs", name: "Next.js" },
];

const lifecycle = [
  {
    verb: "Request",
    body: "A student opens a lab. The job enters the tenant queue with quota checks.",
  },
  {
    verb: "Provision",
    body: "Proxmox clones the VM or Docker builds the container. Every log line streams to the browser.",
  },
  {
    verb: "Expose",
    body: "GUI labs attach a noVNC console. Headless labs publish an IP and port.",
  },
  {
    verb: "Count down",
    body: "The TTL clock runs where the student can see it. Extensions cost Palestras.",
  },
  {
    verb: "Reap",
    body: "At zero, the reaper stops the instance, destroys it, and releases the quota.",
  },
];

const pathsPreview = [
  { title: "SOC Analyst", detail: "14 modules" },
  { title: "Web Exploitation", detail: "12 modules" },
  { title: "Network Defense", detail: "10 modules" },
  { title: "Digital Forensics", detail: "11 modules" },
];

export default function LandingPage() {
  return (
    <>
      {/* HERO: asymmetric split, copy left, live 3D topology right */}
      <section className="mx-auto grid max-w-[1200px] items-center gap-10 px-6 pt-14 pb-16 md:pt-20 lg:grid-cols-[1.05fr_0.95fr] lg:gap-6">
        <Reveal>
          <h1 className="max-w-[16ch] text-4xl font-semibold tracking-tighter md:text-5xl lg:text-6xl">
            Real machines, not slides.
          </h1>
          <p className="mt-5 max-w-[44ch] text-lg leading-relaxed text-muted">
            PalestrIX gives every student an ephemeral lab, a CTF arena, and a
            path to mastery, built on open source.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href="/register">
              <Button size="lg">Create your account</Button>
            </Link>
            <Link href="#labs">
              <Button variant="secondary" size="lg">
                See how labs work
              </Button>
            </Link>
          </div>
        </Reveal>
        <div className="flex justify-center lg:justify-end">
          <HeroVisual />
        </div>
      </section>

      {/* BUILT ON: real open-source marks, logos only */}
      <section className="border-y border-border bg-surface">
        <div className="mx-auto max-w-[1200px] px-6 py-10">
          <p className="text-[13px] text-muted">Built entirely on open source</p>
          <div className="mt-6 grid grid-cols-4 items-center gap-x-8 gap-y-7 md:grid-cols-8">
            {stack.map((s) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={s.slug}
                src={`https://cdn.simpleicons.org/${s.slug}/71717a`}
                alt={s.name}
                width={30}
                height={30}
                loading="lazy"
                className="h-7 w-auto opacity-80"
              />
            ))}
          </div>
        </div>
      </section>

      {/* FEATURES: bento, 5 cells for 5 features, varied backgrounds */}
      <section id="labs" className="mx-auto max-w-[1200px] px-6 py-24">
        <Reveal>
          <h2 className="max-w-[24ch] text-3xl font-semibold tracking-tight md:text-4xl">
            A cyber range with a classroom brain.
          </h2>
          <p className="mt-4 max-w-[52ch] text-base leading-relaxed text-muted">
            Labs are disposable, roles are enforced, and every action runs
            through the same public API your plugins use.
          </p>
        </Reveal>
        <div className="mt-12 grid gap-4 md:grid-cols-6">
          {/* Cell 1: ephemeral labs with a REAL component preview (mock replay) */}
          <Reveal className="md:col-span-4">
            <div className="h-full rounded-(--radius-card) border border-border bg-surface p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="font-semibold tracking-tight">Ephemeral labs</h3>
                  <p className="mt-1 max-w-[46ch] text-sm leading-relaxed text-muted">
                    Real Proxmox VMs and Docker containers, born on request and
                    reaped on schedule. This is the live provisioning stream.
                  </p>
                </div>
                <Badge variant="running">Running</Badge>
              </div>
              <ProvisioningLog lines={provisioningSample} className="mt-5" />
            </div>
          </Reveal>

          {/* Cell 2: Palestras, amber-tinted */}
          <Reveal delay={0.05} className="md:col-span-2">
            <div className="h-full rounded-(--radius-card) border border-border bg-palestras-soft p-6">
              <Coins size={26} weight="fill" className="text-palestras" />
              <h3 className="mt-4 font-semibold tracking-tight">Palestras</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">
                One currency across learning and competition. Earn it by
                finishing modules and capturing flags. Spend it on hints and
                lab extensions.
              </p>
            </div>
          </Reveal>

          {/* Cell 3: sandbox, photographic background with scrim */}
          <Reveal className="md:col-span-2">
            <div className="relative h-full min-h-[240px] overflow-hidden rounded-(--radius-card) border border-border">
              <Image
                src="https://picsum.photos/seed/palestrix-sandbox-tracewall/800/600"
                alt="Analyst workstation with traced malware activity"
                fill
                sizes="(min-width: 768px) 33vw, 100vw"
                className="object-cover"
              />
              <div className="absolute inset-0 bg-[#0d0d10]/78" />
              <div className="relative flex h-full flex-col justify-end p-6">
                <h3 className="font-semibold tracking-tight text-[#ebebf0]">
                  Malware sandbox
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-[#b9b9c3]">
                  Detonate samples in an isolated module and watch file and
                  network activity as it happens.
                </p>
              </div>
            </div>
          </Reveal>

          {/* Cell 4: roles */}
          <Reveal delay={0.05} className="md:col-span-2">
            <div className="h-full rounded-(--radius-card) border border-border bg-surface p-6">
              <UsersThree size={26} className="text-accent" />
              <h3 className="mt-4 font-semibold tracking-tight">Four roles, hard walls</h3>
              <ul className="mt-3 space-y-2 text-sm text-muted">
                <li>Students learn and compete</li>
                <li>Teachers publish courses and labs</li>
                <li>Administrators run the range</li>
                <li>Superadministrators own the platform</li>
              </ul>
            </div>
          </Reveal>

          {/* Cell 5: public API */}
          <Reveal delay={0.1} className="md:col-span-2">
            <div className="h-full rounded-(--radius-card) border border-border bg-accent-soft p-6">
              <h3 className="font-semibold tracking-tight">An API before a UI</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">
                Every function ships as a versioned REST endpoint with webhooks,
                so plugins and external tools use the same contract.
              </p>
              <code className="mt-4 block rounded-(--radius-input) bg-surface px-3 py-2 font-mono text-xs text-accent">
                GET /api/v1/instances/lab-3427
              </code>
            </div>
          </Reveal>
        </div>
      </section>

      {/* LIFECYCLE: horizontal five-stage flow, semantic state chips */}
      <section className="border-y border-border bg-surface">
        <div className="mx-auto max-w-[1200px] px-6 py-24">
          <Reveal>
            <h2 className="max-w-[22ch] text-3xl font-semibold tracking-tight md:text-4xl">
              Every lab is born to expire.
            </h2>
            <p className="mt-4 max-w-[52ch] text-base leading-relaxed text-muted">
              Nothing idles. The lifecycle below is enforced by a reaper worker,
              so a class of forty never exhausts two servers.
            </p>
          </Reveal>
          <div className="mt-12 grid gap-8 md:grid-cols-5 md:gap-5">
            {lifecycle.map((stage, i) => (
              <Reveal key={stage.verb} delay={i * 0.05}>
                <div className="border-t-2 border-accent/60 pt-4">
                  <h3 className="font-mono text-sm font-semibold tracking-tight">
                    {stage.verb}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    {stage.body}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
          <div className="mt-10 flex flex-wrap items-center gap-2.5">
            <Badge variant="provisioning">Provisioning</Badge>
            <Badge variant="running">Running</Badge>
            <Badge variant="stopped">Stopped</Badge>
            <Badge variant="expired">Expired</Badge>
            <span className="text-[13px] text-muted">
              The four states every instance reports, in the UI and the API.
            </span>
          </div>
        </div>
      </section>

      {/* ACADEMY: split, photography left, structured paths right */}
      <section id="academy" className="mx-auto max-w-[1200px] px-6 py-24">
        <div className="grid items-center gap-10 lg:grid-cols-2">
          <Reveal>
            <div className="relative aspect-[4/3] overflow-hidden rounded-(--radius-card) border border-border">
              <Image
                src="https://picsum.photos/seed/palestrix-academy-terminal/1200/900"
                alt="Students working through terminal exercises in a lab room"
                fill
                sizes="(min-width: 1024px) 50vw, 100vw"
                className="object-cover"
              />
            </div>
          </Reveal>
          <Reveal delay={0.08}>
            <h2 className="max-w-[20ch] text-3xl font-semibold tracking-tight md:text-4xl">
              Paths that end in proof.
            </h2>
            <p className="mt-4 max-w-[48ch] text-base leading-relaxed text-muted">
              Roadmaps, modules, and walkthroughs build toward certification
              states a teacher can grade and an employer can check.
            </p>
            <ul className="mt-8 space-y-3">
              {pathsPreview.map((p) => (
                <li
                  key={p.title}
                  className="flex items-center justify-between border-b border-border pb-3 text-sm last:border-b-0"
                >
                  <span className="flex items-center gap-2.5 font-medium">
                    <GraduationCap size={17} className="text-accent" />
                    {p.title}
                  </span>
                  <span className="font-mono text-xs text-muted">{p.detail}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </section>

      {/* COMPETE: full-bleed photographic band */}
      <section id="compete" className="relative overflow-hidden">
        <Image
          src="https://picsum.photos/seed/palestrix-ctf-arena-dark/1920/800"
          alt="Competition floor lit by rows of screens"
          fill
          sizes="100vw"
          className="object-cover"
        />
        <div className="absolute inset-0 bg-[#0d0d10]/82" />
        <div className="relative mx-auto max-w-[1200px] px-6 py-28">
          <Reveal>
            <FlagCheckered size={28} className="text-[#dfaf54]" weight="fill" />
            <h2 className="mt-5 max-w-[22ch] text-3xl font-semibold tracking-tight text-[#ebebf0] md:text-4xl">
              First blood goes to the fast.
            </h2>
            <p className="mt-4 max-w-[48ch] text-base leading-relaxed text-[#b9b9c3]">
              Timed events, live leaderboards, and flags worth Palestras. The
              arena runs on the same ephemeral infrastructure as class.
            </p>
            <Link href="/compete" className="mt-8 inline-block">
              <Button variant="secondary" size="lg" className="border-transparent">
                Explore the CTF arena
                <ArrowRight size={16} />
              </Button>
            </Link>
          </Reveal>
        </div>
      </section>

      {/* FACULTY: asymmetric narrative + deploy facts */}
      <section className="mx-auto max-w-[1200px] px-6 py-24">
        <div className="grid gap-12 lg:grid-cols-[1.2fr_0.8fr]">
          <Reveal>
            <h2 className="max-w-[24ch] text-3xl font-semibold tracking-tight md:text-4xl">
              Faculty publish labs, not tickets.
            </h2>
            <p className="mt-4 max-w-[56ch] text-base leading-relaxed text-muted">
              Upload a quiz file and you are done. Flip one toggle and the same
              form takes a Dockerfile or a Proxmox VM template, a GUI choice,
              a TTL, and tenant isolation. No requests to IT, no shared
              machines, no cleanup duty.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-1.5 text-sm text-muted">
                <Timer size={15} className="text-accent" /> TTL on every instance
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-1.5 text-sm text-muted">
                <ShieldCheck size={15} className="text-accent" /> Per-class network isolation
              </span>
            </div>
          </Reveal>
          <Reveal delay={0.08}>
            <div className="rounded-(--radius-card) border border-border bg-surface p-6">
              <h3 className="font-semibold tracking-tight">Deploy it your way</h3>
              <dl className="mt-4 space-y-4 text-sm">
                <div>
                  <dt className="font-medium">Your own metal</dt>
                  <dd className="mt-1 leading-relaxed text-muted">
                    One Proxmox VE workstation runs the platform and the labs,
                    published under your public IP or domain.
                  </dd>
                </div>
                <div>
                  <dt className="font-medium">Your cloud account</dt>
                  <dd className="mt-1 leading-relaxed text-muted">
                    Kubernetes namespaces on EKS, S3 storage, RDS Postgres.
                    Every service named generically and in AWS terms.
                  </dd>
                </div>
              </dl>
              <Link
                href="/docs"
                className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline"
              >
                Read both runbooks
                <ArrowRight size={15} />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      {/* FINAL CTA: accent color block */}
      <section className="border-t border-border bg-accent-soft">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-6 px-6 py-20">
          <Reveal>
            <h2 className="max-w-[24ch] text-3xl font-semibold tracking-tight md:text-4xl">
              Put your students on real terrain.
            </h2>
          </Reveal>
          <Link href="/register">
            <Button size="lg">Create your account</Button>
          </Link>
        </div>
      </section>
    </>
  );
}
