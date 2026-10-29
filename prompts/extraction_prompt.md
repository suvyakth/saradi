# Bolna extraction prompt

Paste into the agent's extraction settings. Saradi's webhook (`POST /webhooks/bolna`) looks for the key `elder_response`.

## Prompt

From the call transcript, return JSON with exactly one key, `elder_response`, set to one of:
- `leaving`: the elder agreed to leave now or said they are going.
- `already_left`: the elder is already on the way or at the hospital.
- `unwell`: the elder said they feel unwell, are in pain, or can't go.
- `call_later`: the elder asked to be called back later.
- `confused`: the elder didn't understand, didn't know who was calling, or the outcome is unclear.
- `no_answer`: nobody spoke, or it was a voicemail.

For a `brief` call with no problem mentioned, use `leaving`.

Example: {"elder_response": "leaving"}
