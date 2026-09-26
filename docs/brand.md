# PalestrIX brand standards

The rules for the PalestrIX mark, name, colour, type and imagery. The
palette and type here are the ones already locked in
[`components/theme/tokens.css`](../components/theme/tokens.css). This document
names them, gives them jobs and print values, and adds the mark. Where the two
disagree, `tokens.css` wins for the product UI.

Assets: [`public/brand/`](../public/brand/) · favicon: [`app/icon.svg`](../app/icon.svg)
· React: [`components/brand/logo.tsx`](../components/brand/logo.tsx)
(`BrandMark`, `BrandLockup`).

---

## 1. The mark: "The Keystone"

A palaestra, the walled courtyard where Greek athletes trained before the games,
seen from above. A heavy square wall encloses an open courtyard. Its top-right
corner is lifted out as a separate block (the keystone) and set apart by a
narrow channel.

| Part | Meaning |
| --- | --- |
| **The wall**: one continuous L-shaped enclosure | The isolated range: every class section has its own network, quota and perimeter. |
| **The courtyard**: the negative square | The training floor. The mark never fills it. |
| **The keystone**: the lifted corner, the only colour | The learner, the piece that completes the structure. The silhouette only reads as a whole square with it in place. |
| **The channel** | The single, controlled way in. |

### Construction (64-unit grid)

| Element | Units | At 16 px |
| --- | --- | --- |
| Outer bounds | 4 → 60 (56) | 1 → 15 px |
| Wall weight **W** | 12 | 3 px |
| Courtyard | 16 → 48 (32) | 8 px |
| Channel | 8 | 2 px |
| Keystone | 36 → 60, 4 → 28 (24 = 2W) | 6 px |

Every coordinate is a multiple of 4, so the mark lands on whole pixels at 16,
24, 32 and 48 px. There are no curves and no hairlines.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <path fill="#0D0D10" d="M28 4H4v56h56V36H48v12H16V16h12z"/>  <!-- wall -->
  <rect fill="#2F6FE0" x="36" y="4" width="24" height="24"/>   <!-- keystone -->
</svg>
```

### Files

| File | Use |
| --- | --- |
| `palestrix-mark.svg` | Default. Follows `prefers-color-scheme`. |
| `palestrix-mark-on-dark.svg` | Chalk wall + Signal Blue, for Ink or darker grounds. |
| `palestrix-mark-on-light.svg` | Ink wall + Keystone Blue, for Paper or white. |
| `palestrix-mark-mono.svg` | `currentColor`, for embroidery, etching, foil and one-colour print. |

### Rules

- **Clear space:** 1W (3/16 of the mark's width) on every side.
- **Minimum size:** 16 px on screen, 6 mm in print.
- **Name:** always **PalestrIX**, set in Geist 600 with "IX" in the accent.
  Never Palestrix, PALESTRIX or Palestr-IX.
- **Lockup:** mark at 1.25× the text size (snapped to 4 px), with a gap of 0.4× the mark.
  The mark may stand alone. The wordmark may not.
- **On photos:** only over a Palaestra Ink scrim of 60% or more.

**Don't:** stretch, rotate or mirror it; close the channel; move the keystone
from the top-right; animate or offset the keystone outward (a block leaving the
wall reads as a sandbox escape); add gradients, glows, shadows, bevels or
outlines; turn the keystone gold or red; put anything in the courtyard.

**Motion:** the only sanctioned animation is the keystone *seating* inward into
place (240 ms, `--ease-swift`), on first load or when a flag is captured.

---

## 2. Story and voice

**Mission.** Give every institution a real, contained cyber range, so students
train on genuine systems and earn their standing through verified progress.

**Audience, in order of priority:** the department chairs and IT directors who
approve it, the faculty who teach on it, and the students who compete on it.

**Personality:** Rigorous · Disciplined · Candid · Quietly competitive.

**Values:** real over simulated · contained by design · earned, not farmed ·
open by default.

| How we speak | How we don't |
| --- | --- |
| Your lab expires in 42 minutes. Extend for 150 Palestras. | Your epic session is almost over! |
| Each class section runs on its own VLAN with its own quota. | Military-grade, bulletproof security. |
| Launch blocked: section quota is 12 vCPU and 12 are in use. | Oops! Something went wrong 😅 |
| +40 Palestras · first blood on web-03. | GG, you totally pwned it, legend! |
| Samples detonate in a network-isolated sandbox. Nothing leaves. | Unleash real malware and hack like the elite! |
| The VirtualBox path is for demos. It does not produce study data. | Runs anywhere, perfectly, every time. |

---

## 3. Colour

Dark-dominant. There is one accent, blue. Gold is reserved for Palestras. The
proportion is roughly **70 / 18 / 9 / 3** (Ink and surfaces / Chalk / blue / gold).

### Primary

| Name | Token | HEX | RGB | CMYK | Role |
| --- | --- | --- | --- | --- | --- |
| Palaestra Ink | `--background` (dark) | `#0D0D10` | 13 13 16 | 19 19 0 94 (large areas: rich black 60 40 40 100) | Ground |
| Keystone Blue | `--accent` (light) | `#2F6FE0` | 47 111 224 | 79 50 0 12 (≈ Pantone 2727 C, proof it) | Keystone on light, CTAs, links, print |
| Signal Blue | `--accent` (dark) | `#6F97EE` | 111 151 238 | 53 37 0 7 | Keystone on dark, CTAs, focus |
| Chalk | `--foreground` (dark) | `#EBEBF0` | 235 235 240 | 2 2 0 6 | Wall on dark, text |
| Laurel Gold | `--palestras-fg` (dark) | `#DFAF54` | 223 175 84 | 0 22 62 13 | **Palestras and streaks only** |
| Laurel Bronze | `--palestras-fg` (light) | `#7C5410` | 124 84 16 | 0 32 87 51 | Gold on light grounds |

### Neutrals and semantic colours

| Name | HEX | Role |
| --- | --- | --- |
| Court | `#141419` | Dark surface |
| Colonnade | `#1B1B22` | Dark surface 2 |
| Seam | `#26262E` | Dark border |
| Ash | `#9C9CA8` | Muted text on dark |
| Slate | `#63636E` | Muted text on light |
| Mortar | `#E2E2E6` | Light border |
| Paper | `#F6F6F7` | Light ground |
| Marble | `#FCFCFD` | Light surface |
| Breach Rose / Red | `#E2607B` / `#B3243F` | Danger, expired, malicious. Never marketing. |

Contrast: Signal Blue on Ink is 6.78:1 and Chalk on Ink is 16.33:1. Keystone
Blue on Paper is 4.35:1, which is fine for UI, links and large text but not for
small body copy.

CMYK values are direct conversions. Match the spot colour against a physical
swatch on a press proof before the first print run.

---

## 4. Typography

| Role | Face | Use |
| --- | --- | --- |
| Primary (headings and UI) | **Geist** 400/500/600 | Headlines, navigation, buttons, product body |
| Secondary (long-form body) | **Source Serif 4** 400/600 | Marketing body, docs articles, faculty reports, certificates |
| Utility (technical) | **Geist Mono** 400/500 | IPs, ports, hashes, timers, flags, scores, logs, eyebrows. Always tabular. |

All three are SIL OFL and on Google Fonts. The product keeps Geist for all UI
body text. Source Serif 4 is for editorial and academic contexts.

| Level | Spec |
| --- | --- |
| H1 | Geist 600 · 56/58 px · −3.5% tracking · max 2 lines |
| H2 | Geist 600 · 32/37 px · −2% |
| H3 | Geist 600 · 20/27 px · −1% |
| Body (long-form) | Source Serif 4 400 · 18/30 px · ≤ 65ch |
| Body (UI) | Geist 400 · 15/24 px |
| Eyebrow | Geist Mono 500 · 11–12 px · +9% · uppercase |
| Data | Geist Mono 400 · 13–14 px · `tabular-nums` |

---

## 5. Iconography and imagery

**Icons:** Phosphor Regular (1.5 px on a 24 px grid). Selected state uses
Phosphor Fill in the accent. Custom icons use square caps, mitred joins and at
most a 2 px radius. No duotone, gradient or multi-colour icons. The 6 px
keystone square is the bullet and unread dot.

**Imagery:** real campus hardware and real students, photographed on site,
desaturated 30–50% under a 60–75% Ink scrim. Wireframe and topology abstractions
in Ash with Signal Blue nodes. Product screenshots in real states. **Never** use
hooded hackers, green code rain, skulls, glowing padlocks, binary globes or
AI-generated faces.

---

## 6. Applications

- **Dark-mode dashboard.** Ink ground, Court sidebar with the 15 px lockup,
  12 px cards on Seam borders. Signal Blue appears once per view, on the
  primary action. TTL in Geist Mono tabular, Palestras in the gold chip only,
  lifecycle as pastel pills.
- **NFC business card.** 85 × 55 mm soft-touch rich black, edges painted
  Keystone Blue. The front is the mark alone: the wall as tonal spot-UV, the
  keystone in blue foil, with the NTAG216 chip behind the keystone ("tap the
  keystone"). The back has the name in Geist 600 and contacts in Geist Mono.
- **Matte black hoodie.** 420 gsm. Left chest: 64 mm embroidery (Chalk wall,
  Signal Blue keystone). Back: 260 mm tonal puff print with "RANGE 01 · COHORT
  2026" in Geist Mono. Left sleeve: a 12 mm woven keystone tab. Issued only
  on completing a learning path.
