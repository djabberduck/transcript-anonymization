# TRUST.md — What to trust, what to verify, what this skill cannot do

This document is for researchers who need to understand the reliability of this
skill before using it in studies involving sensitive participant data.

**Bottom line up front:** This skill is a strong first pass, not a guarantee.
Two complementary tools run in sequence — Presidio for structured PII,
a local LLM for contextual PII. Neither sends data off your machine.
Manual spot-checks (listed below) remain a required part of the process.

---

## What Presidio does well (Steps 0 + 0b)

| Entity type | Reliability | Notes |
|-------------|-------------|-------|
| Email addresses | ✅ High | Rule-based; near-perfect |
| Phone numbers | ✅ High | Rule-based; near-perfect |
| Common Western full names | ✅ Good | "John Smith"-style names reliably caught |
| Large company names | ✅ Good | Google, Microsoft, Apple etc. reliably caught |

---

## Where Presidio struggles — what the local LLM covers (Step 0c)

- **Unusual or non-Western names** — trained predominantly on Western name
  patterns. Arabic, East Asian, South Asian names may be missed
- **First names used alone** — "I spoke to Sarah" has low confidence without
  a surname
- **Casual name references** — "My manager Dave" less reliable than "David Johnson"
- **Small or niche companies** — startups, internal team names often missed
- **Informal org references** — "those guys in Stockholm" not flagged
- **Indirect identifiers** — role + location + industry combinations not detected
- **Social handles, unique event references** — not in Presidio's entity set

Step 0c specifically prompts the local LLM to look for all of the above.
Together the two tools cover each other's blind spots.

---

## What the local LLM adds (Step 0c)

The `verify_pii.py` script prompts the model to look for what Presidio misses:
casual name references, indirect identifiers, named third parties, and unique
identifying details.

| Detection type | Handled by |
|---------------|-----------|
| Emails, phones | Presidio (Steps 0 + 0b) |
| Formal full names, large orgs | Presidio (Steps 0 + 0b) |
| Informal name references | Local LLM (Step 0c) |
| Non-Western names | Local LLM (Step 0c) |
| Indirect identifiers | Local LLM (Step 0c) |
| Unique personal references | Local LLM (Step 0c) |

Note: Step 0b uses the same Presidio engine as Step 0, so it primarily serves
as a pipeline integrity check (confirming files were written and processed
correctly) rather than catching new missed PII. The local LLM in Step 0c
is the substantive second-pass check.

---

## False positives

Both Presidio and the local LLM occasionally flag things that are not PII.

**Presidio:** `anonymize.py` automatically suppresses two common categories:
- **Timestamps** (e.g. `00:05:40`, `1:23`) — common in interview transcripts
- **Well-known product names** (Gmail, YouTube, Slack, Zoom, etc.) when
  misidentified as PERSON

**Local LLM:** `verify_pii.py` suppresses known false positives for DDG
research transcripts:
- **"DuckDuckGo"**, **"DDG"**, **"Duck Duck Go"** — flagged as org context
  but expected and non-identifying in DDG's own research

Any suppressed items are logged in the terminal output and JSON report for
transparency. To add additional suppressions, update the `SUPPRESSED_TEXTS`
set in `verify_pii.py`.

---

## What the PII log tells you (and doesn't)

The `_pii_log.json` file records every Presidio substitution:
- ✅ What was found and replaced
- ✅ Entity type and confidence score

It does not tell you:
- ❌ What Presidio looked at and decided was NOT PII
- ❌ Whether anything was missed
- ❌ Whether indirect identifiers are present

An empty log means Presidio found nothing — not that there is nothing to find.
Always run Steps 0b and 0c before treating transcripts as clean.

---

## Recommended manual checks before sharing externally

Regardless of Step 0c results, do these checks before sharing transcripts
outside your immediate team:

1. **Read the first and last 200 words of each transcript** — participants
   often introduce themselves at the start and mention names at the end
2. **Search for "@"** — catches any emails missed
3. **Search for "my colleague", "my manager", "Mr.", "Ms.", "Dr."** —
   these often precede names
4. **Skim for re-identification risk** — role + location + industry
   combinations that could identify someone without a name
5. **Check any quotes** — participants sometimes name-drop colleagues,
   competitors, or clients in passing
6. **Scan for non-Western names** — the local LLM is better than Presidio
   here but not infallible; read carefully if your participant pool is diverse

---

## How confident should you be?

| Use case | Confidence | Recommendation |
|----------|------------|----------------|
| Internal team analysis | ✅ High | Run Steps 0–0c, do manual spot-check |
| Automated pipeline (Cursor/Code) | ✅ High | Best for reproducible workflows with full JSON audit trail |
| Sharing with external partners | ✅ High | Manual review of flagged items required |
| Publishing quotes in reports | ⚠️ Medium-High | Human eyes on every quote that appears publicly |
| Privacy team approval / audit trail | ✅ High | JSON logs from all three steps serve as audit evidence |
| Regulatory/legal compliance (GDPR, HIPAA) | ❌ Not sufficient alone | This tool does not constitute compliant anonymization under law — DPO review required |

---

## How this was validated

Tested on 6 English-language user research transcripts. Presidio correctly
returned empty PII logs on pre-anonymized transcripts, and verification passed
on all sampled files.

**Validation limitations:**
- Small sample size (6 transcripts)
- English only
- Structured interview format — less naturalistic than in-person interviews
- Transcripts may have been partially pre-anonymized by the research platform

Run your own spot-check on your first batch to calibrate for your context.

---

## Reporting issues

If this skill misses real PII or produces excessive false positives, document:
1. The entity type missed or falsely flagged
2. The approximate phrasing/context (do not share actual PII)
3. Which step missed it (Presidio / local LLM / both)
4. Whether it was caught by manual spot-check or not

This helps improve threshold settings and suppression lists for future versions.
