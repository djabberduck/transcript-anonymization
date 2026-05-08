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

### STEP 0b: Verify Anonymization (Presidio)

Spot-check a sample of the anonymized files before finishing. This step is a gate — report failure clearly if the check does not pass.

**What you do:**

1. Count the total number of `.txt` files in `02-Input-Anonymized/`
2. Select a sample: 3 files, or all files if there are fewer than 3
3. For each sampled file, run Presidio's analyzer directly (no replacement) to scan for any remaining PII:

```python
from presidio_analyzer import AnalyzerEngine
from pathlib import Path

analyzer = AnalyzerEngine()
ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ORGANIZATION"]
sample_dir = Path("02-Input-Anonymized/")

files = sorted(f for f in sample_dir.glob("*.txt") if "_pii_log" not in f.name)
sample = files[:3]

for f in sample:
    text = f.read_text(encoding="utf-8")
    results = analyzer.analyze(text=text, entities=ENTITIES, language="en")
    hits = [r for r in results if r.score >= 0.6]
    if hits:
        print(f"FAIL: {f.name} — {len(hits)} potential PII hit(s) remaining")
        for r in hits:
            print(f"  [{r.entity_type}] score={r.score:.2f} → '{text[r.start:r.end]}'")
    else:
        print(f"PASS: {f.name} — no PII detected above threshold")
```

**What this produces:**

A printed verification report in the terminal. No files are written.

**How to interpret results:**

- `PASS` on all sampled files → proceed to Step 0c
- `FAIL` on any file → stop. Review the flagged hits:
  - If the hit is a false positive (score below 0.6 or a common word misidentified as a name), note it and proceed with a comment
  - If the hit is real PII that was missed, re-run `anonymize.py` on the affected file(s) and re-verify before continuing

**Rules:**
- Sample selection should cover a spread of file sizes — don't only check the smallest files
- A Presidio score below 0.6 is likely a false positive — use judgment, but flag it
- Do not modify files in this step — this is read-only verification only
- Report the outcome clearly: files checked, pass/fail status, any false positives noted

---

### STEP 0c: Second-Pass Verification (Local LLM)

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
  anonymized files, then re-run Steps 0b and 0c before proceeding
- `⚠️ ERROR` → check that LM Studio is running and the server is started

**Rules:**
- Do not proceed to analysis if any file fails
- Suppressed false positives (e.g. "DuckDuckGo") are logged but do not count as failures
- Record the outcome and retain the JSON report as part of your audit trail
