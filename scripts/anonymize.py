"""
Transcript Anonymizer
---------------------
Uses Microsoft Presidio to detect and replace PII in .txt transcript files.
Configured via directives.md. Run directly or invoked by Cursor AI.

PII replaced: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, ORGANIZATION, LOCATION

Changes from v1:
- Added LOCATION to detected entity types
- False positive suppression now logs suppressed hits (suppressed: true in PII log)
  so you have an audit trail of what was intentionally skipped
- Score threshold made explicit (MIN_SCORE = 0.4) and consistent with verify step
- Suppressed hits written to a separate _suppressed_log for review
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


# --- Configuration -----------------------------------------------------------

ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ORGANIZATION", "LOCATION"]

# Minimum confidence score — results below this are discarded
# Set to 0.4 to match the spirit of the original (catch more, let verify_pii.py
# act as the quality gate). Raise to 0.6 if false positives are a problem.
MIN_SCORE = 0.4

# Maps each entity type to a readable placeholder prefix
PLACEHOLDER_MAP = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "ORGANIZATION": "COMPANY",
    "LOCATION": "LOCATION",
}

# Regex patterns that should never be tagged as PII regardless of Presidio's verdict
# Covers: HH:MM:SS and HH:MM timestamps common in interview transcripts
FALSE_POSITIVE_PATTERNS = [
    re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$"),  # timestamps: 00:05:40, 1:23, 01:23:45
    re.compile(
        r"^\d{1,2}:\d{2}(:\d{2})?\s*-\s*\d{1,2}:\d{2}(:\d{2})?$"
    ),  # ranges: 00:00:14 - 00:00:19
]

# Well-known product/brand names Presidio misidentifies as PERSON.
# IMPORTANT: Any participant whose first name matches an entry here will be
# silently suppressed by Presidio. Review this list carefully before each study.
# Suppressed hits are now logged to _suppressed_log.json for audit purposes.
FALSE_POSITIVE_NAMES = {
    "gmail", "youtube", "google", "safari", "chrome", "firefox",
    "netflix", "spotify", "slack", "notion", "figma", "zoom",
    "instagram", "facebook", "twitter", "tiktok", "linkedin",
    "mac", "linux", "mint", "bing", "mhmm", "claude", "gorgias",
    "roku", "pocket",
}


def is_false_positive(text: str, entity_type: str) -> bool:
    """Return True if this detection is a known false positive to suppress."""
    if entity_type == "PERSON":
        # Suppress timestamp patterns
        for pattern in FALSE_POSITIVE_PATTERNS:
            if pattern.match(text.strip()):
                return True
        # Suppress well-known product names
        if text.strip().lower() in FALSE_POSITIVE_NAMES:
            return True
    return False


def read_transcript_text(path: Path) -> str:
    """Read a transcript: UTF-8 first, then MacRoman / ISO-8859-1 fallbacks."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    for encoding in ("mac_roman", "iso-8859-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# --- Core logic --------------------------------------------------------------

def build_engines():
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


def anonymize_text(text: str, analyzer: AnalyzerEngine, anonymizer: AnonymizerEngine):
    """
    Analyze text for PII and replace with consistent placeholders.
    Returns (anonymized_text, pii_log, suppressed_log).

    pii_log      — list of replacements actually made
    suppressed_log — list of detections that were suppressed as false positives
                     (included for audit trail; these were NOT replaced)
    """
    results = analyzer.analyze(text=text, entities=ENTITIES, language="en")

    # Apply minimum score threshold
    results = [r for r in results if r.score >= MIN_SCORE]

    # Separate genuine detections from known false positives
    kept_results = []
    suppressed_log = []

    for r in results:
        span_text = text[r.start:r.end]
        if is_false_positive(span_text, r.entity_type):
            suppressed_log.append({
                "original": span_text,
                "type": r.entity_type,
                "score": round(r.score, 2),
                "reason": (
                    "timestamp_pattern"
                    if any(p.match(span_text.strip()) for p in FALSE_POSITIVE_PATTERNS)
                    else "false_positive_names_list"
                ),
                "suppressed": True,
            })
        else:
            kept_results.append(r)

    # Sort by position for consistent label assignment
    results_sorted = sorted(kept_results, key=lambda r: r.start)

    # Assign consistent placeholder labels per unique original value
    label_counters = {v: 0 for v in PLACEHOLDER_MAP.values()}
    value_to_label = {}
    pii_log = []

    for result in results_sorted:
        original = text[result.start:result.end]
        key = original.lower().strip()

        if key not in value_to_label:
            prefix = PLACEHOLDER_MAP.get(result.entity_type, result.entity_type)
            label_counters[prefix] += 1
            label = f"[{prefix}_{label_counters[prefix]}]"
            value_to_label[key] = label
            pii_log.append({
                "original": original,
                "replacement": label,
                "type": result.entity_type,
                "score": round(result.score, 2),
            })

    # Rebuild text with replacements applied in reverse order to preserve offsets
    anonymized_text = text
    for result in sorted(results_sorted, key=lambda r: r.start, reverse=True):
        original = text[result.start:result.end]
        key = original.lower().strip()
        label = value_to_label.get(key, f"[{result.entity_type}]")
        anonymized_text = anonymized_text[:result.start] + label + anonymized_text[result.end:]

    # Spread logged replacements globally to catch fragmented repeats Presidio missed
    anonymized_text = apply_logged_string_replacements(anonymized_text, pii_log)

    return anonymized_text, pii_log, suppressed_log


def apply_logged_string_replacements(text: str, pii_log: list[dict]) -> str:
    """Replace any remaining occurrences of each logged original with its placeholder."""
    entries = sorted(pii_log, key=lambda item: len(item["original"]), reverse=True)
    out = text
    for item in entries:
        original = item["original"]
        label = item["replacement"]
        if not original.strip():
            continue
        pat = re.compile(re.escape(original), re.IGNORECASE)
        out = pat.sub(label, out)
    return out


def process_file(input_path: Path, output_dir: Path, log: bool = True):
    """
    Anonymize a single .txt file. Writes anonymized output, PII log, and suppressed log.
    """
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    if input_path.suffix.lower() != ".txt":
        print(f"ERROR: Only .txt files are supported. Got: {input_path.suffix}")
        sys.exit(1)

    text = read_transcript_text(input_path)

    print(f"Analyzing: {input_path.name} ({len(text)} chars)")

    analyzer, anonymizer = build_engines()
    anonymized_text, pii_log, suppressed_log = anonymize_text(text, analyzer, anonymizer)

    # Write anonymized output
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    out_file = output_dir / f"{stem}_anonymized_{timestamp}.txt"
    out_file.write_text(anonymized_text, encoding="utf-8")
    print(f"Anonymized file written:   {out_file}")

    if log:
        # Write PII replacement log
        if pii_log:
            log_file = output_dir / f"{stem}_pii_log_{timestamp}.json"
            log_file.write_text(
                json.dumps(pii_log, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"PII log written:           {log_file}")

        # Write suppressed detections log (always write so absence is explicit)
        suppressed_file = output_dir / f"{stem}_suppressed_log_{timestamp}.json"
        suppressed_file.write_text(
            json.dumps(suppressed_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if suppressed_log:
            print(f"Suppressed detections log: {suppressed_file}")
            print(f"  ⚠️  {len(suppressed_log)} detection(s) were suppressed as false positives.")
            print(f"  Review the suppressed log to confirm none are real participant names.")
        else:
            print(f"Suppressed detections log: {suppressed_file} (empty — nothing suppressed)")

    # Summary
    print(f"\nSummary: {len(pii_log)} unique PII items replaced, {len(suppressed_log)} suppressed")
    for item in pii_log:
        print(f"  {item['original']!r:30s} → {item['replacement']} ({item['type']}, score: {item['score']})")
    if suppressed_log:
        print(f"\nSuppressed (not replaced):")
        for item in suppressed_log:
            print(f"  {item['original']!r:30s}   ({item['type']}, score: {item['score']}, reason: {item['reason']})")

    return out_file, pii_log, suppressed_log


def process_directory(input_dir: Path, output_dir: Path, log: bool = True):
    """
    Anonymize all .txt files in a directory.
    """
    txt_files = sorted(
        f
        for f in input_dir.glob("*.txt")
        if not f.name.startswith("~$")
    )
    if not txt_files:
        print(f"No .txt files found in {input_dir}")
        return

    print(f"Found {len(txt_files)} .txt file(s) in {input_dir}\n")
    for f in txt_files:
        process_file(f, output_dir, log=log)
        print()


# --- CLI entry point ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Anonymize PII from .txt transcript files using Microsoft Presidio."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to a .txt file or a directory of .txt files.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory (default: same as input, subfolder 'anonymized/').",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Skip writing the JSON PII log file.",
    )

    args = parser.parse_args()

    output_dir = args.output_dir or (
        args.input.parent / "anonymized"
        if args.input.is_file()
        else args.input / "anonymized"
    )

    if args.input.is_dir():
        process_directory(args.input, output_dir, log=not args.no_log)
    else:
        process_file(args.input, output_dir, log=not args.no_log)


if __name__ == "__main__":
    main()
