---
name: transcript-anonymization
description: >
  Use this skill to anonymize PII (personally identifiable information) from
  user research interview transcripts before analysis begins. Triggers whenever
  a researcher mentions anonymizing transcripts, stripping PII, protecting
  participant identity, preparing transcripts for analysis, or running
  anonymization before qualitative coding. Also use when a directives file
  or research pipeline includes a Step 0 or pre-processing phase involving
  transcript files. Works with .txt files. Uses Microsoft Presidio locally —
  no data leaves the machine.
---

# Transcript Anonymization Skill

This skill prepares raw interview transcripts for safe analysis by detecting
and replacing PII before any human or AI reads the content. It runs in two
phases: anonymization (Step 0) and verification (Step 0b).

---

## What this skill does

**Step 0 — Anonymize**
Runs Microsoft Presidio across all `.txt` transcripts in an input folder.
Replaces PII with consistent, readable placeholders and writes anonymized
copies to a separate output folder. Raw originals are never modified.

**Step 0b — Verify**
Spot-checks a sample of the anonymized files by re-running Presidio's
analyzer (read-only) to confirm no PII remains. Acts as a gate: analysis
must not proceed if verification fails.

---

## PII entities detected and replaced

| Entity type      | Placeholder format          |
|------------------|-----------------------------|
| Person names     | `[PERSON_1]`, `[PERSON_2]`  |
| Organizations    | `[COMPANY_1]`, `[COMPANY_2]`|
| Email addresses  | `[EMAIL_1]`, `[EMAIL_2]`    |
| Phone numbers    | `[PHONE_1]`, `[PHONE_2]`    |

Placeholders are **consistent within each transcript** — the same name always
gets the same tag throughout a file.

---

## Dependencies

Install once before running:

```bash
pip install presidio-analyzer presidio-anonymizer spacy
python -m spacy download en_core_web_lg
```

> If `pip` is not found, use `pip3`. If you are on macOS with Apple Silicon
> (M1/M2/M3/M4), use Python 3.11 via Homebrew to avoid numpy/OpenBLAS crashes
> with the system Python 3.9.

---

## Required file: anonymize.py

This skill requires `anonymize.py` to be present in the project root.
The script is included in this skill package as `scripts/anonymize.py`.
Copy it to your project root before running.

---

## Step 0: Anonymize transcripts

### What to run

```bash
python anonymize.py <input-folder>/ --output-dir <output-folder>/
```

**Example:**
```bash
python anonymize.py "02 - Input/" --output-dir "02-Input-Anonymized/"
```

### What it produces

For each `.txt` transcript in the input folder:
- `<filename>.txt` — anonymized copy in the output folder
- `<filename>_pii_log.json` — log of every substitution made

### Rules

- If Presidio finds no PII, the file is still copied to the output folder
  unchanged — so all downstream steps read from the same location
- Do **not** modify files in the input folder — treat them as read-only originals
- All subsequent analysis steps must read from the output folder, never the input
- Wait until ALL files are present in the output folder before running Step 0b

---

## Step 0b: Verify anonymization

### What to run

Run this Python snippet from your project root (or ask Claude to run it):

```python
from presidio_analyzer import AnalyzerEngine
from pathlib import Path

analyzer = AnalyzerEngine()
ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ORGANIZATION"]
sample_dir = Path("02-Input-Anonymized/")  # update path if different

files = sorted(f for f in sample_dir.glob("*.txt") if "_pii_log" not in f.name)
sample = files[:3]  # spot-check 3 files; check all if fewer than 3

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

### How to interpret results

| Result | Action |
|--------|--------|
| PASS on all sampled files | Proceed to analysis |
| FAIL — hit score < 0.6 | Likely false positive. Note it, proceed with caution |
| FAIL — hit score ≥ 0.6 | Real PII missed. Re-run `anonymize.py` on that file, then re-verify |

### Rules

- Sample should cover a spread of file sizes — don't only check the smallest
- Score threshold of 0.6 filters likely false positives (common words misread
  as names). Use judgment for borderline cases
- This step is **read-only** — do not modify any files here
- Record outcome in your run log before proceeding to analysis

---

## Folder structure this skill expects

```
your-project/
├── anonymize.py              ← copy from scripts/anonymize.py
├── 02 - Input/               ← raw transcripts (read-only)
│   ├── transcript-p01.txt
│   └── ...
└── 02-Input-Anonymized/      ← created by Step 0
    ├── transcript-p01.txt
    ├── transcript-p01_pii_log.json
    └── ...
```

Folder names with spaces are supported — use quotes in all bash commands.

---

---

## Step 0c: Second-pass verification using Claude API

This step sends each anonymized transcript to Claude to catch contextual and
indirect PII that Presidio's rule-based approach cannot detect.

### What to run

```bash
pip install anthropic   # one-time install
python verify_pii.py <anonymized-folder>/
```

**Example:**
```bash
python verify_pii.py "02-Input-Anonymized/"
```

**To check all files (not just a sample):**
```bash
python verify_pii.py "02-Input-Anonymized/" --all
```

### What it checks for

Beyond Presidio's structural detection, Claude looks for:
- **First names used alone** — "I asked Sarah to review it"
- **Names after relationship words** — "my manager Dave", "my colleague Tom"
- **Names in possessives** — "John's team", "Maria's approach"
- **Indirect identifiers** — role + location + industry combinations that
  could re-identify a participant even without a name
- **Unique references** — "after my TEDx talk", internal project codenames
- **Named third parties** — colleagues, clients, or competitors mentioned
  in passing that Presidio missed

### What it produces

- Terminal output with PASS/FAIL per file and details of any issues found
- A timestamped JSON report saved to `<folder>/claude-pii-reports/`

### How to interpret results

| Result | Action |
|--------|--------|
| ✅ All files PASS | Proceed to analysis |
| ❌ Issues found | Review flagged text. Apply suggested replacements manually, then re-run |
| ⚠️ API error | Check your `ANTHROPIC_API_KEY` environment variable is set |

### Prerequisites

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here   # or set in your .env
```

### Rules

- This step checks a sample of 3 files by default. Use `--all` for full
  coverage before sharing transcripts externally
- If issues are found, fix them manually in the anonymized files and re-run
  Steps 0b and 0c before proceeding
- The JSON report should be saved alongside your PII logs as part of your
  audit trail for Privacy team review

---

## Notes for Claude Cowork users

This skill runs Python scripts via bash. In Cowork:
- Ask Claude to run `anonymize.py` using the bash tool
- Ask Claude to run the Step 0b verification snippet using the bash tool
- Claude cannot access files outside its working directory — ensure transcripts
  are uploaded or accessible before starting
- See `TRUST.md` for known limitations before using outputs in sensitive research
