# Saradi

Saradi (Kannada: ಸರದಿ, "your turn") tells elders in Bengaluru when to leave home for a doctor's visit, so they don't sit in OPD waiting rooms for hours. It calls the elder by voice in Kannada, Hindi or English, and keeps the family (often abroad) updated on WhatsApp. It works at any hospital, with no partnership needed, using whatever queue signal exists.

Status: first working build (simulation mode), for the Bolna.ai hackathon (submit by 31 Oct 2026).

## Run it
Needs only Python 3.11+ (standard library, nothing to install).

```bash
python -m saradi
```

Open http://127.0.0.1:8765 and click **Load cold-start demo**. Use the +5/+15/+30 min buttons or the speed menu to move time. Answer the elder's calls in the "Elder's phone" column, and enter check-ins on the visit card.

Run the tests:

```bash
python -m unittest discover -s tests -t .
```

## On a phone
The dashboard is built for phones first. Below 720 px wide (and on landscape phones) it shows one section at a time with a bottom tab bar: **Plan**, **Phone** (a pink dot means a call is ringing) and **Family** (a number shows unread messages). The clock and demo controls move into the sliders button, which opens the **Demo tools** sheet. Below 1360 px they use that sheet too, so laptop headers stay on one row.

To open it on a phone on the same Wi-Fi, set `SARADI_HOST=0.0.0.0` before `python -m saradi` and browse to your computer's address and port. Anyone on that network can then use the dashboard, so only do this on a trusted network.

## Hints
Every button has a one-line explanation.
- **Mouse:** hover, or tab to a button with the keyboard.
- **Touch:** press and hold a button for half a second. The hint appears and the button is not pressed.
- **Hints mode:** tap the **?** button (in the header and in each sheet). While it's on, tapping any button shows what it does instead of doing it. Tap **?** again to turn it off.

## Family notifications
The bell opens a sheet where each family member chooses what they hear: morning plan, leave time changes, elder has left, and the visit summary, plus optional quiet hours. **Urgent alerts** (elder unwell, can't be reached, confused) are always sent and can't be turned off. Updates that are muted, or fall in quiet hours, are skipped, not delayed, and show as "Not sent" notes in the Family feed so nothing disappears silently. "Load cold-start demo" resets these settings to the defaults.

## How it works, from zero data
Day one has no Saradi families and no history. Each visit uses the best signal available:

| Signal | Where it comes from | Needs anyone's goodwill? |
|---|---|---|
| Live token link | The hospital's own queue tool (TOKENN, OPDly and similar) sends the patient a link; the family pastes it in | No |
| Family check-ins | "Token 9 running", "doctor not in", "3 patients ahead", "called in" | Only our own paying customer |
| One reception call | The family calls once at OPD start, as any patient would | Normal patient behaviour |
| Doctor history | Every completed visit, plus the family's memory at sign-up ("last time, seen 2 hours late") | No |
| Default assumption | Generic OPD figures, used when nothing else exists | No |

With no data at all, Saradi honestly says so: leave at the usual time. It still does the elder call, the family updates and the escalation, and the visit is recorded so the next one is better. Token readings are shared by every patient of that doctor that day.

Estimates are ranges (likely seen between X and Y). The leave time is planned off the early end, so an elder risks a short wait, never a missed turn.

### Elder calls
1. **Morning plan call**, about 2 hours before the usual leave time: "Be ready by 12:05. Don't leave yet."
2. **Leave-now call** when the leave time arrives. The elder answers by voice: leaving / already left / not feeling well / call later / who is this?
3. **No answer twice, unwell or confused:** the family gets an urgent WhatsApp.
4. **After the visit:** the family gets the wait time, and the same neutral Google review prompt as everyone (see COMPLIANCE.md).

## Going live (needs your accounts)
1. **Bolna calls:** follow [SETUP_BOLNA.md](SETUP_BOLNA.md). Saradi polls Bolna for call results, so no public URL is needed. `POST /webhooks/bolna` also exists for when it's deployed.
2. **Telegram alerts for the family (free, best for the demo):** message **@BotFather** on Telegram, send `/newbot`, and paste the token into `TELEGRAM_BOT_TOKEN` in `.env` (keep `SARADI_MESSENGER=telegram`). Restart the app, then click the "Open Telegram to connect" link on the visit card and press Start. The link holds a random code, never a phone number, and only the first Telegram account to use it gets linked. Alerts sent before someone connects are recorded as "not connected".
3. **WhatsApp:** a Meta WhatsApp Cloud API number and token, with `SARADI_MESSENGER=whatsapp`. Free text only reaches users who messaged first in the last 24 hours, so approved templates are needed before real use.

## Code
| Path | What |
|---|---|
| `saradi/predictor.py` | Turn-time ranges from live data, history or the default |
| `saradi/engine.py` | Visit lifecycle: brief, watch, call, escalate, learn |
| `saradi/voice.py` | Simulated calls and Bolna calls, plus webhook parsing |
| `saradi/messaging.py` | Simulated and WhatsApp Cloud family messages |
| `saradi/clinic_link.py` | Best-effort reader for a forwarded live token page |
| `saradi/server.py` | Local web server, API and background loop |
| `web/` | Dashboard |
| `tests/` | Unit tests |

## Docs
| File | What it's for |
|---|---|
| [COMPLIANCE.md](COMPLIANCE.md) | Reviews, ethics codes, patient data, calls, WhatsApp |
