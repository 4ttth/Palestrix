# PalestrIX — product film

A 60-second motion piece for the platform, 1920×1080 at 60 fps with a
synthesized score. It uses the locked product design system: Geist and Geist
Mono, the calm electric-blue accent, amber only for Palestras, the pastel
lifecycle states, and the `swift` / `spring` easings from
`components/theme/`.

| Time | Chapter | What it shows |
| --- | --- | --- |
| 0:00 | Cold open | "Real machines, not slides." |
| 0:04 | Wordmark | PalestrIX, "the cyber range with a classroom brain" |
| 0:08 | Ephemeral labs | A lab goes Requested → Provisioning → Running with a live log, then its TTL runs out and the reaper destroys it and releases the quota. Lifecycle rail underneath. |
| 0:19 | Palestras | Ledger awards (module, flag, first blood, streak) count the balance up |
| 0:26 | Arena | CTF board solves, a first-blood tile, leaderboard reordering |
| 0:34 | Malware sandbox | Detonation timeline with ATT&CK techniques, then the verdict |
| 0:41 | Multitenancy | Per-class VLAN tenants; a packet is refused at a tenant wall; the four roles |
| 0:47 | Academy | The four shipped paths with their real module counts and hours |
| 0:52 | Open source | The stack |
| 0:56 | End card | Wordmark and tagline |

## Files

- `palestrix-film.mp4` is the rendered film: 1080p60 H.264 at about 7 Mb/s,
  with AAC audio at −16 LUFS (55 MB). `poster.jpg` is its end card. The
  CRF-16 master from `render.mjs` is about 320 MB, because the per-frame film
  grain barely compresses. The committed file is a two-step delivery encode
  of that master (see Rebuild).

- `index.html` is the whole film. Each frame is a pure function of time
  (`renderAt(t)`), so the page plays live in a browser and renders
  frame-exact. Open it directly: **space** pauses, **← →** scrub two seconds,
  **R** restarts, and `?t=26` starts at a given second.
- `render.mjs` steps through the page with Playwright's Chromium and pipes
  PNG frames to ffmpeg (H.264, CRF 16). It muxes `soundtrack.wav` in when that
  file exists, loudness-normalized to −16 LUFS.
- `soundtrack.py` synthesizes `soundtrack.wav` with numpy. Its cues are
  pinned to the same timestamps as `index.html`, so if you move a cue in one
  file, move it in the other too.
- `fonts/` holds Geist and Geist Mono (SIL Open Font License), taken from the
  `geist` package the app already depends on.

## Rebuild

```bash
cd media/film
pip install numpy imageio-ffmpeg            # imageio-ffmpeg ships ffmpeg with libx264
python soundtrack.py                         # → soundtrack.wav
FFMPEG=$(python -c "import imageio_ffmpeg as f; print(f.get_ffmpeg_exe())") \
  node render.mjs                            # → palestrix-film.mp4, ~25 min
# delivery encode (what is committed)
$FFMPEG -i palestrix-film.mp4 -c:v libx264 -preset slow -b:v 7M -maxrate 10M \
  -bufsize 20M -tune film -pix_fmt yuv420p -c:a copy -movflags +faststart out.mp4
node render.mjs --stills 5.4,17.9,29.5       # review frames → stills/
node render.mjs --fps 30 --from 26 --to 34   # quick partial pass
```

The data on screen, such as the provisioning log, the academy paths, the
roles, and the tenancy and quota rules, is taken from the product and its
docs (`lib/mock.ts`, `academy_catalog.py`, `docs/rbac-matrix.md`). Team names,
scores, the sample hash and the sandbox events are illustrative.
