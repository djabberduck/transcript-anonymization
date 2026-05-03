# Interview Analyzer Agent

## Context

You are analyzing interviews for a startup exploring the personal AI assistant market. The research brief in `02-Input/strategic-research-brief.md` defines the strategic questions. The interview transcripts are in the `02-Input/` folder (files ending in `.txt`).

The research brief organizes strategic questions into four areas:

1. **Current Behaviors** — When and how people use AI tools personally
2. **Pain Points and Failures** — Where today's tools break down
3. **Mental Models of Trust** — What makes people trust (or distrust) AI
4. **Desire and Delight** — What the ideal AI assistant would look like

**Scope note:** The transcripts include Q10-Q11 responses about the experience of being interviewed by AI. These are meta-research data about the interview method itself — not about the product being researched. Exclude them from your analysis unless they reveal something about trust or AI interaction preferences that's relevant to the strategic questions.

---

## Your Process

Follow these steps in order. Complete ALL work for one step before starting the next.

---

### STEP 0: Anonymize Transcripts

Before any analysis begins, run PII removal across all raw transcripts.

**What you do:**
Run `anonymize.py` against the entire `02-Input/` folder:

```bash
python anonymize.py 02-Input/ --output-dir 02-Input-Anonymized/
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
- All subsequent steps (1–4) read from `02-Input-Anonymized/`, not `02-Input/`
- Wait until ALL anonymized files exist in `02-Input-Anonymized/` before moving to Step 1

**Dependencies (install once before running):**
```bash
pip install presidio-analyzer presidio-anonymizer spacy --break-system-packages
python -m spacy download en_core_web_lg
```

---

### STEP 0b: Verify Anonymization

Spot-check a sample of the anonymized files before analysis begins. This step is a gate — do not proceed to Step 1 if the check fails.

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
    if results:
        print(f"FAIL: {f.name} — {len(results)} potential PII hit(s) remaining")
        for r in results:
            print(f"  [{r.entity_type}] score={r.score:.2f} → '{text[r.start:r.end]}'")
    else:
        print(f"PASS: {f.name} — no PII detected")
```

**What this produces:**

A printed verification report in the terminal. No files are written.

**How to interpret results:**

- `PASS` on all sampled files → proceed to Step 1
- `FAIL` on any file → **stop**. Do not proceed. Review the flagged hits:
  - If the hit is a false positive (e.g., a common word misidentified as a name), note it and proceed with a comment in the run log
  - If the hit is real PII that was missed, re-run `anonymize.py` on the affected file(s) and re-verify before continuing

**Rules:**
- Sample selection should be random or cover a spread of file sizes if possible — don't only check the smallest files
- A Presidio score below 0.6 is likely a false positive — use judgment, but flag it
- Do not modify files in this step — this is read-only verification only
- Record the outcome (files checked, pass/fail, any false positives noted) as a comment in your run log before moving on

---

### STEP 1: Extract by Strategic Question

Process each interview transcript from `02-Input-Anonymized/` as a separate agent — one transcript per agent. Each agent reads the research brief and one transcript, then produces one extract file.

- **What each agent receives:** One interview transcript + the research brief (`02-Input/strategic-research-brief.md`)
- **What each agent does:** Read the transcript and pull out relevant quotes and observations, organized by the four strategic question areas listed above
- **What each agent produces:** One markdown file for that interview

Save each file to `03-Extraction/` as `extract-[filename].md` (e.g., `extract-en_response_0008.md`)

**Why separate agents?** Each interview is a complete story. Keeping one agent focused on one participant preserves the connections between what they said about trust, pain points, and desires. It also means agents can run in parallel.

**Format each file like this:**

```yaml
---
interview_id: "[filename without extension, e.g., en_response_0008]"
participant_profile:
  tools_used: "[from Q1 - list primary AI tools mentioned]"
  usage_frequency: "[from Q2 - daily, weekly, occasionally, etc.]"
  trust_level: "[from Q6 - high, moderate, low, or brief description]"
  notable_context: "[any other relevant background - role, experience level, etc.]"
strategic_areas_covered:
  current_behaviors: true/false
  pain_points: true/false
  trust_models: true/false
  desire_delight: true/false
extraction_notes: "[any important context about this interview - gaps, strong themes, etc.]"
---

# Extract: [filename]

## Current Behaviors
[Direct quotes and observations relevant to how they use AI personally]

**Key patterns in this interview:**
- [Brief bullet summary of main behavioral patterns observed]

## Pain Points and Failures
[Direct quotes and observations about where tools fall short]

**Key frustrations in this interview:**
- [Brief bullet summary of main pain points mentioned]

## Mental Models of Trust
[Direct quotes and observations about trust, verification, hesitations]

**Trust stance in this interview:**
- [Brief bullet summary of their trust approach]

**How trust varies according to usage context**
- [Brief bullet summary of how their trust varies according to context]

**Factors that feed into trust**
- Brief bullet summary of what factors create or break trust

## Desire and Delight
[Direct quotes and observations about their ideal AI assistant]

**Ideal characteristics mentioned:**
- [Brief bullet summary of what they want in an AI assistant]

## Notable Moments
[Anything surprising, emotional, or unexpected that doesn't fit the categories above — e.g., strong emotional reactions, contradictions within the same interview, unprompted tangents that reveal unarticulated needs]
```

**Rules:**

- **YAML Front Matter:** Fill in all fields based on the interview content. Set boolean flags to `false` if a strategic area wasn't meaningfully addressed
- **Participant Profile:** Extract this info from the early questions (Q1, Q2, Q6) to give context for the responses
- **Quote Format:** Use the participant's exact words — do not paraphrase quotes
- Put each quote in blockquote format (>) with enough surrounding context to understand it
- Add a brief observation note after each quote explaining why it matters
- **Key Pattern Summaries:** After each major section, add a brief bullet-point summary of the main patterns you observed in that area for this participant
- If a strategic area wasn't addressed, write "Not directly addressed in this interview" and set its boolean to `false` in the front matter
- Wait until ALL extract files exist in `03-Extraction/` before moving to Step 2

---

### STEP 2: Synthesize Across Interviews

- **What you receive:** All extract files from `03-Extraction/`
- **What you do:** For each strategic question area, look across all interviews to find patterns, contradictions, and surprises
- **What you produce:** A single synthesis document

Save to `04-Synthesis/` as `synthesis.md`

**Format the synthesis like this:**

For each of the four strategic question areas, include:

1. **Key finding** (1-2 sentences stating the pattern plainly)
2. **Strength of evidence** (e.g., "5 of 6 participants described this" — use actual counts)
3. **Supporting quotes** (3-5 strongest quotes, attributed by filename)
4. **Contradictions or outliers** (who disagreed or had a different experience, and what they said)
5. **Implications for product design** (1-2 sentences connecting the finding to the startup's goals)

End with a section called **Cross-Cutting Themes** for patterns that span multiple strategic areas.

**Rules:**

- Always attribute quotes to their source file (e.g., "en_response_0032")
- Do not claim consensus when only 1-2 participants said something — be precise about counts
- Contradictions are often the most interesting findings — highlight them, don't bury them
- If a finding is based on a single participant, label it as "individual insight" not a pattern

---

### STEP 3: Verify Quotes

- **What you receive:** The synthesis from `04-Synthesis/synthesis.md` + anonymized transcripts from `02-Input-Anonymized/`
- **What you do:** Check every quote in the synthesis against the original transcript. Confirm it's accurate and not taken out of context
- **What you produce:** A verified version of the synthesis with a verification log at the end

Save to `05-Verification/` as `verified-synthesis.md`

Mark each quote with:

- ✅ **Verified** — matches transcript exactly
- ⚠️ **Corrected** — quote was inaccurate, now fixed (show what changed)
- ❌ **Removed** — quote was fabricated or badly misrepresents context (replace with a verified quote that supports the same point, or note that the finding needs weaker language)

At the end of the file, add:

```
## Verification Log
- Total quotes checked: [number]
- ✅ Verified: [number]
- ⚠️ Corrected: [number]
- ❌ Removed: [number]
```

---

### STEP 4: Final Output

- **What you receive:** The verified synthesis from `05-Verification/verified-synthesis.md`
- **What you do:**
  1. Generate a brief executive summary with top 1-2 findings per strategic area
  2. Combine executive summary + cleaned synthesis (remove verification markers)
- **What you produce:** A final analysis with executive summary at the top

Save to `06-Output/` as `interview-analysis.md`

**Executive Summary Format:**

At the very beginning of the final document, before Strategic Area 1, add:

```
# Executive Summary

**Research Question:** [One sentence describing what this research explored - from the research brief]

**Sample:** [Number] participants | [Brief description of usage patterns]

**Key Findings:**

**Current Behaviors:**
- [The single most important behavioral pattern or insight]
- [Optional: One additional critical behavioral finding if highly relevant]

**Pain Points & Failures:**
- [The single most critical failure mode, gap, or limitation]
- [Optional: One additional critical pain point if highly relevant]

**Trust Models:**
- [The single most important trust-related finding or barrier]
- [Optional: One additional trust insight if highly relevant]

**Ideal AI Assistant:**
- [The single most critical user need or design implication]
- [Optional: One additional desire/design insight if highly relevant]
```

**Rules for Executive Summary:**

- Each bullet should be one sentence maximum
- Focus on "so what" for strategic decision-making
- Include actual participant counts to show strength of evidence (e.g., "All 3 participants...")
- Prioritize findings that are actionable or challenge assumptions
- Extract research question directly from the research brief's goals

---

## Rules for All Steps

- Show your work for each step BEFORE moving to the next
- Save outputs to the appropriate folder before proceeding
- Do not skip steps. Do not combine steps
- Steps 1–4 always read from `02-Input-Anonymized/`, never from `02-Input/`
- When in doubt about a quote's meaning, include the surrounding context from the transcript
