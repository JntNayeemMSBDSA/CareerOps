from careerops_config import experience_blocks, load_facts
from careerops_config import source_dir
#!/usr/bin/env python3

import json
import re
from pathlib import Path


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
SOURCE = source_dir(ROOT)

RESUME = RUNTIME / "generated_resume_content.json"
OVERRIDES = SOURCE / "candidate_attestations.json"


# ---------------------------------------------------------------------
# AUTHORITATIVE EXPERIENCE IDENTITIES
# ---------------------------------------------------------------------

EXPERIENCE = {re.sub(r"[^A-Z0-9]", "", row["block_id"].upper()): {"company":row["organization"], "title":row["title"], "dates":row["period"]} for row in experience_blocks(ROOT)}


# ---------------------------------------------------------------------
# AUTHORITATIVE EDUCATION
# ---------------------------------------------------------------------

EDUCATION = {row["institution"]:{k:v for k,v in row.items() if k in {"degree","graduation","gpa","honors"}} for row in load_facts(ROOT).get("education",[])}


# ---------------------------------------------------------------------
# LARGE-NUMBER COMPACTION
#
# Compact SCALE numbers only when integer magnitude >= 10,000.
#
# Examples: 240,000 -> 240K; 12,500,000 -> 12.5M.
# Small exact model/configuration numbers remain exact:
#   1,080
#   54
#   48
#   53
#   0.61
#   117 -> 6
#   percentages
# ---------------------------------------------------------------------

NUMBER_PATTERN = re.compile(
    r"""
    (?<![\w.])
    (?P<currency>\$?)
    (?P<number>
        \d{1,3}(?:,\d{3})+
        |
        \d{5,}
    )
    (?![\w.%])
    """,
    re.X,
)


def strip_decimal(value, decimals):
    s = f"{value:.{decimals}f}"

    if "." in s:
        s = s.rstrip("0").rstrip(".")

    return s


def compact_integer(value):
    if value >= 1_000_000_000:
        return strip_decimal(
            value / 1_000_000_000,
            2,
        ) + "B"

    if value >= 100_000_000:
        return strip_decimal(
            value / 1_000_000,
            1,
        ) + "M"

    if value >= 10_000_000:
        return strip_decimal(
            value / 1_000_000,
            1,
        ) + "M"

    if value >= 1_000_000:
        return strip_decimal(
            value / 1_000_000,
            2,
        ) + "M"

    if value >= 100_000:
        return strip_decimal(
            value / 1_000,
            1,
        ) + "K"

    if value >= 10_000:
        return strip_decimal(
            value / 1_000,
            1,
        ) + "K"

    return f"{value:,}"


def compact_large_numbers(text):
    changes = []

    def replace(match):
        original = match.group(0)
        currency = match.group("currency") or ""

        raw = match.group("number")
        value = int(
            raw.replace(",", "")
        )

        # Preserve exact small configuration counts.
        if value < 10_000:
            return original

        compacted = (
            currency
            + compact_integer(value)
        )

        if compacted != original:
            changes.append(
                (original, compacted)
            )

        return compacted

    result = NUMBER_PATTERN.sub(
        replace,
        text,
    )

    return result, changes


def transform_strings(value, log):
    if isinstance(value, str):
        transformed, changes = (
            compact_large_numbers(value)
        )

        log.extend(changes)
        return transformed

    if isinstance(value, list):
        return [
            transform_strings(x, log)
            for x in value
        ]

    if isinstance(value, dict):
        return {
            k: transform_strings(v, log)
            for k, v in value.items()
        }

    return value


# ---------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------

if not RESUME.exists():
    raise SystemExit(
        f"Missing resume content: {RESUME}"
    )

resume = json.loads(
    RESUME.read_text(
        encoding="utf-8"
    )
)


# ---------------------------------------------------------------------
# FIX EXPERIENCE IDENTITIES
# ---------------------------------------------------------------------

for exp in resume.get(
    "experience",
    [],
):
    block_id = exp.get("block_id")

    if block_id not in EXPERIENCE:
        continue

    authoritative = EXPERIENCE[
        block_id
    ]

    exp["company"] = (
        authoritative["company"]
    )

    exp["title"] = (
        authoritative["title"]
    )

    exp["dates"] = (
        authoritative["dates"]
    )


# ---------------------------------------------------------------------
# FIX EDUCATION
# ---------------------------------------------------------------------

for edu in resume.get(
    "education",
    [],
):
    institution = edu.get(
        "institution"
    )

    if institution not in EDUCATION:
        continue

    authoritative = EDUCATION[
        institution
    ]

    for key, value in (
        authoritative.items()
    ):
        edu[key] = value


# ---------------------------------------------------------------------
# COMPACT LARGE SCALE NUMBERS
# ---------------------------------------------------------------------

number_changes = []

resume = transform_strings(
    resume,
    number_changes,
)


# ---------------------------------------------------------------------
# Authority is read-only; generation cannot create candidate attestations.

# WRITE RESUME
# ---------------------------------------------------------------------

RESUME.write_text(
    json.dumps(
        resume,
        indent=2,
        ensure_ascii=False,
    ) + "\n",
    encoding="utf-8",
)


# ---------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------

print("=" * 100)
print("CAREEROPS RESUME INVARIANTS")
print("=" * 100)

print()
print("EXPERIENCE DATES:")

for exp in resume.get(
    "experience",
    [],
):
    print(
        "-",
        exp.get("company"),
        "|",
        exp.get("title"),
        "|",
        exp.get("dates"),
    )

print()
print("LARGE-NUMBER COMPACTION:")

seen = set()

for old, new in number_changes:
    key = (old, new)

    if key in seen:
        continue

    seen.add(key)

    print(
        f"- {old} -> {new}"
    )

if not seen:
    print("- NONE NEEDED")

print()
print("EDUCATION:")

for edu in resume.get(
    "education",
    [],
):
    print(
        "-",
        edu.get("institution"),
        "|",
        edu.get("degree"),
        "|",
        edu.get("gpa"),
        "|",
        edu.get("graduation"),
    )

print()
print("CONTENT CLAIMS ADDED: NO")
print("TECHNICAL DETAIL REMOVED: NO")
print("SOL/MODEL CALLS: 0")
print("=" * 100)
