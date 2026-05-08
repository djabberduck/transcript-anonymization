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
  no data leaves the machine. Does not use any external LLM on transcript data.
---

# Transcript Anonymization Skill

This skill prepares raw interview transcripts for safe analysis by detecting
and replacing PII before any human or AI reads the content. It runs in two
phases: Presidio anonymization (Step 0) and local LLM verification (Step 0b).
All processing is local — no transcript data is sent to any external service.

---

## Python pipeline (local machine or Cowork)

Runs Microsoft Presidio locally for anonymization, then a local LLM via
LM Studio for contextual verification. No data leaves the machine.

### Dependencies

Install once before running:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install presidio-analyzer presidio-anonymizer spacy openai
python -m spacy download en_core_web_lg
```

> Use Python 3.11+. On macOS with Apple Silicon (M1/M2/M3/M4), use Python 3.11
> via Homebrew to avoid numpy/OpenBLAS crashes with the system Python 3.9.

### Required files

Copy both scripts from this skill package into your project root:

```bash
cp scripts/anonymize.py your-project/
cp scripts/verify_pii.py your-project/
```

### LM Studio setup (for Step 0b)

1. Download and install LM Studio
2. In the Discover tab, download `Qwen2.5-32B-Instruct-GGUF` (Q4_K_M, ~20GB)
3. In the Developer tab, load the model and click Start Server
4. Keep the server running while running the pipeline

---

### Step 0: Anonymize transcripts

```bash
python anonymize.py <input-folder>/ --output-dir <output-folder>/
```

**Example:**
```bash
python anonymize.py "02 - Input/" --output-dir "02-Input-Anonymized/"
```

**What it produces**

For each `.txt` transcript in the input folder:
- `<filename>.txt` — anonymized copy in the output folder
- `<filename>_pii_log.json` — log of every substitution made

**Rules**

- If Presidio finds no PII, the file is still copied to the output folder
  unchanged — so all downstream steps read from the same location
- Do not modify files in the input folder — treat them as read-only originals
- All subsequent analysis steps must read from the output folder, never the input
- Wait until ALL files are present in the output folder before running Step 0b

---

### Step 0b: Second-pass verification (local LLM)

Checks anonymized transcripts for contextual and indirect PII that Presidio's
rule-based approach cannot detect. Runs entirely locally via LM Studio.

```bash
python verify_pii.py "02-Input-Anonymized/"
```

**To check all files (not just a sample):**
```bash
python verify_pii.py "02-Input-Anonymized/" --all
```

**What it checks for**

Beyond Presidio's structural detection, the local LLM looks for:
- First names used alone — "I asked Sarah to review it"
- Names after relationship words — "my manager Dave", "my colleague Tom"
- Names in possessives — "John's team", "Maria's approach"
- Indirect identifiers — role + location + industry combinations
- Unique references — "after my TEDx talk", internal project codenames
- Named third parties — colleagues, clients, or competitors mentioned in passing

**How to interpret results**

| Result | Action |
|--------|--------|
| ✅ All files PASS | Proceed to analysis |
| ❌ Issues found | Review flagged text. Apply replacements manually, then re-run Steps 0 and 0b |
| ⚠️ Error | Check LM Studio server is running |

**Rules**

- Checks a sample of 3 files by default. Use `--all` for full coverage before
  sharing transcripts externally
- JSON reports are saved to `02-Input-Anonymized/local-llm-pii-reports/`
- If issues are found, fix them manually in the anonymized files and re-run
  both steps before proceeding

---

## Folder structure

```
your-project/
├── anonymize.py              ← copy from scripts/anonymize.py
├── verify_pii.py             ← copy from scripts/verify_pii.py
├── 02 - Input/               ← raw transcripts (read-only)
│   ├── transcript-p01.txt
│   └── ...
└── 02-Input-Anonymized/      ← created by Step 0
    ├── transcript-p01.txt
    ├── transcript-p01_pii_log.json
    └── local-llm-pii-reports/
        └── local_llm_pii_check_<timestamp>.json
```

Folder names with spaces are supported — use quotes in all bash commands.
