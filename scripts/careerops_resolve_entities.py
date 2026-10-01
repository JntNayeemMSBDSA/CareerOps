from careerops_config import source_dir
#!/usr/bin/env python3

import csv
import json
import re
from pathlib import Path
from collections import Counter, defaultdict


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)

INDEX_PATH = source_dir(ROOT) / 'verified_evidence_index.csv'
INVENTORY_PATH = source_dir(ROOT) / 'verified_evidence_inventory.md'

OUT = RUNTIME / 'candidate_entities.json'


ENTITY_HEADING = re.compile(
    r"^##\s+((?:EXP|PRJ)-\d{3})\s+-\s+(.+?)\s*$",
    re.M
)


def normalize_org(text):
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def parse_inventory_blocks(text):
    matches = list(
        ENTITY_HEADING.finditer(text)
    )

    blocks = {}

    for i, match in enumerate(matches):
        entity_id = match.group(1).strip()
        heading_name = match.group(2).strip()

        start = match.start()
        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )

        block = text[start:end].strip()

        blocks[entity_id] = {
            "heading_name": heading_name,
            "block_text": block
        }

    return blocks


def split_tags(text):
    return [
        x.strip()
        for x in (text or "").split(";")
        if x.strip()
    ]


def main():
    for path in [
        INDEX_PATH,
        INVENTORY_PATH
    ]:
        if not path.exists():
            raise SystemExit(
                f"Missing required source: {path}"
            )

    with INDEX_PATH.open(
        newline="",
        encoding="utf-8-sig",
        errors="replace"
    ) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise SystemExit(
            "Evidence index is empty."
        )

    ids = [
        row["ID"].strip()
        for row in rows
    ]

    duplicate_ids = [
        item
        for item, count in Counter(ids).items()
        if count > 1
    ]

    if duplicate_ids:
        raise SystemExit(
            "Duplicate evidence IDs found: "
            + ", ".join(duplicate_ids)
        )

    inventory_text = INVENTORY_PATH.read_text(
        encoding="utf-8",
        errors="replace"
    )

    blocks = parse_inventory_blocks(
        inventory_text
    )

    missing_blocks = [
        entity_id
        for entity_id in ids
        if entity_id not in blocks
    ]

    extra_blocks = [
        entity_id
        for entity_id in blocks
        if entity_id not in ids
    ]

    entities = []

    org_groups = defaultdict(list)

    for row in rows:
        entity_id = row["ID"].strip()

        block = blocks.get(
            entity_id,
            {}
        )

        organization = (
            row.get("Organization")
            or ""
        ).strip()

        org_key = normalize_org(
            organization
        )

        entity = {
            "entity_id": entity_id,

            "canonical_name": (
                row.get("Name")
                or ""
            ).strip(),

            "inventory_heading_name": block.get(
                "heading_name"
            ),

            "entity_type": (
                row.get("Entity Type")
                or ""
            ).strip(),

            "organization": organization,

            "role": (
                row.get("Role")
                or ""
            ).strip(),

            "period": (
                row.get("Period")
                or ""
            ).strip(),

            "ownership_status": (
                row.get("Ownership Status")
                or ""
            ).strip(),

            "evidence_status": (
                row.get("Evidence Status")
                or ""
            ).strip(),

            "source_artifacts": (
                row.get("Source Artifacts")
                or ""
            ).strip(),

            "role_tags": split_tags(
                row.get("Role Tags")
            ),

            "inventory_block_present": (
                entity_id in blocks
            ),

            "inventory_block_characters": len(
                block.get(
                    "block_text",
                    ""
                )
            ),

            "resolution": {
                "canonical_entity_id": entity_id,

                # Critical rule:
                # same organization/client/tool/dataset
                # does NOT imply same project.
                "merge_status": "KEEP_SEPARATE",

                "merge_allowed_without_explicit_directive": False,

                "shared_organization_is_not_merge_evidence": True,

                "shared_tools_are_not_merge_evidence": True,

                "shared_role_tags_are_not_merge_evidence": True,

                "shared_dataset_alone_is_not_merge_evidence": True,

                "shared_client_or_course_alone_is_not_merge_evidence": True
            }
        }

        entities.append(
            entity
        )

        if org_key:
            org_groups[org_key].append(
                entity_id
            )

    shared_context_groups = []

    for org_key, group_ids in org_groups.items():
        if len(group_ids) < 2:
            continue

        organization = next(
            e["organization"]
            for e in entities
            if e["entity_id"] == group_ids[0]
        )

        shared_context_groups.append({
            "organization": organization,
            "entity_ids": group_ids,
            "relationship": "SHARED_CONTEXT_ONLY",
            "merge_entities": False
        })

    output = {
        "schema_version": "candidate-entities-v1",

        "policy": {
            "canonical_evidence_id_is_entity_boundary": True,

            "automatic_merging": False,

            "merge_requires_explicit_supported_directive": True,

            "same_organization_does_not_imply_same_project": True,

            "same_client_does_not_imply_same_project": True,

            "same_dataset_does_not_imply_same_project": True,

            "same_tools_does_not_imply_same_project": True,

            "same_course_does_not_imply_same_project": True,

            "same_role_tags_do_not_imply_same_project": True,

            "employment_and_project_boundaries_must_be_preserved": True,

            "historical_work_and_later_reconstruction_must_not_be_silently_merged": True
        },

        "validation": {
            "index_entity_count": len(rows),
            "inventory_entity_block_count": len(blocks),
            "duplicate_ids": duplicate_ids,
            "missing_inventory_blocks": missing_blocks,
            "extra_inventory_blocks": extra_blocks
        },

        "entities": entities,

        "shared_context_groups": shared_context_groups
    }

    OUT.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        )
    )

    print("ENTITY RESOLUTION: CREATED")
    print("CANONICAL ENTITIES:", len(entities))
    print(
        "INVENTORY BLOCKS:",
        len(blocks)
    )
    print(
        "MISSING BLOCKS:",
        len(missing_blocks)
    )
    print(
        "EXTRA BLOCKS:",
        len(extra_blocks)
    )
    print(
        "SHARED CONTEXT GROUPS:",
        len(shared_context_groups)
    )

    print("\nENTITY TYPES:")

    counts = Counter(
        e["entity_type"]
        for e in entities
    )

    for key, value in sorted(
        counts.items()
    ):
        print(
            f"  {key}: {value}"
        )

    print(
        "\nSHARED CONTEXT, NOT MERGED:"
    )

    if not shared_context_groups:
        print("  NONE")

    for group in shared_context_groups:
        print(
            " ",
            group["organization"],
            "=>",
            ", ".join(
                group["entity_ids"]
            )
        )

    print(
        "\nOUTPUT:",
        OUT.relative_to(ROOT)
    )


if __name__ == "__main__":
    main()
