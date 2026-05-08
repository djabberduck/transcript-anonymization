# TRUST.md — What to trust, what to verify, what this skill cannot do

This document is for researchers who need to understand the reliability of this
skill before using it in studies involving sensitive participant data.

**Bottom line up front:** This skill is a strong first pass, not a guarantee.
Presidio's rule-based detection covers structured PII well but has known gaps
around informal name references and indirect identifiers. Manual spot-checks
(listed below) are a required part of the process, not optional.

---

## What Presidio does well

| Entity type | Reliability | Notes |
|-------------|-------------|-------|
| Email addresses | ✅ High | Rule-based; near-perfect |
| Phone numbers | ✅ High | Rule-based; near-perfect |
| Common Western full names | ✅ Good | "John Smith"-style names reliably caught |
| Large company names | ✅ Good | Google, Microsoft, Apple etc. reliably caught |

---

## Where Presidio struggles — what to check manually

These are the known gaps in rule-based detection. The recommended manual checks
below are designed to catch precisely these cases.

- **Unusual or non-Western names** — trained predominantly on Western name
  patterns. Arabic, East Asian, South Asian names may be missed
- **First names used alone** — "I spoke to Sarah" has low confidence without
  a surname
- **Casual name references** — "My manager Dave" less reliable than "David Johnson"
- **Small or niche companies** — startups, internal team names often missed
- **Informal org references** — "those guys in Stockholm" not flagged
- **Indirect identifiers** — role + location + industry combinations not detected
- **Social handles, unique event references** — not in Presidio's entity set

---

## False positives

Presidio occasionally flags things that are not PII:
- Job titles like "Manager", "Director" at low confidence
- Common words that happen to match name patterns

`anonymize.py` automatically suppresses two common categories before Presidio
tags them:
- **Timestamps** (e.g. `00:05:40`, `1:23`) — common in interview transcripts
- **Well-known product names** (Gmail, YouTube, Google, Slack, Notion, Figma,
  Zoom, etc.) when misidentified as PERSON

Product names detected as ORGANIZATION are not filtered — those may be
legitimate org references depending on context. Review them manually.

The 0.6 confidence threshold in the Step 0b verification snippet filters
remaining likely false positives. Review any flags above that threshold manually.

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

---

## Recommended manual checks before sharing externally

Do these checks before sharing transcripts outside your immediate team:

1. **Read the first and last 200 words of each transcript** — participants
   often introduce themselves at the start and mention names at the end
2. **Search for "@"** — catches any emails missed
3. **Search for "my colleague", "my manager", "Mr.", "Ms.", "Dr."** —
   these often precede names
4. **Skim for re-identification risk** — role + location + industry
   combinations that could identify someone without a name
5. **Check any quotes** — participants sometimes name-drop colleagues,
   competitors, or clients in passing
6. **Scan for non-Western names** — Presidio is weaker here; read carefully
   if your participant pool includes non-Western names

---

## How confident should you be?

| Use case | Confidence | Recommendation |
|----------|------------|----------------|
| Internal team analysis | ✅ High | Run Steps 0 + 0b, do manual spot-check |
| Automated pipeline (Cursor/Code) | ✅ High | Best for reproducible workflows with JSON audit trail |
| Sharing with external partners | ✅ High | Manual review of flagged items required |
| Publishing quotes in reports | ⚠️ Medium-High | Human eyes on every quote that appears publicly |
| Privacy team approval / audit trail | ✅ High | JSON logs from Steps 0 + 0b serve as audit evidence |
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
3. The confidence score if available
4. Whether the miss was caught by manual spot-check or not

This helps improve threshold settings and false-positive suppression for future
versions.
