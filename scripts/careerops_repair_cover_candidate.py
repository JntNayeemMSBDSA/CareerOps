#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path

from careerops_cover_gate_v2 import (
    INTEREST_SIGNAL_GROUPS,
    interest_signals,
    normalize,
)


ALLOWED_REPAIRS = {
    "paragraph1_specific_hook",
    "paragraph3_names_company",
    "specific_interest",
    "no_paragraph3_keyword_stack",
    "semantic_resume_complementarity",
    "no_ai_pattern_language",
    "jd_terms_present",
    "body_word_count",
}


def acronym_from_company(company):
    m = re.search(r"\(([A-Z][A-Z0-9&.-]{1,15})\)\s*$", company or "")
    return m.group(1) if m else None


REASONING_MARKERS = (
    "because",
    "rather than",
    "instead of",
    "to preserve",
    "to ensure",
    "so that",
)

def sentence_chunks(text):
    """
    Split prose sentences without treating initials such as
    "A. B." or "U.S." as sentence boundaries.
    """
    raw = str(text or "").strip()

    if not raw:
        return []

    token = "__CAREEROPS_PROTECTED_DOT__"

    # Protect single-letter initials before another capitalized token.
    # Covers Example abbreviation, U.S. Bank, J. P. Morgan, etc.
    protected = re.sub(
        r"\b([A-Z])\.(?=\s+[A-Z])",
        rf"\1{token}",
        raw,
    )

    # Protect common personal-title abbreviations.
    protected = re.sub(
        r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr)\.",
        rf"\1{token}",
        protected,
        flags=re.I,
    )

    chunks = [
        x.strip().replace(token, ".")
        for x in re.split(
            r"(?<=[.!?])\s+",
            protected,
        )
        if x.strip()
    ]

    return chunks


def has_reasoning(sentence):
    low = normalize(sentence)

    return any(
        marker in low
        for marker in REASONING_MARKERS
    )


def split_keyword_stack_sentence(sentence):
    """
    Split only a Cover Gate-identified keyword-stack sentence.

    CAREEROPS_KEYWORD_STACK_SPLIT_V2
    PHASE11_LOW_OVERHEAD_KEYWORD_SPLIT_V1
    LI6_REASONING_SETUP_PRESERVATION_V1

    The transformation preserves existing action/setup language
    instead of deleting grammar-bearing text such as
    "bring the same reasoning to".

    It adds no candidate fact, metric, employer, tool, outcome,
    history, or requirement.
    """

    sentence = str(
        sentence
        or ""
    ).strip()

    if not sentence:
        return sentence

    def join_items(items):
        items = [
            str(x).strip()
            for x in items
            if str(x).strip()
        ]

        if len(items) == 1:
            return items[0]

        if len(items) == 2:
            return (
                items[0]
                + " and "
                + items[1]
            )

        return (
            ", ".join(
                items[:-1]
            )
            + ", and "
            + items[-1]
        )

    def split_at_company(text):
        text = str(
            text
            or ""
        ).strip()

        m = re.match(
            r"^(At\s+.+?,)\s+I would\s+(.+?)[.!?]?$",
            text,
            flags=re.I,
        )

        if not m:
            return text, False

        location_prefix = (
            m.group(1)
            .strip()
        )

        body = (
            m.group(2)
            .strip()
        )

        # Preserve grammar-bearing setup language.
        setup = ""

        reasoning = re.match(
            (
                r"^("
                r"(?:apply|use|extend|bring)\s+"
                r"(?:that|the same)\s+reasoning\s+to\s+"
                r")"
                r"(.+)$"
            ),
            body,
            flags=re.I,
        )

        if reasoning:
            setup = (
                reasoning.group(1)
                .strip()
                + " "
            )

            action_text = (
                reasoning.group(2)
                .strip()
            )

        else:
            action_text = body

        parts = [
            part.strip()
            for part
            in re.split(
                r",\s*(?:and\s+)?",
                action_text,
            )
            if part.strip()
        ]

        if len(parts) < 3:
            return text, False

        split_at = (
            2
            if len(parts) >= 4
            else 1
        )

        first = parts[
            :split_at
        ]

        second = parts[
            split_at:
        ]

        first_sentence = (
            location_prefix
            + " I would "
            + setup
            + join_items(first)
            + "."
        )

        second_sentence = (
            "I would "
            + setup
            + join_items(second)
            + "."
        )

        return (
            first_sentence
            + " "
            + second_sentence,
            True,
        )

    # ---------------------------------------------------------
    # Colon-nested shape.
    #
    # Repair the comma-heavy head during THIS invocation rather
    # than merely exposing it for a later repair pass.
    # ---------------------------------------------------------

    if ":" in sentence:
        head, tail = sentence.split(
            ":",
            1,
        )

        head = head.strip()
        tail = tail.strip()

        if (
            head
            and tail
        ):
            repaired_head, _ = split_at_company(
                head
            )

            if re.match(
                r"^I would\b",
                tail,
                flags=re.I,
            ):
                tail_sentence = tail
            else:
                tail_sentence = (
                    "I would "
                    + tail[0].lower()
                    + tail[1:]
                )

            if tail_sentence[-1] not in ".!?":
                tail_sentence += "."

            return (
                repaired_head.rstrip()
                + " "
                + tail_sentence
            )

    repaired, changed = split_at_company(
        sentence
    )

    if changed:
        return repaired

    return sentence


def build_interest_sentence(plan, company):
    """
    Build a concise employer-specific interest sentence using
    ONLY semantic interest groups already authorized by the
    deterministic cover plan.

    The phrases come from the same vocabulary Cover Gate V2
    uses to evaluate specific_interest.
    """

    reason = (
        plan.get("interest_reason", {})
        .get("reason", "")
    )

    groups = interest_signals(reason)

    if not groups:
        interest_reason = (
            plan.get("interest_reason", {}) or {}
        )
        target_requirements = (
            plan.get("target_role_application", {})
            .get("target_requirements", [])
            or []
        )

        jd_specific = (
            str(
                interest_reason.get("source", "")
            ).strip().upper()
            == "TARGET_JD"
            and str(
                interest_reason.get("confidence", "")
            ).strip().upper()
            == "JD_SPECIFIC"
            and bool(str(reason or "").strip())
            and bool(target_requirements)
        )

        if jd_specific:
            return (
                f"That work at {company} "
                "specifically interests me."
            )

        return None

    phrases = []

    for group in groups[:2]:
        variants = list(
            INTEREST_SIGNAL_GROUPS.get(
                group,
                []
            )
        )

        if not variants:
            continue

        # Prefer the shortest canonical phrase in the gate's
        # own semantic-equivalence group.
        phrase = min(
            variants,
            key=lambda x: (
                len(str(x).split()),
                len(str(x)),
            ),
        )

        phrases.append(
            str(phrase).strip()
        )

    if not phrases:
        return None

    if len(phrases) == 1:
        focus = phrases[0]
    else:
        focus = (
            phrases[0]
            + " and "
            + phrases[1]
        )

    return (
        f"The focus on {focus} at {company} "
        "specifically interests me."
    )


def normalize_repairer_interest_grammar(p3, company):
    """
    Clean the first-version deterministic repair construction:

        At COMPANY, X is the work I want to pursue.

    This only rewrites a sentence created by this repairer.
    It does not alter candidate evidence or introduce facts.
    """

    pattern = re.compile(
        rf"At {re.escape(company)}, "
        r"(.+?) is the work I want to pursue\.",
        flags=re.I,
    )

    def repl(match):
        focus = match.group(1).strip()

        return (
            f"The focus on {focus} at {company} "
            "specifically interests me."
        )

    return pattern.sub(
        repl,
        p3,
        count=1,
    )


def replace_interest_sentence(p3, replacement):
    """
    Replace an existing weak/general interest sentence when
    possible. Otherwise insert the deterministic interest
    sentence before the required final thank-you sentence.
    """

    chunks = sentence_chunks(p3)

    if not chunks:
        return p3

    interest_markers = (
        "want to pursue",
        "want to advance",
        "want to take on",
        "specific work",
        "interested in",
        "interests me",
        "draws me",

        # Generic writer phrasing that functions as an interest
        # sentence should be replaced, not followed by another
        # deterministic interest sentence.
        "especially concrete",
    )

    for sentence in chunks:
        low = normalize(sentence)

        if any(
            marker in low
            for marker in interest_markers
        ):
            return p3.replace(
                sentence,
                replacement,
                1,
            )

    final_sentence = (
        "Thank you for your consideration."
    )

    if final_sentence in p3:
        return p3.replace(
            final_sentence,
            replacement
            + " "
            + final_sentence,
            1,
        )

    return (
        p3.rstrip()
        + " "
        + replacement
    )


def repair_semantic_overlap(paragraphs, report):
    """
    Repair only sentences Cover Gate V2 itself identified as
    resume-like.

    The repair does not paraphrase facts or invent reasoning.
    It joins the flagged sentence to an immediately adjacent
    sentence that ALREADY contains a documented reasoning
    marker. This converts bullet-like prose into explanatory
    cover prose while preserving the original factual content.
    """

    overlaps = (
        report.get("details", {})
        .get(
            "semantic_resume_overlap",
            []
        )
    )

    repaired = list(paragraphs)

    for item in overlaps:
        target = str(
            item.get(
                "cover_sentence",
                ""
            )
        ).strip()

        if not target:
            continue

        repaired_this = False

        for paragraph_index, paragraph in enumerate(
            repaired
        ):
            if target not in paragraph:
                continue

            chunks = sentence_chunks(paragraph)

            target_index = None

            for i, chunk in enumerate(chunks):
                if chunk == target:
                    target_index = i
                    break

            if target_index is None:
                continue

            # Prefer the following reasoning sentence because
            # cover prose commonly states evidence first and
            # then explains the decision.
            neighbor_indexes = []

            if target_index + 1 < len(chunks):
                neighbor_indexes.append(
                    target_index + 1
                )

            if target_index - 1 >= 0:
                neighbor_indexes.append(
                    target_index - 1
                )

            for neighbor_index in neighbor_indexes:
                neighbor = chunks[
                    neighbor_index
                ]

                if not has_reasoning(neighbor):
                    continue

                if neighbor_index > target_index:
                    merged = (
                        target.rstrip(".!?")
                        + "; "
                        + neighbor[0].lower()
                        + neighbor[1:]
                    )

                    old_pair = (
                        target
                        + " "
                        + neighbor
                    )

                else:
                    merged = (
                        neighbor.rstrip(".!?")
                        + "; "
                        + target[0].lower()
                        + target[1:]
                    )

                    old_pair = (
                        neighbor
                        + " "
                        + target
                    )

                paragraph = paragraph.replace(
                    old_pair,
                    merged,
                    1,
                )

                repaired[
                    paragraph_index
                ] = paragraph

                repaired_this = True
                break

            if repaired_this:
                break

        if not repaired_this:
            raise SystemExit(
                "STOP: semantic-overlap sentence had no "
                "adjacent documented reasoning sentence; "
                "deterministic repair refused."
            )

    return repaired


def repair_paragraph1_specific_hook(
    paragraph,
    plan,
):
    """
    Add one already-authorized numerical anchor from the cover
    plan to paragraph 1.

    No new fact is created. The anchor already belongs to the
    selected primary evidence and is already authorized for the
    cover by Cover Planner V2.
    """
    anchors = plan.get(
        "numerical_anchors",
        [],
    )

    candidates = []

    for anchor in anchors:
        value = str(
            anchor.get(
                "value",
                "",
            )
        ).strip()

        label = str(
            anchor.get(
                "label",
                "",
            )
        ).strip()

        text = str(
            anchor.get(
                "text",
                "",
            )
        ).strip()

        if value and label:
            candidates.append(
                value + " " + label
            )
        elif text:
            candidates.append(text)

    phrase = (
        min(
            candidates,
            key=lambda x: (
                len(str(x).split()),
                len(str(x)),
            ),
        )
        if candidates
        else None
    )

    if not phrase:
        raise SystemExit(
            "STOP: paragraph-1 hook repair has no "
            "plan-authorized numerical anchor."
        )

    if normalize(phrase) in normalize(
        paragraph
    ):
        return paragraph

    chunks = sentence_chunks(
        paragraph
    )

    if not chunks:
        raise SystemExit(
            "STOP: paragraph-1 hook repair received "
            "an empty paragraph."
        )

    first = chunks[0]

    revised_first = (
        first.rstrip(".!?")
        + ", spanning "
        + phrase
        + "."
    )

    return paragraph.replace(
        first,
        revised_first,
        1,
    )


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--cover", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--report", required=True)

    args = ap.parse_args()

    cover_path = Path(args.cover)
    plan_path = Path(args.plan)
    report_path = Path(args.report)

    cover = json.loads(cover_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    failed = set(report.get("failed_checks", []))

    unexpected = failed - ALLOWED_REPAIRS

    if unexpected:
        raise SystemExit(
            "STOP: repair engine received non-style gate failures: "
            + ", ".join(sorted(unexpected))
        )

    paragraphs = cover.get("paragraphs", [])

    if len(paragraphs) != 3:
        raise SystemExit(
            "STOP: deterministic repair requires exactly 3 paragraphs."
        )

    company = str(
        (
            plan.get("target_job", {}).get("company")
            or cover.get("company")
            or ""
        )
    ).strip()

    if not company:
        raise SystemExit(
            "STOP: exact employer identity unavailable."
        )

    p1 = paragraphs[0]
    p3 = paragraphs[2]

    # ---------------------------------------------------------
    # 0. Plan-authorized paragraph-1 specificity hook
    # ---------------------------------------------------------

    if "paragraph1_specific_hook" in failed:
        p1 = repair_paragraph1_specific_hook(
            p1,
            plan,
        )

        paragraphs[0] = p1

    # ---------------------------------------------------------
    # 1. Plan-authorized specific employer / role interest
    # ---------------------------------------------------------

    if "specific_interest" in failed:
        interest_sentence = build_interest_sentence(
            plan,
            company,
        )

        if not interest_sentence:
            raise SystemExit(
                "STOP: cover plan contains no deterministic "
                "interest signal that can be safely repaired."
            )

        p3 = replace_interest_sentence(
            p3,
            interest_sentence,
        )

    p3 = normalize_repairer_interest_grammar(
        p3,
        company,
    )

    # ---------------------------------------------------------
    # 2. Exact company identity in paragraph 3
    # ---------------------------------------------------------

    if (
        "paragraph3_names_company" in failed
        and company not in p3
    ):
        acronym = acronym_from_company(company)

        if acronym and re.search(
            rf"\b{re.escape(acronym)}\b",
            p3
        ):
            p3 = re.sub(
                rf"\b{re.escape(acronym)}\b",
                company,
                p3,
                count=1,
            )
        else:
            raise SystemExit(
                "STOP: cannot safely expand paragraph-3 "
                "employer identity."
            )

    # ---------------------------------------------------------
    # 2. Deterministic banned AI-pattern repair
    # ---------------------------------------------------------

    replacements = {
        r"\bI would apply\b":
            "I would bring",
        r"\bI am excited to apply\b":
            "I am interested in",
        r"\bI would welcome the opportunity\b":
            "I would value the opportunity",
        r"\bThat combination\b":
            "This mix",
    }

    if "no_ai_pattern_language" in failed:

        # Preserve any paragraph-1/paragraph-3 repairs already made
        # above before applying language repair to the whole letter.
        paragraphs[0] = p1
        paragraphs[2] = p3

        for index, paragraph in enumerate(
            paragraphs
        ):
            repaired_paragraph = paragraph

            for pattern, replacement in (
                replacements.items()
            ):
                repaired_paragraph = re.sub(
                    pattern,
                    replacement,
                    repaired_paragraph,
                    flags=re.I,
                )

            paragraphs[index] = (
                repaired_paragraph
            )

        p1 = paragraphs[0]
        p3 = paragraphs[2]

    # ---------------------------------------------------------
    # 3. Split only sentences the gate itself identified as
    #    keyword-stacked. Preserve all underlying content.
    # ---------------------------------------------------------

    if "no_paragraph3_keyword_stack" in failed:
        stacked = (
            report.get("details", {})
            .get("keyword_stack_sentences", [])
        )

        for sentence in stacked:
            candidate_sentence = sentence

            # An earlier deterministic AI-pattern replacement
            # may have changed the exact report sentence.
            if candidate_sentence not in p3:
                for pattern, replacement in replacements.items():
                    candidate_sentence = re.sub(
                        pattern,
                        replacement,
                        candidate_sentence,
                        flags=re.I,
                    )

            if candidate_sentence not in p3:
                raise SystemExit(
                    "STOP: gate-identified keyword-stack "
                    "sentence is no longer present."
                )

            repaired = split_keyword_stack_sentence(
                candidate_sentence
            )

            if repaired == candidate_sentence:
                raise SystemExit(
                    "STOP: keyword-stack sentence could not "
                    "be deterministically split."
                )

            p3 = p3.replace(
                candidate_sentence,
                repaired,
                1,
            )

    paragraphs[2] = p3

    # ---------------------------------------------------------
    # 5. Deterministic semantic complementarity repair
    # ---------------------------------------------------------

    if "semantic_resume_complementarity" in failed:
        paragraphs = repair_semantic_overlap(
            paragraphs,
            report,
        )

        p3 = paragraphs[2]

    # ---------------------------------------------------------
    # 6. Deterministic over-length compression
    # ---------------------------------------------------------

    def body_words():
        return sum(
            len(str(x).split())
            for x in [
                paragraphs[0],
                paragraphs[1],
                p3,
            ]
        )

    #
    # Every deterministic edit may change length. Enforce the canonical
    # 190-240 word contract on the resulting cover, not only when the
    # original gate happened to report body_word_count.
    min_words = 190
    max_words = 240

    if (
        "body_word_count" in failed
        and body_words() < min_words
    ):
        raise SystemExit(
            "STOP: cover is below the minimum word budget; "
            "deterministic expansion is not permitted."
        )

    if body_words() > max_words:
        compression_rules = [
            (
                "In practice, I would ",
                "I would ",
            ),
            (
                "the specific reason I am pursuing this role",
                "why I am pursuing this role",
            ),
            (
                "I would bring that reasoning to",
                "I would bring it to",
            ),
            (
                "I would use that reasoning to",
                "I would use it to",
            ),
            (
                "that help cross-functional partners",
                "helping cross-functional partners",
            ),
        ]

        for old, new in compression_rules:
            if body_words() <= max_words:
                break

            if old in p3:
                p3 = p3.replace(
                    old,
                    new,
                    1,
                )

        if body_words() > max_words:
            raise SystemExit(
                "STOP: deterministic post-repair compression "
                f"could not reach <= {max_words} words."
            )

    paragraphs[2] = p3
    cover["paragraphs"] = paragraphs

    # ---------------------------------------------------------
    # 7. Synchronize declared JD-term metadata with repaired
    #    prose. Never retain a declared term absent from body.
    # ---------------------------------------------------------

    body = " ".join(
        str(x)
        for x in paragraphs
    )

    declared_terms = [
        str(x).strip()
        for x in cover.get(
            "jd_terms_used",
            []
        )
        if str(x).strip()
    ]

    present_terms = [
        term
        for term in declared_terms
        if normalize(term) in normalize(body)
    ]

    if (
        "jd_terms_present" in failed
        or present_terms != declared_terms
    ):
        if len(present_terms) < 3:
            raise SystemExit(
                "STOP: fewer than 3 declared supported JD "
                "terms remain in repaired cover prose."
            )

        cover["jd_terms_used"] = present_terms

    cover_path.write_text(
        json.dumps(
            cover,
            indent=2,
            ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    print("DETERMINISTIC COVER REPAIR: APPLIED")
    print("COMPANY:", company)
    print("PARAGRAPH 3:")
    print(p3)
    print("MODEL CALLS: 0")


if __name__ == "__main__":
    main()
