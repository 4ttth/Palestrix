"use client";

/*
 * Isolated Three.js leaf for the landing hero. Loaded via next/dynamic
 * (ssr: false) from components/marketing/hero-visual.tsx so the bundle
 * stays out of every other route.
 *
 * The scene is a wireframe icosahedron network: a quiet nod to lab
 * topologies without neon or fake dashboards. Rotation is slow and
 * disabled entirely under prefers-reduced-motion (a single static frame
 * is rendered instead).
 */

import { useEffect, useRef } from "react";
import * as THREE from "three";

function cssColor(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export default function HeroModel() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 6.2);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const accent = new THREE.Color(cssColor("--accent", "#2f6fe0"));
    const dim = new THREE.Color(cssColor("--muted", "#63636e"));

    const group = new THREE.Group();

    const icoGeo = new THREE.IcosahedronGeometry(2.05, 1);
    const wire = new THREE.LineSegments(
      new THREE.WireframeGeometry(icoGeo),
      new THREE.LineBasicMaterial({ color: dim, transparent: true, opacity: 0.5 })
    );
    group.add(wire);

    const innerGeo = new THREE.IcosahedronGeometry(1.15, 0);
    const inner = new THREE.LineSegments(
      new THREE.WireframeGeometry(innerGeo),
      new THREE.LineBasicMaterial({ color: accent, transparent: true, opacity: 0.9 })
    );
    group.add(inner);

    const nodePositions = icoGeo.attributes.position;
    const pointsGeo = new THREE.BufferGeometry();
    pointsGeo.setAttribute("position", nodePositions.clone());
    const points = new THREE.Points(
      pointsGeo,
      new THREE.PointsMaterial({ color: accent, size: 0.055, sizeAttenuation: true })
    );
    group.add(points);

    group.rotation.set(0.42, -0.35, 0.08);
    scene.add(group);

    const resize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    let raf = 0;
    const clock = new THREE.Clock();

    if (reduce) {
      renderer.render(scene, camera);
    } else {
      const tick = () => {
        const t = clock.getElapsedTime();
        group.rotation.y = -0.35 + t * 0.12;
        group.rotation.x = 0.42 + Math.sin(t * 0.4) * 0.05;
        inner.rotation.y = -t * 0.2;
        renderer.render(scene, camera);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      icoGeo.dispose();
      innerGeo.dispose();
      pointsGeo.dispose();
      wire.geometry.dispose();
      inner.geometry.dispose();
      (wire.material as THREE.Material).dispose();
      (inner.material as THREE.Material).dispose();
      (points.material as THREE.Material).dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={mountRef} className="size-full" aria-hidden="true" />;
}
