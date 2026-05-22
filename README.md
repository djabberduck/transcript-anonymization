# Transcript Anonymization Skill — README

## What this is

A reusable skill for stripping PII (personally identifiable information) from
user research interview transcripts before any analysis begins.

PII replaced: person names, company/org names, email addresses, phone numbers,
locations. Each is replaced with a consistent, readable placeholder
(`[PERSON_1]`, `[COMPANY_1]`, `[EMAIL_1]`, `[PHONE_1]`, `[LOCATION_1]`).

All processing runs locally. No transcript data is sent to any external service
or LLM.

---

## When to use this skill

| Situation | Recommendation |
|-----------|---------------|
| Team-wide process, consistent output needed | Use this skill — enforces consistent placeholders and standardised output |
| Automated pipeline (Cursor / Claude Code) | Use this skill — reproducible, auditable, JSON logs included |
| Privacy team sign-off needed | Use this skill — JSON audit logs from both steps are required evidence |

---

## How it works

Two tools run in sequence, covering each other's blind spots:

- **Presidio** (Step 0) — rule-based, fast, deterministic. Strong on structured
  PII: emails, phone numbers, locations, formal names, large company names.
- **Local LLM via LM Studio** (Step 0b) — contextual, catches what Presidio
  misses: informal name references, indirect identifiers, non-Western names.

Neither tool sends data off your machine.

---

## Setup

### Python environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install presidio-analyzer presidio-anonymizer spacy openai
python -m spacy download en_core_web_lg
```

> Use Python 3.11+. On macOS with Apple Silicon (M1/M2/M3/M4), use Python 3.11
> via Homebrew to avoid numpy/OpenBLAS crashes with the system Python 3.9.

### LM Studio (for Step 0b)

1. Download and install LM Studio
2. In the Discover tab, download `Qwen2.5-32B-Instruct-GGUF` (Q4_K_M, ~20GB)
3. In the Developer tab, load the model and click Start Server
4. Keep the server running while running the pipeline

### Copy the scripts

Copy both scripts from this skill package into your project root:

```bash
cp scripts/anonymize.py your-project/
cp scripts/verify_pii.py your-project/
```

---

## How to run

### Step 0: Anonymize

```bash
python anonymize.py "02 - Input/" --output-dir "02-Input-Anonymized/"
```

This produces for each transcript:
- An anonymized `.txt` file
- A `_pii_log.json` recording every substitution made
- A `_suppressed_log.json` recording detections intentionally skipped as false
  positives — review this to confirm no real participant names were suppressed

### Step 0b: Local LLM verification

```bash
python verify_pii.py "02-Input-Anonymized/"
```

Use `--all` to check every file instead of a 3-file sample (recommended before
sharing transcripts externally).

Long transcripts are automatically split into overlapping chunks so the full
transcript is covered regardless of length. Use `--chunk-size` to adjust the
chunk size if needed:

```bash
python verify_pii.py "02-Input-Anonymized/" --all --chunk-size 20000
```

---

## Integrate into a directives file

Add these steps at the top of your `directives.md`, before any analysis steps:

```
STEP 0:  Run python anonymize.py "02 - Input/" --output-dir "02-Input-Anonymized/"
         Review _suppressed_log.json for any real names incorrectly suppressed.
STEP 0b: Run python verify_pii.py "02-Input-Anonymized/" --all
         Do not proceed if any file fails or has unresolved errors.
All subsequent steps must read from 02-Input-Anonymized/, never from 02 - Input/
```

---

## What this skill produces

For each transcript:
- **Anonymized `.txt` file** in the output folder
- **`_pii_log_{timestamp}.json`** — every Presidio substitution with confidence scores
- **`_suppressed_log_{timestamp}.json`** — every detection suppressed as a false
  positive, with entity type, score, and reason

For the verification pass:
- **`local-llm-pii-reports/local_llm_pii_check_{timestamp}.json`** — LLM
  verification report including per-chunk results for long transcripts

These files form your audit trail for Privacy team review.

---

## Limitations

- Presidio is less reliable on informal name references, non-Western names,
  and indirect identifiers — this is what Step 0b is designed to catch
- The `FALSE_POSITIVE_NAMES` suppression list in `anonymize.py` may silence
  a real participant name that happens to match a product name (e.g. "Mac",
  "Mint"). Review `_suppressed_log.json` after each run
- The local LLM (Qwen2.5-32B) performs well on explicit and contextual PII
  but quasi-identifier detection (indirect re-identification risk) is
  prompt-sensitive and not infallible — manual spot-checks remain necessary
- See TRUST.md for a full breakdown and recommended manual spot-checks

---

## Changelog

### v2 (current)
- `anonymize.py`: Added `LOCATION` entity type; explicit `MIN_SCORE` threshold;
  suppressed detections now written to `_suppressed_log.json` for audit
- `verify_pii.py`: Replaced hard 30k char truncation with overlapping chunking
  (28k chunk / 2k overlap) for full transcript coverage; raised `max_tokens`
  from 1000 to 2500; restructured system prompt for local model compatibility;
  added `temperature=0.1` for consistent Qwen output; `--chunk-size` CLI flag

### v1
- Initial release with Presidio + local LLM two-pass pipeline

---

## How this skill was built

This skill was developed iteratively during a real research project.

The problem: Interview transcripts contain real names, company names, emails,
and phone numbers. Before AI-assisted analysis, PII must be removed to protect
participant privacy and comply with research ethics norms.

Why two detection methods? No single tool catches everything. Presidio
(rule-based) is strong on structured PII like emails, phones, and formal names.
The local LLM is stronger on contextual PII like casual name references and
indirect identifiers. Running both in sequence covers each tool's blind spots.

Why consistent placeholders? `[PERSON_1]`, `[COMPANY_1]` etc. are used rather
than `[REDACTED]` so analysts can follow the narrative and distinguish between
different anonymized entities.

What was tested: The skill was validated on 6 English-language user research
transcripts. Presidio correctly returned empty PII logs on pre-anonymized
transcripts, and the LLM verification passed on all sampled files.

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
    ├── anonymize.py  ← Presidio-based anonymization script
    └── verify_pii.py ← local LLM second-pass verification script
```

---

## Questions and known issues

See TRUST.md for a full breakdown of what each detection method can and cannot
reliably catch, confidence levels by use case, and what to check manually before
sharing transcripts externally or seeking Privacy team approval.
