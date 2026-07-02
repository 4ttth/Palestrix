"use client";

import dynamic from "next/dynamic";

/*
 * Client wrapper that lazy-loads the Three.js scene so it never blocks
 * LCP and never ships to non-marketing routes. The loading placeholder
 * reserves the exact box to keep CLS at zero.
 */
const HeroModel = dynamic(() => import("@/components/three/HeroModel"), {
  ssr: false,
  loading: () => <div className="size-full" aria-hidden="true" />,
});

export function HeroVisual() {
  return (
    <div className="relative aspect-square w-full max-w-[520px]">
      <HeroModel />
    </div>
  );
}
