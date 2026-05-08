# Transcript Anonymization Agent

## Context

You are anonymizing raw interview transcripts before analysis begins. The transcripts are in the `02-Input/` folder (files ending in `.txt`).

---

## Your Process

Follow these steps in order. Complete ALL work for one step before starting the next.

---

### STEP 0: Anonymize Transcripts

Before any analysis begins, run PII removal across all raw transcripts.

**What you do:**
Run `anonymize.py` against the entire `02-Input/` folder:

```bash
python scripts/anonymize.py 02-Input/ --output-dir 02-Input-Anonymized/
```

**What this produces:**
- One anonymized `.txt` file per transcript in `02-Input-Anonymized/`
- One `_pii_log.json` file per transcript (records every substitution made)

**PII replaced:**
- Person names → `[PERSON_1]`, `[PERSON_2]`, ...
- Organizations / companies → `[COMPANY_1]`, `[COMPANY_2]`, ...
- Email addresses → `[EMAIL_1]`, `[EMAIL_2]`, ...
- Phone numbers → `[PHONE_1]`, `[PHONE_2]`, ...

**Rules:**
- If Presidio finds no PII in a transcript, still copy it to `02-Input-Anonymized/` unchanged so all subsequent steps read from the same folder
- Do not modify files in `02-Input/` — treat them as read-only originals
- Wait until ALL anonymized files exist in `02-Input-Anonymized/` before moving to Step 0b

**Dependencies (install once before running):**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install presidio-analyzer presidio-anonymizer spacy openai
python -m spacy download en_core_web_lg
```

---

### STEP 0b: Second-Pass Verification (Local LLM)

Run a contextual PII check using a local LLM to catch what Presidio's rule-based
approach cannot detect. Requires LM Studio to be running with a model loaded.

**What you do:**

```bash
python verify_pii.py "02-Input-Anonymized/"
```

To check all files instead of a sample:
```bash
python verify_pii.py "02-Input-Anonymized/" --all
```

**What this produces:**

- Terminal output with PASS/FAIL per file and details of any issues found
- A timestamped JSON report saved to `02-Input-Anonymized/local-llm-pii-reports/`

**How to interpret results:**

- `✅ PASS` on all sampled files → anonymization complete, transcripts are ready for analysis
- `❌ ISSUES FOUND` → stop. Review the flagged text, apply replacements manually in the
  anonymized files, then re-run Steps 0 and 0b before proceeding
- `⚠️ ERROR` → check that LM Studio is running and the server is started

**Rules:**
- Do not proceed to analysis if any file fails
- Suppressed false positives (e.g. "DuckDuckGo") are logged but do not count as failures
- Record the outcome and retain the JSON report as part of your audit trail
