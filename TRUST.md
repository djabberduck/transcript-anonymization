# TRUST.md — What to trust, what to verify, what this skill cannot do

This document is for researchers who need to understand the reliability of this
skill before using it in studies involving sensitive participant data.

**Bottom line up front:** This skill is a strong first pass, not a guarantee.
The right level of confidence depends on which mode you use. Read the section
that applies to you.

---

## Mode A (Claude.ai / Cowork) — what to trust

In Mode A, Claude performs the anonymization directly using language
understanding. This has different strengths and weaknesses from the Python
pipeline.

### What Claude does well in Mode A

| Entity type | Reliability | Notes |
|-------------|-------------|-------|
| Contextual name references | ✅ Strong | "my manager Dave", "I asked Sarah to..." reliably caught |
| Indirect identifiers | ✅ Strong | Role + location combinations flagged as risks |
| Emails and phone numbers | ✅ Strong | Pattern recognition is reliable |
| Formal full names | ✅ Strong | "John Smith", "Maria Chen" reliably caught |
| Unusual or non-Western names | ✅ Better than Presidio | Language model handles these better than rule-based NLP |

### Where Mode A is weaker

- **Not deterministic** — running the same transcript twice may produce
  slightly different placeholder assignments or catch different items
- **No machine-readable audit log** — you get a text summary in chat, not
  a structured JSON file. Copy and save it manually
- **Transcripts leave your machine** — content is sent to Anthropic's API.
  Check your organisation's data policy before using with highly sensitive data
- **Context window limits** — very long transcripts (>50,000 words) may need
  to be split into sections

### Audit trail in Mode A

Claude produces a substitution summary in the chat window. To create an audit
record:
1. Copy the substitution log from the chat
2. Save it as a text or markdown file alongside your anonymized transcript
3. Note the date, your name, and which version of the skill was used

This is sufficient for internal team use. For formal Privacy team approval,
Mode B's JSON logs are stronger evidence.

---

## Mode B (Python Pipeline) — what to trust

In Mode B, two tools run in sequence: Presidio (rule-based) then Claude API
(contextual). Each covers the other's blind spots.

### What Presidio does well

| Entity type | Reliability | Notes |
|-------------|-------------|-------|
| Email addresses | ✅ High | Rule-based; near-perfect |
| Phone numbers | ✅ High | Rule-based; near-perfect |
| Common Western full names | ✅ Good | "John Smith"-style names reliably caught |
| Large company names | ✅ Good | Google, Microsoft, Apple etc. reliably caught |

### Where Presidio struggles (why Claude second-pass matters)

- **Unusual or non-Western names** — trained predominantly on Western name
  patterns. Arabic, East Asian, South Asian names may be missed
- **First names used alone** — "I spoke to Sarah" has low confidence without
  a surname
- **Casual name references** — "My manager Dave" less reliable than "David Johnson"
- **Small or niche companies** — startups, internal team names often missed
- **Informal org references** — "those guys in Stockholm" not flagged
- **Indirect identifiers** — role + location + industry combinations not detected
- **Social handles, unique event references** — not in Presidio's entity set

### What the Claude second-pass adds

The `verify_pii.py` script specifically prompts Claude to look for what
Presidio misses: casual name references, indirect identifiers, named third
parties, and unique identifying details. Together the two tools cover:

- Presidio catches: structured PII (emails, phones, formal names, major orgs)
- Claude catches: contextual PII (casual references, indirect identifiers,
  unusual names, niche companies)

### What the PII log tells you (and doesn't)

The `_pii_log.json` file records every Presidio substitution:
- ✅ What was found and replaced
- ✅ Entity type and confidence score

It does not tell you:
- ❌ What Presidio looked at and decided was NOT PII
- ❌ Whether anything was missed
- ❌ Whether indirect identifiers are present

An empty log means Presidio found nothing — not that there is nothing to find.
Always run `verify_pii.py` as a second pass.

---

## False positives (both modes)

Both Claude and Presidio occasionally flag things that are not PII:
- Job titles like "Manager", "Director" at low confidence
- Product names (e.g., "Notion", "Figma") detected as organisations
- Common words that happen to match name patterns

In Mode B, the 0.6 confidence threshold in `verify_pii.py` filters likely
false positives. Review any remaining flags manually before removing them.
In Mode A, Claude will generally explain its reasoning — push back if a
flagged item looks wrong.

---

## Recommended manual checks before sharing externally

Regardless of which mode you use, do these checks before sharing transcripts
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

---

## How confident should you be?

| Use case | Mode | Confidence | Recommendation |
|----------|------|------------|----------------|
| Quick internal check | Mode A | ✅ High | Sufficient for internal use |
| Internal team analysis | Mode A + manual spot-check | ✅ High | Recommended default for researchers |
| Automated pipeline (Cursor/Code) | Mode B (Steps 0–0c) | ✅ Very high | Best for reproducible workflows |
| Sharing with external partners | Either + manual spot-check | ✅ High | Manual review of flagged items required |
| Publishing quotes in reports | Either + manual review of every quote | ⚠️ Medium-High | Human eyes on every quote that appears publicly |
| Privacy team approval / audit trail | Mode B + JSON reports | ✅ High | JSON logs from both steps serve as audit evidence |
| Regulatory/legal compliance (GDPR, HIPAA) | Any mode + DPO review | ❌ Not sufficient alone | This tool does not constitute compliant anonymization under law |

### Why the mode matters for Privacy approval

Mode A produces a text summary that you save manually — useful, but not
machine-verifiable. Mode B produces timestamped JSON logs from two independent
detection systems, which gives Privacy teams a documented, repeatable audit
trail. If you need formal sign-off, use Mode B and retain the JSON reports.

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
3. The confidence score if available (Mode B)
4. Which mode you were using

This helps improve threshold settings and prompts for future versions.
