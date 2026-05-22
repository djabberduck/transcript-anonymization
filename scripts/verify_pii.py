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

Changes from v1:
- Transcripts longer than CHUNK_SIZE are split into overlapping chunks and
  each chunk is checked independently. Results are merged. This fixes the
  hard 30k char truncation that silently left the second half of most
  hour-long transcripts unchecked.
- max_tokens raised from 1000 to 2500 to reduce truncated JSON responses
  when many issues are found in a single chunk.
- System prompt restructured for local model compatibility: each check type
  is a numbered, explicit instruction rather than a prose description.
  Quasi-identifier detection is called out as a distinct reasoning task.
- parse_error responses now include the raw model output for diagnosis.
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

# Chunk size in characters. Transcripts longer than this are split into
# overlapping chunks to ensure full coverage.
# ~30k chars ≈ 20–25 minutes of interview at typical transcription density.
# Overlap ensures names or quasi-identifiers that span a chunk boundary
# are not missed.
CHUNK_SIZE = 28000
CHUNK_OVERLAP = 2000  # characters of overlap between consecutive chunks

# Max tokens for model response. Raised from 1000 to reduce truncated JSON
# when a chunk contains many issues. 2500 supports ~15–20 detailed issues.
MAX_TOKENS = 2500

# Text values that the LLM may flag but should be suppressed as known
# false positives in DuckDuckGo research transcripts.
# Matching is case-insensitive and exact on the flagged text field.
SUPPRESSED_TEXTS = {
    "duckduckgo",
    "duck duck go",
    "ddg",
}

# System prompt restructured for local model compatibility.
# Explicit numbered instructions work better than prose for instruction-following
# models. Quasi-identifier detection is broken out as a distinct reasoning task
# with concrete examples.
SYSTEM_PROMPT = """You are a privacy auditor. Your task is to find PII remaining in an anonymized research transcript.

Presidio has already replaced common PII with placeholders like [PERSON_1], [COMPANY_1], [EMAIL_1], [PHONE_1], [LOCATION_1].

You must check for FOUR categories of remaining PII:

CATEGORY 1 — DIRECT PII (real text that should have been replaced):
- Person names: first names, last names, full names, nicknames, handles
- Organization names or employer names
- Email addresses or phone numbers
- Physical addresses, postcodes, city+street combinations
- Social media handles, usernames, profile URLs

CATEGORY 2 — NAMES PRESIDIO COMMONLY MISSES:
- First names used alone: "I asked Sarah to..." or "then Dave said..."
- Names after relationship words: "my manager Tom", "my colleague Lisa", "our CEO Mark"
- Names in possessives: "John's team", "Maria's feedback", "Sarah's project"
- Nicknames or shortened names not caught by NER

CATEGORY 3 — NAMED THIRD PARTIES:
- Colleagues, clients, competitors, or public figures mentioned by name in passing
- Examples: "I spoke to Jennifer at [COMPANY_1]", "similar to what Elon Musk did"

CATEGORY 4 — INDIRECT IDENTIFIERS (combinations that could re-identify a participant):
This requires reasoning, not just pattern matching. Ask yourself: could a determined person identify who said this, even without a name?
- Role + company size + location combinations: "the only female VP of Engineering at a Series B fintech in Austin"
- Unique career events: "after my TEDx talk", "when I sold my startup in 2019"
- Rare role descriptions: "I run the only pediatric oncology unit in rural Montana"
- Internal project codenames or product names unique to one company
- Any combination of 3+ attributes (role, location, industry, team size, event) that narrows to a single person

RULES:
- Only flag text that is actually present and problematic. Do not flag placeholders like [PERSON_1].
- For Category 4, only flag combinations that are genuinely re-identifying, not generic descriptions.
- Be precise: quote the exact text that is the problem.

OUTPUT FORMAT:
Respond ONLY with valid JSON. No preamble, no explanation outside the JSON, no markdown fences.

If no issues found:
{"status": "clean", "issues": [], "summary": "No PII detected."}

If issues found:
{
  "status": "issues_found",
  "issues": [
    {
      "text": "exact problematic text quoted from the transcript",
      "type": "direct|indirect",
      "category": "person_name|organization|location|indirect_identifier|third_party_name|other",
      "risk": "one sentence explaining the risk",
      "suggestion": "suggested replacement text"
    }
  ],
  "summary": "One or two sentence plain-English summary of what was found"
}"""


# --- Chunking ----------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """
    Split text into overlapping chunks for sequential LLM processing.
    Returns list of dicts with 'text', 'start', 'end', 'chunk_index'.

    Overlap ensures PII near chunk boundaries is not missed. Duplicate
    issues found in the overlap region are deduplicated after merging.
    """
    if len(text) <= chunk_size:
        return [{"text": text, "start": 0, "end": len(text), "chunk_index": 0}]

    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append({
            "text": text[start:end],
            "start": start,
            "end": end,
            "chunk_index": idx,
        })
        if end == len(text):
            break
        start += chunk_size - overlap
        idx += 1

    return chunks


def deduplicate_issues(issues: list[dict]) -> list[dict]:
    """
    Remove duplicate issues that appear in overlapping chunk regions.
    Deduplicates on exact 'text' value, keeping first occurrence.
    """
    seen = set()
    deduped = []
    for issue in issues:
        key = issue.get("text", "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(issue)
    return deduped


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


def check_chunk(client: OpenAI, model: str, chunk_text: str, filename: str, chunk_index: int, total_chunks: int) -> dict:
    """
    Send a single chunk to the local LLM for PII checking.
    Returns parsed JSON response dict.
    """
    chunk_note = f" [chunk {chunk_index + 1}/{total_chunks}]" if total_chunks > 1 else ""
    user_message = (
        f"Audit this anonymized transcript{chunk_note} for remaining PII. "
        f"Follow all four categories in your instructions.\n\n---\n{chunk_text}\n---"
    )

    raw = ""
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=0.1,  # low temperature for consistent, literal output
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
        result["chunk_index"] = chunk_index
        return result

    except json.JSONDecodeError as e:
        return {
            "chunk_index": chunk_index,
            "status": "parse_error",
            "issues": [],
            "summary": f"Could not parse model response: {e}",
            "raw_response": raw[:500] if raw else "No response",
        }
    except Exception as e:
        return {
            "chunk_index": chunk_index,
            "status": "api_error",
            "issues": [],
            "summary": f"Error: {e}",
        }


def check_transcript(client: OpenAI, model: str, text: str, filename: str) -> dict:
    """
    Check a full transcript for PII, chunking if necessary.
    Merges results across all chunks and deduplicates.
    Returns a single result dict compatible with the original format.
    """
    chunks = chunk_text(text)
    total_chunks = len(chunks)

    if total_chunks > 1:
        print(f"     Transcript length: {len(text):,} chars — splitting into {total_chunks} overlapping chunks")

    all_issues = []
    all_suppressed = []
    chunk_errors = []
    chunk_results = []

    for chunk in chunks:
        if total_chunks > 1:
            print(f"     Checking chunk {chunk['chunk_index'] + 1}/{total_chunks} "
                  f"(chars {chunk['start']:,}–{chunk['end']:,})...")

        chunk_result = check_chunk(client, model, chunk["text"], filename, chunk["chunk_index"], total_chunks)
        chunk_results.append(chunk_result)

        status = chunk_result.get("status", "unknown")

        if status in ("parse_error", "api_error"):
            chunk_errors.append(chunk_result)
        elif status in ("clean", "issues_found"):
            issues = chunk_result.get("issues", [])
            kept, suppressed = filter_false_positives(issues)
            all_issues.extend(kept)
            all_suppressed.extend(suppressed)

        if chunk["chunk_index"] < total_chunks - 1:
            time.sleep(0.3)

    # Deduplicate across overlapping regions
    all_issues = deduplicate_issues(all_issues)
    all_suppressed = deduplicate_issues(all_suppressed)

    # Build merged result
    if chunk_errors and not all_issues:
        # All errors, no usable output
        status = "api_error" if any(c["status"] == "api_error" for c in chunk_errors) else "parse_error"
        summary = f"{len(chunk_errors)} chunk(s) failed to process. " + chunk_errors[0].get("summary", "")
    elif all_issues:
        status = "issues_found"
        summary = f"{len(all_issues)} issue(s) found across {total_chunks} chunk(s)."
        if chunk_errors:
            summary += f" Note: {len(chunk_errors)} chunk(s) had errors and may not have been fully checked."
    else:
        status = "clean"
        summary = f"No PII detected across {total_chunks} chunk(s)."
        if all_suppressed:
            summary += f" ({len(all_suppressed)} known false positive(s) suppressed.)"
        if chunk_errors:
            summary = f"Errors in {len(chunk_errors)} chunk(s) — coverage may be incomplete."
            status = "parse_error"

    return {
        "filename": filename,
        "status": status,
        "issues": all_issues,
        "suppressed": all_suppressed,
        "summary": summary,
        "chunks_total": total_chunks,
        "chunks_errored": len(chunk_errors),
        "char_length": len(text),
        "chunk_details": chunk_results if total_chunks > 1 else [],
    }


def print_result(result: dict):
    """Print a single file's result to terminal."""
    status = result.get("status", "unknown")
    filename = result.get("filename", "unknown")
    suppressed = result.get("suppressed", [])
    chunks_total = result.get("chunks_total", 1)
    chunks_errored = result.get("chunks_errored", 0)
    char_length = result.get("char_length", 0)

    chunk_note = f" [{chunks_total} chunk(s), {char_length:,} chars]" if chunks_total > 1 else f" [{char_length:,} chars]"
    error_note = f" ⚠️ {chunks_errored} chunk(s) had errors" if chunks_errored else ""

    if status == "clean":
        print(f"  ✅ PASS: {filename}{chunk_note}{error_note}")
        print(f"     {result.get('summary', '')}")
        if suppressed:
            print(f"     Suppressed false positives: {[s.get('text') for s in suppressed]}")

    elif status == "issues_found":
        issues = result.get("issues", [])
        print(f"  ❌ ISSUES FOUND: {filename}{chunk_note}{error_note} — {len(issues)} issue(s)")
        print(f"     Summary: {result.get('summary', '')}")
        for i, issue in enumerate(issues, 1):
            print(f"     Issue {i}: [{issue.get('type','?').upper()}] {issue.get('category','?')}")
            print(f"       Text:       \"{issue.get('text', '')}\"")
            print(f"       Risk:       {issue.get('risk', '')}")
            print(f"       Suggestion: {issue.get('suggestion', '')}")
        if suppressed:
            print(f"     Suppressed false positives: {[s.get('text') for s in suppressed]}")

    elif status in ("parse_error", "api_error"):
        print(f"  ⚠️  ERROR: {filename}{chunk_note} — {result.get('summary', '')}")

    else:
        print(f"  ?: {filename} — unknown status: {status}")


def process_folder(folder: Path, output_dir: Path, server_url: str, check_all: bool = False):
    """
    Run second-pass PII check on anonymized transcripts in a folder.
    """
    files = sorted(
        f for f in folder.glob("*.txt")
        if "_pii_log" not in f.name and "_suppressed_log" not in f.name
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
    print(f"   Folder:     {folder}")
    print(f"   Files:      {total} total, checking {checking}")
    print(f"   Mode:       {'all files' if check_all else f'sample of {checking}'}")
    print(f"   Server:     {server_url}")
    print(f"   Model:      {model}")
    print(f"   Chunk size: {CHUNK_SIZE:,} chars with {CHUNK_OVERLAP:,} char overlap")
    print(f"   Max tokens: {MAX_TOKENS}")
    print()

    results = []
    issues_count = 0
    clean_count = 0
    error_count = 0

    for i, f in enumerate(sample, 1):
        print(f"[{i}/{checking}] Checking: {f.name}")
        text = f.read_text(encoding="utf-8")
        result = check_transcript(client, model, text, f.name)
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
        "folder_checked": str(folder),
        "total_files": total,
        "files_checked": checking,
        "mode": "all" if check_all else "sample",
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "max_tokens": MAX_TOKENS,
        "summary": {
            "clean": clean_count,
            "issues_found": issues_count,
            "errors": error_count,
        },
        "results": results,
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
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help=f"Characters per chunk (default: {CHUNK_SIZE}). Reduce if model context is limited."
    )

    args = parser.parse_args()

    if not args.folder.exists():
        print(f"ERROR: Folder not found: {args.folder}")
        sys.exit(1)

    # Allow CLI override of chunk size
    global CHUNK_SIZE
    CHUNK_SIZE = args.chunk_size

    output_dir = args.output_dir or (args.folder / "local-llm-pii-reports")
    passed = process_folder(args.folder, output_dir, args.url, check_all=args.all)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
