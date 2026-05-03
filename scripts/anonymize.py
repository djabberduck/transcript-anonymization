"""
Transcript Anonymizer
---------------------
Uses Microsoft Presidio to detect and replace PII in .txt transcript files.
Configured via directives.md. Run directly or invoked by Cursor AI.

PII replaced: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, ORGANIZATION
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

ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ORGANIZATION"]

# Maps each entity type to a readable placeholder prefix
PLACEHOLDER_MAP = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "ORGANIZATION": "COMPANY",
}

# Regex patterns that should never be tagged as PII regardless of Presidio's verdict
# Covers: HH:MM:SS and HH:MM timestamps common in interview transcripts
FALSE_POSITIVE_PATTERNS = [
    re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$"),  # timestamps: 00:05:40, 1:23, 01:23:45
]

# Well-known product/brand names Presidio misidentifies as PERSON
FALSE_POSITIVE_NAMES = {
    "gmail", "youtube", "google", "safari", "chrome", "firefox",
    "netflix", "spotify", "slack", "notion", "figma", "zoom",
    "instagram", "facebook", "twitter", "tiktok", "linkedin",
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


# --- Core logic --------------------------------------------------------------

def build_engines():
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


def anonymize_text(text: str, analyzer: AnalyzerEngine, anonymizer: AnonymizerEngine):
    """
    Analyze text for PII and replace with consistent placeholders.
    Returns (anonymized_text, pii_log) where pii_log is a list of dicts.
    """
    results = analyzer.analyze(text=text, entities=ENTITIES, language="en")

    # Filter out known false positives (timestamps, product names)
    results = [
        r for r in results
        if not is_false_positive(text[r.start:r.end], r.entity_type)
    ]

    # Sort by position so we can build a replacement map with consistent labels
    results_sorted = sorted(results, key=lambda r: r.start)

    # Assign consistent placeholder labels per unique original value
    label_counters = {k: 0 for k in PLACEHOLDER_MAP.values()}
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

    # Build operator config: replace each entity with its consistent placeholder
    # We do a manual pass to ensure consistency across repeated values
    operators = {
        entity: OperatorConfig("replace", {"new_value": "<TEMP>"})
        for entity in ENTITIES
    }

    # Use Presidio anonymizer for the replacement pass, then fix up labels
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators,
    )
    anonymized_text = anonymized.text

    # Replace <TEMP> placeholders won't work for consistency — do it ourselves
    # by rebuilding from scratch using sorted results (reverse order to preserve offsets)
    anonymized_text = text
    for result in sorted(results_sorted, key=lambda r: r.start, reverse=True):
        original = text[result.start:result.end]
        key = original.lower().strip()
        label = value_to_label.get(key, f"[{result.entity_type}]")
        anonymized_text = anonymized_text[:result.start] + label + anonymized_text[result.end:]

    return anonymized_text, pii_log


def process_file(input_path: Path, output_dir: Path, log: bool = True):
    """
    Anonymize a single .txt file. Writes anonymized output and optional JSON log.
    """
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    if input_path.suffix.lower() != ".txt":
        print(f"ERROR: Only .txt files are supported. Got: {input_path.suffix}")
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")

    print(f"Analyzing: {input_path.name} ({len(text)} chars)")

    analyzer, anonymizer = build_engines()
    anonymized_text, pii_log = anonymize_text(text, analyzer, anonymizer)

    # Write anonymized output
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    out_file = output_dir / f"{stem}_anonymized_{timestamp}.txt"
    out_file.write_text(anonymized_text, encoding="utf-8")
    print(f"Anonymized file written: {out_file}")

    # Write PII log
    if log and pii_log:
        log_file = output_dir / f"{stem}_pii_log_{timestamp}.json"
        log_file.write_text(
            json.dumps(pii_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"PII log written:        {log_file}")

    # Summary
    print(f"\nSummary: {len(pii_log)} unique PII items replaced")
    for item in pii_log:
        print(f"  {item['original']!r:30s} → {item['replacement']} ({item['type']}, score: {item['score']})")

    return out_file, pii_log


def process_directory(input_dir: Path, output_dir: Path, log: bool = True):
    """
    Anonymize all .txt files in a directory.
    """
    txt_files = list(input_dir.glob("*.txt"))
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
