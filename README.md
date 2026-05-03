# Transcript Anonymization Skill — README

## What this is

A reusable skill for stripping PII (personally identifiable information) from
user research interview transcripts before any analysis begins.

PII replaced: person names, company/org names, email addresses, phone numbers.
Each is replaced with a consistent, readable placeholder (`[PERSON_1]`,
`[COMPANY_1]`, `[EMAIL_1]`, `[PHONE_1]`).

This skill works in two different modes depending on how your team works.
**Read the section that applies to you before doing anything else.**

---

## ⚡ Do I even need this skill?

**Short answer:** It depends on how you're working.

| Situation | Recommendation |
|-----------|---------------|
| Quick personal check, one-off transcript | Skip the skill — just ask Claude directly (see prompt below) |
| Team-wide process, consistent output needed | Install the skill — it enforces consistent placeholders and standardised output format |
| Automated pipeline (Cursor / Claude Code) | Use Mode B (Python) — meaningfully stronger than plain Claude.ai |
| Privacy team sign-off needed | Use Mode B (Python) — JSON audit logs are required evidence |

### If you skip the skill: plain Claude.ai prompt

This prompt gives you most of the benefit without installing anything:

    Please anonymize this research transcript before analysis.
    Replace all PII with consistent placeholders:
    - Person names → [PERSON_1], [PERSON_2], etc. (same name = same tag throughout)
    - Company/org names → [COMPANY_1], [COMPANY_2], etc.
    - Email addresses → [EMAIL_1], etc.
    - Phone numbers → [PHONE_1], etc.
    After anonymizing, do a second pass and check for anything missed —
    especially first names used alone, names after "my manager/colleague",
    and indirect identifiers. Provide a substitution log at the end.

    [paste transcript here]

**What the skill adds over this prompt:**
- Consistent placeholder format enforced across everyone on the team
- Second-pass check is always included — researchers can't forget it
- Standardised audit log format for Privacy team review
- Scope is locked — Claude won't over-redact or under-redact

**What the skill does NOT add:**
- It does not make Claude more accurate — the underlying model is the same,
  and a researcher who includes a second-pass request in their own prompt
  will get identical detection quality
- It does not enable Presidio in the browser — that requires Python (Mode B)
- The "built-in second pass" is Claude re-reading its own output — it is not
  an independent check, and offers no reliability advantage over asking Claude
  to do a second pass yourself

---

## ⚡ Which setup is right for you?

| I use… | My setup is… | Go to… |
|--------|-------------|--------|
| Claude.ai in a browser, quick checks | No coding required | Mode A (below) |
| Claude Cowork desktop app | No coding required | Mode A (below) |
| Cursor, terminal, or Claude Code | Comfortable with Python | Mode B (below) |
| Need Privacy team sign-off | Python required | Mode B (below) |

---

## Mode A: Claude.ai Chat / Cowork (no coding)

This is the right mode for most researchers on the team.

### How it works

Claude reads the SKILL.md instructions and performs the anonymization itself
using its language understanding — no Python, no terminal, no installation
required. This makes it better at catching contextual PII (e.g., "my manager
Dave", indirect identifiers) but produces output that varies slightly between
sessions, so it is less suitable as a formal audit trail on its own.

### How to enable the skill

1. In Claude.ai, go to Settings → Customize → Skills
2. Find transcript-anonymization and toggle it on
3. If you don't see it, ask your team admin — it may need to be shared with
   you first

### How to use it

Start a new chat and paste your transcript text with a prompt like:

    I need to anonymize this research transcript before analysis.
    Please remove all PII and replace with consistent placeholders.

    [paste transcript text here]

Or trigger it explicitly:

    Use the transcript anonymization skill on this transcript.

Claude will:
1. Identify all PII in the text
2. Replace each instance with a consistent placeholder
3. Return the anonymized transcript
4. Provide a summary log of what was replaced
5. Do a second-pass check to catch anything missed in the first pass

### What to do with the output

- Copy the anonymized text into a new file
- Save the substitution log separately as your audit record
- Do a quick manual check before sharing outside your team
  (see TRUST.md for what to look for)

### Mode A limitations

- Output varies slightly between sessions (Claude is not deterministic)
- No JSON audit log file is produced automatically — copy the log from chat
- Transcripts are sent to Anthropic's API for processing
- Not suitable as the sole evidence for formal Privacy team approval —
  combine with manual spot-check (see TRUST.md)

---

## Mode B: Python Pipeline (Cursor / Terminal)

This is the right mode if you are running an automated analysis pipeline
(e.g., using a directives.md file in Cursor or Claude Code) and need a
reproducible, auditable process with JSON logs.

### How it works

Two Python scripts run locally on your machine:
- anonymize.py — uses Microsoft Presidio (rule-based) to detect and replace PII
No transcript data is stored outside your machine.

### Prerequisites

- Python 3.11+ (on macOS, use Homebrew — avoid system Python 3.9 on Apple Silicon)

### One-time setup

    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install presidio-analyzer presidio-anonymizer spacy anthropic
    python -m spacy download en_core_web_lg

### Copy the scripts

Copy both scripts from this skill package into your project root:

    cp scripts/anonymize.py your-project/
    
### Run

    # Step 0: Anonymize
    python anonymize.py "01 - Input/" --output-dir "02 - Output/"

    # Step 0b: Check terminal output for PASS/FAIL per file

### Integrate into a directives file

Add these steps at the top of your directives.md, before any analysis steps:

    STEP 0: Run python anonymize.py "01 - Input/" --output-dir "02 - Output/"
    STEP 0b: Check terminal output for PASS/FAIL per file
    All subsequent steps read from 02 - Output/, never from 01 - Input/

### What Mode B produces

For each transcript:
- Anonymized .txt file in the output folder
- _pii_log.json — every Presidio substitution with confidence scores

These files form your audit trail for Privacy team review.

### Mode B limitations

- Requires Python setup (one-time effort)
- Presidio misses contextual and indirect PII — see TRUST.md for details
- See TRUST.md for full breakdown of what each tool can and cannot detect

---

## How this skill was built

This skill was developed iteratively during a real research project.

The problem: Interview transcripts contain real names, company names, emails,
and phone numbers. Before AI-assisted analysis, PII must be removed to protect
participant privacy and comply with research ethics norms.

Why two detection methods? No single tool catches everything. Presidio
(rule-based) is strong on structured PII like emails, phones, and formal names.
Claude (LLM-based) is stronger on contextual PII like casual name references
and indirect identifiers. Running both in sequence covers each tool's blind spots.

Why consistent placeholders? [PERSON_1], [COMPANY_1] etc. are used rather than
[REDACTED] so analysts can follow the narrative and distinguish between different
anonymized entities.

What was tested: The skill was validated on 6 English-language user research
transcripts. Presidio correctly returned empty PII logs on pre-anonymized
transcripts, and the verification gate passed on all sampled files.

Validation limitations: small sample, English only, structured interview format,
transcripts may have been partially pre-anonymized by the research platform.

---

## Files in this package

    transcript-anonymization/
    ├── SKILL.md          ← instructions Claude reads when the skill triggers
    ├── README.md         ← this file
    ├── TRUST.md          ← reliability details and what to verify manually
    └── scripts/
        ├── anonymize.py  ← Presidio-based anonymization script (Mode B only)

---

## Questions and known issues

See TRUST.md for a full breakdown of what each detection method can and cannot
reliably catch, confidence levels by use case, and what to check manually before
sharing transcripts externally or seeking Privacy team approval.
