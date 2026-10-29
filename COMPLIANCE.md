# Compliance and ethics rules

Not legal advice. These rules come from research done on 2026-10-19; re-verify before launch.
Where the source is a secondary summary rather than the official text, it says so.

## Google reviews
Sources: summaries of Google's policy by DemandHub, ApplauseHQ and WiserReview (secondary, but consistent with each other).
- **Prompt every visit, everyone.** Show the same neutral "Share your experience with Dr. X on Google" after every visit, to every user.
- **No gating.** Never put an in-app rating before the Google link, and never show the link only to happy users. This is banned.
- **No rewards.** No credits, discounts or perks for reviewing. Reporter credits (for queue reports) must stay completely separate from reviews.
- **No scripting.** Don't suggest stars, keywords or staff names.
- **No pressure on site.** The prompt comes in the app after the visit, not at the desk.
- **Who may review:** the person who went, and the family member who booked and coordinated, writing as themselves ("I booked for my mother from abroad..."). Never pretend to have been in the waiting room.
- **No spikes.** A steady, natural flow survives spam filters; sudden bursts from one app link get removed quietly.
- The clinic must never repost reviews as testimonials (see the next section).

## Dentists' ethics code (Revised Dentists Code of Ethics Regulations, 2014, national)
Source: the regulations' text (Tamil Nadu Dental Council copy).
- **5.1.1 and 5.1.2:** no commissions, gifts or gratuities for referred patients.
- **8.1.1:** no demeaning solicitation or false promises in advertising or direct marketing.
- **8.1.2:** no promotion that "cold targets" vulnerable groups, including old age homes.
- **8.1.4:** no agents or canvassers to obtain patients commercially.
- **NDC advisory, 14 Oct 2026:** dentists must not post patient endorsements or before/after photos. Penalties go up to removal from the register.

What this means for us:
- The clinic pays nothing, and never per patient.
- We never market "we send you patients", and never promote a specific dentist to elders.
- We are an operations tool (queue, alerts, fewer calls), not a lead-generation or advertising channel.
- The same caution applies to doctors: NMC rules bar fee-splitting, and its Oct 2026 advertising guidelines bar fabricated testimonials. A doctor stays responsible for content made by third parties they knowingly permit.

## Patient data (DPDP Act, 2023)
- Collect the minimum: patient name, phone, clinic, doctor, appointment time, token, and timestamps. No diagnoses or medical records in the MVP.
- **Explicit consent** at sign-up, in plain language, covering WhatsApp messages, AI voice calls and data use. Make withdrawal easy.
- **Family accounts:** the elder consents (or a family member with the elder's agreement). Log who consented.
- Delete visit data on request. Set a retention period (for example, anonymise after 12 months, keeping only aggregated delay statistics).
- **Needs a legal entity** (company or registered firm) before handling real patient data at scale. Decide who signs the partner and clinic agreements.
- Re-verify the DPDP Rules timeline and obligations before launch.

## Voice calls
- The AI says it is an automated assistant at the start of every call.
- If calls are recorded, say so at the start.
- **Outbound calls only to users who opted in** (alerts for their own visit). No promotional calls; Indian unsolicited-call (TRAI) rules target those.
- No caller-ID rotation, no number spoofing, no repeated polling of clinic desks.

## WhatsApp
- Only message users who opted in.
- Use approved message templates for alerts.
- Keep alerts transactional. Marketing messages cost more and need separate opt-in.

## Runners and crowd reporters
- Runners: background-checked, trained, insured, non-clinical. Never give medical advice. Hire through a local agency or partner.
- Never pay hospital or clinic staff for information. It can look like a bribe.
- Government hospitals: no place-holding at first, because it can look like touting.
- Crowd reporter payouts: batched, with anti-fraud checks.

## Doctor data
- Delay scorecards stay private to the user and family, and factual only.
- Never publish named doctor ratings or rankings, because of defamation risk and clinic pushback.

## Sources
- Google review policy summaries: https://demandhub.co/articles/google-review-policy · https://www.applausehq.com/blog/googles-rules-for-incentivizing-reviews · https://wiserreview.com/blog/review-gating/
- Revised Dentists (Code of Ethics) Regulations 2014: https://tndentalcouncil.com/source/dentists_code_of_ethics_regulations_2014.pdf
- NDC advisory, Oct 2026: https://medicaldialogues.in/news/health/doctors/national-dental-commission-warns-dentists-against-unethical-social-media-advertising-181335
- NMC advertising guidelines, Oct 2026: https://thesouthfirst.com/health/doctors-on-instagram-nmc-says-no-to-patient-testimonials-paid-ads-ai-promotions-and-guaranteed-claims/
