// Renders index.html to video, one deterministic frame at a time.
//
//   node render.mjs                     → palestrix-film.mp4 (1080p60, H.264)
//   node render.mjs --stills 3,12.5,40  → stills/t-<sec>.png for review
//   node render.mjs --fps 30 --from 8 --to 19   → a partial, lower-rate pass
//
// Needs Playwright's Chromium and an ffmpeg with libx264 on PATH, or pointed
// to by FFMPEG (e.g. the static build from `pip install imageio-ffmpeg`).
// If soundtrack.wav sits next to this file it is muxed in as AAC.

import { spawn } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require("playwright")); }
catch { ({ chromium } = require("/opt/node22/lib/node_modules/playwright")); }

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (name, fallback) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : fallback; };

const FFMPEG = process.env.FFMPEG || "ffmpeg";
const fps = Number(opt("fps", 60));
const stills = opt("stills", null);
const out = opt("out", join(here, "palestrix-film.mp4"));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(join(here, "index.html")).href + "?render");
await page.evaluate(() => document.fonts.ready);
const { DURATION } = await page.evaluate(() => window.FILM);
const from = Number(opt("from", 0)), to = Number(opt("to", DURATION));

async function frame(t) {
  await page.evaluate((tt) => window.renderAt(tt), t);
  return page.screenshot({ type: "png", clip: { x: 0, y: 0, width: 1920, height: 1080 } });
}

if (stills) {
  mkdirSync(join(here, "stills"), { recursive: true });
  for (const s of stills.split(",").map(Number)) {
    const buf = await frame(s);
    const { writeFileSync } = await import("node:fs");
    writeFileSync(join(here, "stills", `t-${s.toFixed(2)}.png`), buf);
    console.log("still", s);
  }
  await browser.close();
  process.exit(0);
}

const audio = join(here, "soundtrack.wav");
const withAudio = existsSync(audio) && from === 0 && !args.includes("--no-audio");
const ff = spawn(FFMPEG, [
  "-y", "-loglevel", "error",
  "-f", "image2pipe", "-framerate", String(fps), "-c:v", "png", "-i", "-",
  ...(withAudio ? ["-ss", String(from), "-i", audio] : []),
  "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "film",
  "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart",
  ...(withAudio ? ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "256k", "-shortest"] : []),
  out,
], { stdio: ["pipe", "inherit", "inherit"] });

const total = Math.round((to - from) * fps);
const started = Date.now();
for (let i = 0; i < total; i++) {
  const buf = await frame(from + i / fps);
  if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
  if (i % fps === 0) {
    const el = (Date.now() - started) / 1000;
    process.stdout.write(`\r${i}/${total} frames · ${(i / Math.max(el, 0.001)).toFixed(1)} fps render`);
  }
}
ff.stdin.end();
await new Promise((r, j) => ff.on("close", (c) => (c === 0 ? r() : j(new Error(`ffmpeg exited ${c}`)))));
await browser.close();
console.log(`\nwrote ${out}`);
