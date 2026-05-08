# Transcript Anonymization Skill — README

## What this is

A reusable skill for stripping PII (personally identifiable information) from
user research interview transcripts before any analysis begins.

PII replaced: person names, company/org names, email addresses, phone numbers.
Each is replaced with a consistent, readable placeholder (`[PERSON_1]`,
`[COMPANY_1]`, `[EMAIL_1]`, `[PHONE_1]`).

All processing runs locally using Microsoft Presidio. No transcript data is
sent to any external service or LLM.

---

## When to use this skill

| Situation | Recommendation |
|-----------|---------------|
| Team-wide process, consistent output needed | Use this skill — enforces consistent placeholders and standardised output |
| Automated pipeline (Cursor / Claude Code) | Use this skill — reproducible, auditable, JSON logs included |
| Privacy team sign-off needed | Use this skill — JSON audit logs are required evidence |

---

## Setup

Install once before running:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install presidio-analyzer presidio-anonymizer spacy
python -m spacy download en_core_web_lg
```

> Use Python 3.11+. On macOS with Apple Silicon (M1/M2/M3/M4), use Python 3.11
> via Homebrew to avoid numpy/OpenBLAS crashes with the system Python 3.9.

### Copy the script

Copy the script from this skill package into your project root:

```bash
cp scripts/anonymize.py your-project/
```

---

## How to run

### Step 0: Anonymize

```bash
python anonymize.py "01 - Input/" --output-dir "02 - Output/"
```

Check terminal output for a summary of what was replaced per file.

### Step 0b: Verify

Run the Presidio verification snippet from SKILL.md (or ask Claude to run it
via bash) to spot-check the output folder for any remaining PII.

---

## Integrate into a directives file

Add these steps at the top of your `directives.md`, before any analysis steps:

```
STEP 0:  Run python anonymize.py "01 - Input/" --output-dir "02 - Output/"
STEP 0b: Run the verification snippet from SKILL.md. Check for PASS/FAIL per file.
         Do not proceed if any file fails.
All subsequent steps must read from 02 - Output/, never from 01 - Input/
```

---

## What this skill produces

For each transcript:
- **Anonymized `.txt` file** in the output folder
- **`_pii_log.json`** — every Presidio substitution with confidence scores

These files form your audit trail for Privacy team review.

---

## Limitations

Presidio uses rule-based NLP and has known gaps — it is less reliable on
informal name references, non-Western names, and indirect identifiers. See
TRUST.md for a full breakdown and the recommended manual spot-checks that
should accompany every run.

---

## How this skill was built

This skill was developed iteratively during a real research project.

The problem: Interview transcripts contain real names, company names, emails,
and phone numbers. Before AI-assisted analysis, PII must be removed to protect
participant privacy and comply with research ethics norms.

Why consistent placeholders? `[PERSON_1]`, `[COMPANY_1]` etc. are used rather
than `[REDACTED]` so analysts can follow the narrative and distinguish between
different anonymized entities.

What was tested: The skill was validated on 6 English-language user research
transcripts. Presidio correctly returned empty PII logs on pre-anonymized
transcripts, and the verification gate passed on all sampled files.

Validation limitations: small sample, English only, structured interview
format, transcripts may have been partially pre-anonymized by the research
platform.

---

## Files in this package

```
transcript-anonymization/
├── SKILL.md          ← instructions Claude reads when the skill triggers
├── README.md         ← this file
├── TRUST.md          ← reliability details and what to verify manually
└── scripts/
    └── anonymize.py  ← Presidio-based anonymization script
```

---

## Questions and known issues

See TRUST.md for a full breakdown of what Presidio can and cannot reliably
catch, confidence levels by use case, and what to check manually before
sharing transcripts externally or seeking Privacy team approval.
