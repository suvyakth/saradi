# QA notes: dashboard UI pass (2026-10-20)

Tested in the in-app browser against a **simulation-only** instance (`SARADI_VOICE=sim`, `SARADI_MESSENGER=sim`, port 8777, scratch database), never the live Bolna instance on 8765, so no real calls or messages were triggered. Widths checked: 1440, 768, 375. Light and dark themes both checked.

## Bugs found
| # | Where | What | Status |
|---|---|---|---|
| 1 | `saradi/server.py` `demo()` | "Load cold-start demo" failed with an alert, "missing: family_phone", whenever `.env` was copied from `.env.example` (blank `SARADI_DEMO_*` values beat the code defaults). The clock still jumped to 10:00 and the data was wiped before the failure. | **Fixed**: blank values now fall back to the defaults. |
| 2 | `web/app.js` | Errors used a blocking `alert()`. | **Fixed**: non-blocking toast. |
| 3 | `demo()` | The demo wipes tables *before* validating its inputs, so a failed demo leaves the app empty. | Open, backend; not changed |
| 4 | Sim calls | The script is English even when "spoken in Kannada". Fine for simulation, but the demo should say so. | Open, content |
| 5 | Visit card | The basis text repeats the "No data yet" badge. | Open, copy |
| 6 | Call timing | If time is advanced in jumps, the leave-now call is placed at the jump time (12:17), not the planned leave time (12:05). | Open, behaviour; not changed |

## UI issues found and fixed
- Column tops and first cards were misaligned (the "New visit" button made the Visits header taller). Now all three heads sit at the same y and share a min height.
- Leave time, likely-seen range and countdown floated with no structure; now stat tiles, with the leave time as the hero tile.
- The "in N min" countdown was an orphan element; now its own tile, hidden when not relevant.
- The 8 check-in buttons were one unlabeled wall; now grouped under Queue signals and Journey, with input and button fused.
- The family message was a plain green box, now a WhatsApp-style bubble with sender, line spacing and right-aligned timestamp in a chat panel.
- Calls had no visual identity; now a phone avatar, quoted script with accent rule, and an "Answer as Ajji" label.
- Header: the clock, simulation-mode pills and controls are now grouped. The time buttons are one segmented control. Mode pills turn red when live.
- Form: inputs in one row sat at different heights when a label wrapped; now bottom-aligned.
- Mobile (375): the clock dot was squashed to an oval, the date wrapped onto two lines, and the sticky header took about 30% of the screen. All fixed, header is static on phones.
- Added a page title, description, favicon, empty-state boxes, focus rings and a footer line.

## Measured at 1440
- Column heads all at y=88, first cards all at y=154.
- No horizontal overflow at 1440, 768 or 375.
- Console: no errors after the fixes.
- Unit tests: 28 passing.

## Still to check
- With real Bolna calls: how a "calling" state looks while a call is live.
- Telegram connect row (needs a bot token).
- Long names and hospital names (wrapping looks fine up to about 30 characters).

## Round 2: dark neon redesign (2026-10-20)
Restyled to a "midnight clinic" theme (dark only, Space Grotesk): neon green for the plan, cyan for the elder's phone, violet for the family, amber and pink for warnings and alerts.

Animations (all disabled under `prefers-reduced-motion`):
- Drifting aurora background and a faded grid; sweeping logo hand; pulsing clock dot and a glow flash on each clock tick.
- Hero headline with flowing gradient text; flow pills light up in turn with a travelling pulse between them.
- Journey tracker (Planned → Waiting → Calling → On the way → At hospital → With doctor → Done) with a glowing progress rail.
- Rotating conic-gradient border on the "Leave home at" tile.
- Ringing phone: shaking avatar with ripple rings; cyan glow on the card while calling; pink pulse when the family is alerted.
- New cards and chat bubbles animate in once (never replayed on refresh); confetti burst when a visit reaches Done.

Bugs found in this round and fixed:
- Class collision: the stat tile's `hero` class picked up the hero section's grid rules and squeezed "12:05" to 37px. Renamed to `key`.
- Flow pills used `:nth-of-type` across mixed spans, so colours were off by one and the last pill had no dot.
- Check-in placeholders ("token", "count") were clipped; inputs widened.
- Mobile: flow connectors dangled when pills wrapped; hidden under 720px.

Not verified: the Google Fonts request needs internet. Offline it falls back to Inter or the system font, which still looks fine, but the demo laptop should be online or the font should be self-hosted.

## Round 3: toned down (2026-10-20)
Removed: drifting background, sweeping logo hand, clock flash, shimmer on the primary button, looping flow-pill highlight and travelling pulse, rotating border on the leave-time tile, glow pulses on live and alert cards, phone shake, all text and avatar gradients, glows on buttons and tracker. Kept: a static soft background glow, a quick 0.35s fade-in for new items, the tracker rail moving, the ripple on a ringing call, and a smaller finish burst (18 particles).

## Round 4: phone-first, hints, notification settings (2026-10-20)
Tested on my own sim-only server (port 8777, scratch DB), never the live one. Layout checked at 375, 360, 320, 812x375 landscape, 768, 1024, 1180, 1280, 1370 and 1440. Behaviour tested through the real DOM under touch emulation.

Added:
- Phone layout (under 720px, and short landscape): one section at a time with a bottom tab bar. Pink dot on Phone while a call rings; unread count on Family. Demo controls live in a bottom sheet (also used below 1360px so laptop headers stay one slim row).
- Simpler visit card: one "Next step" button, with the other reporting buttons and the event log folded away (open state survives refreshes).
- Hints for every button: hover and keyboard focus on desktop, press-and-hold on touch, and a "?" hints mode where taps explain instead of act. The "?" is also inside each sheet.
- Family notification settings (bell): morning plan, leave-time changes, elder has left, visit summary, quiet hours, presets. Urgent alerts are always sent. Muted messages are recorded and shown as "Not sent" notes.

Bugs found and fixed:
- Sheet scroll-lock never released (the async `close` event did not fire reliably). Now driven by a MutationObserver on `open`; verified for close button, backdrop, programmatic close and requestClose.
- History count pill stretched across its row.
- 320px header wrapped the icons to a second row (Kannada wordmark hidden under 360px).
- Landscape header took a third of the screen height (now one row); content capped at 680px wide.
- Desktop header wrapped after the new buttons (tagline hidden under 1500px; controls move to the sheet under 1360px).
- Hints button was unreachable inside an open sheet (added one to each sheet).
- "Load cold-start demo" did not reset notification settings, so a muted family stayed muted in the next demo. Now reset, with tests.

Checks that passed: no tap target under 44px on phone, no horizontal overflow at any width, 42 unit tests (14 new).

Not verified (needs a real phone): iOS Safari quirks (dialog, popover, safe-area insets), real touch scrolling, the on-screen keyboard covering the form. Press-and-hold timing was tested with synthetic touch events, not a finger.

Tooling note: the browser pane's phone emulation mis-crops screenshots (it shows only the top-left part). Phone screenshots here were taken by loading the app in an exact-size iframe inside a desktop page; layout numbers came from the emulated page itself.

## Round 5: pre-submission trim (2026-10-29)
- Removed the three "Plan the visit / Call the elder / Tell the family" pills: they repeated the numbered column headers and pushed the app down. The headline stays; the one-line description is hidden below 1100px.
- The first family message no longer says "no data" twice (dropped the "Based on: ..." line when the plan is only the usual timings).
- 42 tests pass. Layout re-checked at 1440, 1024 and 375.
