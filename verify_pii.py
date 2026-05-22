"""
Second-Pass PII Verifier
------------------------
Uses a local LLM via LM Studio to check anonymized transcripts for PII that
Presidio may have missed. Focuses on contextual and indirect PII that
rule-based tools cannot detect.

No data leaves the machine — all inference runs locally via LM Studio.

Produces a JSON report per transcript and a summary report across all files.

Usage:
    python verify_pii.py <anonymized-folder>/
    python verify_pii.py <anonymized-folder>/ --output-dir <report-folder>/
    python verify_pii.py <anonymized-folder>/ --all   # check all files, not just sample
    python verify_pii.py <anonymized-folder>/ --url http://localhost:1234  # custom server URL
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not found. Install it with:")
    print("  pip install openai")
    sys.exit(1)


# --- Configuration -----------------------------------------------------------

# How many files to sample by default (use --all to check every file)
DEFAULT_SAMPLE_SIZE = 3

# LM Studio local server URL
DEFAULT_LM_STUDIO_URL = "http://localhost:1234"

# Default max chars of transcript body per request. LM Studio often uses
# n_ctx=4096; system prompt + this slice + max_tokens must fit — raise with
# --max-chars if your loaded model has a larger context.
DEFAULT_MAX_CHARS = 4500

# Text values that the LLM may flag but should be suppressed as known
# false positives in DuckDuckGo research transcripts.
# Matching is case-insensitive and exact on the flagged text field.
SUPPRESSED_TEXTS = {
    "duckduckgo",
    "duck duck go",
    "ddg",
}

SYSTEM_PROMPT = """You are a privacy auditor reviewing anonymized user research transcripts.

Presidio (a rule-based PII detector) has already made one pass and replaced
common PII with placeholders like [PERSON_1], [COMPANY_1], [EMAIL_1], [PHONE_1].

Your job is to find anything Presidio may have missed. You are specifically
looking for:

1. DIRECT PII (still present as real text, not yet replaced):
   - Person names (first names, last names, full names, nicknames)
   - Company or organization names
   - Email addresses or phone numbers
   - Physical addresses, postcodes, or specific locations tied to a person
   - Social media handles or usernames
   - URLs that identify a person or organization

2. INDIRECT / CONTEXTUAL PII (combinations that could re-identify someone):
   - Role + location + industry combinations (e.g., "the only female VP of
     Engineering at a Series B fintech in Austin")
   - References to unique events tied to a person (e.g., "after my TEDx talk")
   - Named colleagues, clients, or competitors mentioned in passing
   - Internal project names or product codenames unique to a company

3. STRUCTURAL PATTERNS Presidio misses:
   - First names used alone without a surname ("I asked Sarah to...")
   - Names following relationship words ("my manager Dave", "my colleague Tom")
   - Names in possessives ("John's team", "Maria's approach")

For each issue found, provide:
- The exact text that is problematic (quote it)
- The type of PII risk (direct or indirect)
- Why it is a risk
- A suggested replacement

Respond ONLY with valid JSON. No preamble, no markdown fences.

If no issues are found, respond with:
{"status": "clean", "issues": [], "summary": "No PII detected."}

If issues are found, respond with:
{
  "status": "issues_found",
  "issues": [
    {
      "text": "exact problematic text",
      "type": "direct|indirect",
      "category": "person_name|organization|location|indirect_identifier|other",
      "risk": "brief explanation of the risk",
      "suggestion": "suggested replacement or action"
    }
  ],
  "summary": "Brief plain-English summary of what was found"
}"""


# --- Core logic --------------------------------------------------------------

def get_loaded_model(client: OpenAI) -> str:
    """Fetch the first available model from the LM Studio server."""
    try:
        models = client.models.list()
        if models.data:
            return models.data[0].id
        else:
            print("ERROR: No models loaded in LM Studio. Load a model and start the server.")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Could not connect to LM Studio server: {e}")
        print("Make sure LM Studio is running and the server is started.")
        sys.exit(1)


def filter_false_positives(issues: list) -> tuple:
    """
    Remove known false positives from the LLM's flagged issues.
    Returns (kept_issues, suppressed_issues).
    """
    kept = []
    suppressed = []
    for issue in issues:
        text = issue.get("text", "").strip().lower()
        if text in SUPPRESSED_TEXTS:
            suppressed.append(issue)
        else:
            kept.append(issue)
    return kept, suppressed


def check_transcript(
    client: OpenAI, model: str, text: str, filename: str, max_chars: int
) -> dict:
    """
    Send a transcript to the local LLM for second-pass PII checking.
    Returns parsed JSON response.
    """
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    user_message = f"Please audit this anonymized transcript for any remaining PII:\n\n---\n{text}\n---"

    raw = ""
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)

        # Apply false positive suppression
        original_issues = result.get("issues", [])
        kept, suppressed = filter_false_positives(original_issues)
        result["issues"] = kept
        result["suppressed"] = suppressed
        if suppressed and not kept:
            result["status"] = "clean"
            result["summary"] = f"No PII detected. ({len(suppressed)} known false positive(s) suppressed.)"

        result["filename"] = filename
        result["truncated"] = truncated
        result["max_chars_used"] = max_chars
        return result

    except json.JSONDecodeError as e:
        return {
            "filename": filename,
            "status": "parse_error",
            "issues": [],
            "summary": f"Could not parse model response: {e}",
            "truncated": truncated,
            "max_chars_used": max_chars,
            "raw_response": raw or "No response"
        }
    except Exception as e:
        return {
            "filename": filename,
            "status": "api_error",
            "issues": [],
            "summary": f"Error: {e}",
            "truncated": truncated,
            "max_chars_used": max_chars,
        }


def print_result(result: dict):
    """Print a single file's result to terminal."""
    status = result.get("status", "unknown")
    filename = result.get("filename", "unknown")
    truncated = result.get("truncated", False)
    suppressed = result.get("suppressed", [])
    mc = result.get("max_chars_used", DEFAULT_MAX_CHARS)
    trunc_note = f" [TRUNCATED — only first ~{mc} chars checked]" if truncated else ""

    if status == "clean":
        print(f"  ✅ PASS: {filename}{trunc_note}")
        print(f"     {result.get('summary', '')}")
        if suppressed:
            print(f"     Suppressed false positives: {[s.get('text') for s in suppressed]}")

    elif status == "issues_found":
        issues = result.get("issues", [])
        print(f"  ❌ ISSUES FOUND: {filename}{trunc_note} — {len(issues)} issue(s)")
        print(f"     Summary: {result.get('summary', '')}")
        for i, issue in enumerate(issues, 1):
            print(f"     Issue {i}: [{issue.get('type','?').upper()}] {issue.get('category','?')}")
            print(f"       Text:       \"{issue.get('text', '')}\"")
            print(f"       Risk:       {issue.get('risk', '')}")
            print(f"       Suggestion: {issue.get('suggestion', '')}")
        if suppressed:
            print(f"     Suppressed false positives: {[s.get('text') for s in suppressed]}")

    elif status in ("parse_error", "api_error"):
        print(f"  ⚠️  ERROR: {filename} — {result.get('summary', '')}")

    else:
        print(f"  ?: {filename} — unknown status: {status}")


def process_folder(
    folder: Path,
    output_dir: Path,
    server_url: str,
    check_all: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
):
    """
    Run second-pass PII check on anonymized transcripts in a folder.
    """
    files = sorted(
        f for f in folder.glob("*.txt")
        if "_pii_log" not in f.name
    )

    if not files:
        print(f"No .txt transcript files found in {folder}")
        sys.exit(1)

    sample = files if check_all else files[:DEFAULT_SAMPLE_SIZE]
    total = len(files)
    checking = len(sample)

    client = OpenAI(base_url=f"{server_url}/v1", api_key="local")
    model = get_loaded_model(client)

    print(f"\n── Second-Pass PII Verification (Local LLM) ──────────────────────")
    print(f"   Folder:   {folder}")
    print(f"   Files:    {total} total, checking {checking}")
    print(f"   Mode:     {'all files' if check_all else f'sample of {checking}'}")
    print(f"   Server:   {server_url}")
    print(f"   Model:    {model}")
    print(f"   Max chars per request: {max_chars}")
    print()

    results = []
    issues_count = 0
    clean_count = 0
    error_count = 0

    for i, f in enumerate(sample, 1):
        print(f"[{i}/{checking}] Checking: {f.name}")
        text = f.read_text(encoding="utf-8")
        result = check_transcript(client, model, text, f.name, max_chars)
        results.append(result)
        print_result(result)
        print()

        if result["status"] == "clean":
            clean_count += 1
        elif result["status"] == "issues_found":
            issues_count += 1
        else:
            error_count += 1

        if i < checking:
            time.sleep(0.5)

    # Summary
    print(f"── Summary ────────────────────────────────────────────────────────")
    print(f"   Files checked: {checking} of {total}")
    print(f"   ✅ Clean:       {clean_count}")
    print(f"   ❌ Issues:      {issues_count}")
    print(f"   ⚠️  Errors:      {error_count}")

    if issues_count > 0:
        print(f"\n   ⛔ ACTION REQUIRED: {issues_count} file(s) have remaining PII.")
        print(f"   Review the issues above and re-anonymize before proceeding.")
    elif error_count > 0:
        print(f"\n   ⚠️  Some files could not be checked. Review errors above.")
    else:
        print(f"\n   ✅ All checked files passed. Safe to proceed to analysis.")

    if not check_all and total > DEFAULT_SAMPLE_SIZE:
        print(f"\n   ℹ️  Note: Only {checking} of {total} files were checked (sample mode).")
        print(f"   Run with --all to check every file.")

    # Write report
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"local_llm_pii_check_{timestamp}.json"

    report = {
        "run_at": datetime.now().isoformat(),
        "model": model,
        "server": server_url,
        "max_chars_per_request": max_chars,
        "folder_checked": str(folder),
        "total_files": total,
        "files_checked": checking,
        "mode": "all" if check_all else "sample",
        "summary": {
            "clean": clean_count,
            "issues_found": issues_count,
            "errors": error_count
        },
        "results": results
    }

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n   Report saved: {report_path}")

    return issues_count == 0 and error_count == 0


# --- CLI entry point ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Second-pass PII check using a local LLM via LM Studio."
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Path to folder containing anonymized .txt transcripts."
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Where to save the JSON report (default: <folder>/local-llm-pii-reports/)."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all files instead of a sample."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_LM_STUDIO_URL,
        help=f"LM Studio server URL (default: {DEFAULT_LM_STUDIO_URL})."
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        metavar="N",
        help=(
            "Max transcript characters to send per file (default: %(default)s, "
            "safe for n_ctx≈4096). Increase if your model context is larger."
        ),
    )

    args = parser.parse_args()

    if not args.folder.exists():
        print(f"ERROR: Folder not found: {args.folder}")
        sys.exit(1)

    output_dir = args.output_dir or (args.folder / "local-llm-pii-reports")
    passed = process_folder(
        args.folder,
        output_dir,
        args.url,
        check_all=args.all,
        max_chars=args.max_chars,
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
