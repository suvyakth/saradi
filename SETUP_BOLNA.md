# Getting real calls working with Bolna

About 20 minutes. You need a Bolna account and a relative in India who has agreed to get test calls.
Saradi asks Bolna for each call's result every few seconds, so you don't need a public URL, a webhook or a tunnel.

Bolna's dashboard changes often, so button names below may differ slightly. The API details were checked against Bolna's docs on 2026-10-20.

## 1. Account and API key
1. Sign up at https://platform.bolna.ai (use the hackathon's sign-up link if it gives credits).
2. Find the API key in the dashboard (usually under Developers or API Keys). It starts with `bn-`.
3. Check the wallet balance. Calls are prepaid per minute, and calls to India go through Bolna's default number unless you buy or connect one.

## 2. Create the agent in the dashboard
Create a new agent, then set:

| Setting | Value |
|---|---|
| Name | Saradi elder call |
| Welcome message | `Namaskara {{elder_name}}, this is Saradi, calling for {{family_name}}.` |
| System prompt | The "System prompt" section of [prompts/elder_agent.md](prompts/elder_agent.md) |
| LLM | Any of Bolna's preferred models (keeps the flat per-minute rate) |
| Voice (synthesizer) | Sarvam, model `bulbul:v3`, voice `priya` (works in Kannada, Hindi and English), language `kn` for Kannada |
| Transcriber | Sarvam, if it offers Kannada; otherwise Deepgram with the closest option |
| Call summary / extraction | Paste [prompts/extraction_prompt.md](prompts/extraction_prompt.md) into the extraction settings, and keep the key name `elder_response` |

Notes:
- The voice reads the script it's given, so the prompt tells the model to reply in Kannada script. If calls come out in English, check the voice's language is `kn` and the prompt was pasted in full.
- One agent can do Kannada and Hindi only if the voice supports both. `bulbul:v3` voices do; with other models, make one agent per language.
- Save the agent and copy its **agent ID** (a UUID).

Test it first with the dashboard's own "call me" or test-call button, using your own number, to hear the voice before involving relatives.

## 3. Put the keys in `.env`
Copy `.env.example` to `.env` in this folder, and fill in:

```
SARADI_VOICE=bolna
BOLNA_API_KEY=bn-...
BOLNA_AGENT_ID=...
SARADI_DEMO_ELDER_PHONE=+91...   (the relative who agreed)
SARADI_DEMO_FAMILY_NAME=...
SARADI_DEMO_FAMILY_PHONE=+358...
```

`.env` is git-ignored, so the key won't be committed. Type the key in yourself; don't paste it into a chat.

## 4. Check the key, then place one test call

```bash
python -m saradi.check_bolna
```

That only checks the key and shows the balance. Then place one test call to your relative:

```bash
python -m saradi.check_bolna --call +91XXXXXXXXXX --language kannada
```

It waits up to 3 minutes and prints how it understood the answer (`leaving`, `unwell`, `call_later`, `confused`, `no_answer`) plus the transcript. Ask your relative to try different answers on different calls: "okay, leaving", "I'm not feeling well", "who is this?", and not picking up.

## 5. Run the full demo with real calls

```bash
python -m saradi
```

Open http://127.0.0.1:8765 and click **Load cold-start demo**. The header shows `voice: bolna`. Calls now go to the relative's phone, and their answers appear on the dashboard within a few seconds of the call ending. Family messages stay simulated until WhatsApp is set up.

## If something fails
| What you see | Likely cause |
|---|---|
| `Bolna rejected the API key` | Wrong key, or extra spaces in `.env` |
| `Call was not placed: error: HTTP Error 400` | Agent ID wrong, or the number isn't in `+91...` format |
| Status `failed` or `balance-low` | Wallet empty, or the account can't call that country yet. Ask Bolna support or the hackathon organisers |
| Speaks English instead of Kannada | Voice language not set to `kn`, or the prompt's script rule is missing |
| Answer understood as `confused` every time | Extraction prompt not saved, or its key isn't `elder_response` |

## Before calling anyone
- Only call relatives who agreed to test calls. The agent says it's an automated assistant.
- Keep calls short. Every minute costs wallet credit.
