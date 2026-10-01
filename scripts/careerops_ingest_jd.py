#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from careerops_probe_ats import probe as probe_ats, fetch as fetch_page
from careerops_detect_ats import attach_behavior_profile


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
RUNTIME.mkdir(parents=True, exist_ok=True)


class VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
            return

        if self.skip_depth == 0 and tag in {
            "p", "div", "section", "article", "li",
            "h1", "h2", "h3", "h4", "br", "tr"
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            if self.skip_depth > 0:
                self.skip_depth -= 1
            return

        if self.skip_depth == 0 and tag in {
            "p", "div", "section", "article", "li",
            "h1", "h2", "h3", "h4", "tr"
        }:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text + " ")


def clean_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Normalize horizontal whitespace.
    text = re.sub(r"[ \t]+", " ", text)

    # Remove spaces surrounding newlines.
    text = re.sub(r" *\n *", "\n", text)

    # Collapse excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse repeated spaces again after HTML extraction.
    text = re.sub(r" {2,}", " ", text)

    return text.strip()





def ensure_ats_behavior_profile(
    detection,
    *,
    unknown_reason=None,
):
    """
    Normalize ATS metadata at the ingestion boundary.

    Known ATS platforms receive their canonical behavior profile.
    Unknown/unresolved ATS values receive UNKNOWN_CONSERVATIVE_MIXED
    through the existing Career-Ops UNKNOWN_FALLBACK contract.

    This function never guesses an ATS vendor and never invents
    employer-specific configuration.
    """
    base = (
        dict(detection)
        if isinstance(
            detection,
            dict,
        )
        else {}
    )

    if not base.get(
        "platform"
    ):
        base[
            "platform"
        ] = "UNKNOWN_ATS"

    if (
        base.get(
            "platform"
        )
        == "UNKNOWN_ATS"
    ):
        base.setdefault(
            "confidence",
            "UNKNOWN",
        )

        if unknown_reason:
            base.setdefault(
                "reason",
                unknown_reason,
            )

    return attach_behavior_profile(
        base
    )

#
# Universal source-adapter normalization.
#
# Rules:
# - never infer an employer/job identity without current-requisition evidence;
# - decode HTML entities before identity comparison/output;
# - known ATS adapters may exploit deterministic vendor URL/page contracts;
# - dynamic shells are never accepted as job descriptions;
# - adapter failure fails closed to manual JD rather than fabricating content.


def html_entity_decode(value):
    import html as _html

    if value is None:
        return value

    return _html.unescape(
        str(value)
    )


def normalize_identity_entities(value):
    if isinstance(
        value,
        dict,
    ):
        return {
            key:
                normalize_identity_entities(
                    child
                )
            for key, child
            in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            normalize_identity_entities(
                child
            )
            for child in value
        ]

    if isinstance(
        value,
        str,
    ):
        return clean_text(
            html_entity_decode(
                value
            )
        )

    return value


def identity_apply_high(
    identity,
    field,
    value,
    source,
):
    value = clean_text(
        html_entity_decode(
            value
        )
        or ""
    )

    if not value:
        return identity

    result = dict(
        identity
        if isinstance(
            identity,
            dict,
        )
        else {}
    )

    current = dict(
        result.get(
            field,
            {}
        )
        if isinstance(
            result.get(
                field
            ),
            dict,
        )
        else {}
    )

    existing = clean_text(
        html_entity_decode(
            current.get(
                "value",
                ""
            )
        )
        or ""
    )

    # Never overwrite conflicting current-requisition high-confidence evidence.
    if (
        existing
        and identity_key(
            existing
        )
        != identity_key(
            value
        )
        and str(
            current.get(
                "confidence",
                ""
            )
        ).upper()
        == "HIGH"
    ):
        return result

    alternatives = list(
        current.get(
            "alternatives",
            []
        )
        if isinstance(
            current.get(
                "alternatives"
            ),
            list,
        )
        else []
    )

    current.update({
        "status":
            "RESOLVED_HIGH",

        "value":
            value,

        "confidence":
            "HIGH",

        "sources":
            [source],

        "confirmed_in_current_job":
            True,

        "alternatives":
            alternatives,
    })

    result[
        field
    ] = current

    candidates = list(
        result.get(
            "candidates",
            []
        )
        if isinstance(
            result.get(
                "candidates"
            ),
            list,
        )
        else []
    )

    candidate_key = (
        field,
        identity_key(
            value
        ),
        source,
    )

    existing_keys = {
        (
            row.get(
                "field"
            ),
            identity_key(
                row.get(
                    "value",
                    ""
                )
            ),
            row.get(
                "source"
            ),
        )
        for row in candidates
        if isinstance(
            row,
            dict,
        )
    }

    if candidate_key not in existing_keys:
        candidates.append({
            "field":
                field,

            "value":
                value,

            "source":
                source,

            "confidence":
                "HIGH",

            "priority":
                140,

            "requisition_bound":
                True,
        })

    result[
        "candidates"
    ] = candidates

    result[
        "candidate_count"
    ] = len(
        candidates
    )

    company_ok = bool(
        result.get(
            "company",
            {}
        ).get(
            "value"
        )
    )

    position_ok = bool(
        result.get(
            "position",
            {}
        ).get(
            "value"
        )
    )

    if company_ok and position_ok:
        result[
            "status"
        ] = "COMPLETE_HIGH"

    elif company_ok or position_ok:
        result[
            "status"
        ] = "PARTIAL_HIGH"

    else:
        result[
            "status"
        ] = "UNRESOLVED"

    policy = dict(
        result.get(
            "policy",
            {}
        )
        if isinstance(
            result.get(
                "policy"
            ),
            dict,
        )
        else {}
    )

    policy[
        "high_confidence_autofill_eligible"
    ] = bool(
        company_ok
        or position_ok
    )

    policy.setdefault(
        "current_requisition_confirmation_required",
        True,
    )

    policy.setdefault(
        "silent_guessing_forbidden",
        True,
    )

    result[
        "policy"
    ] = policy

    return result


def page_title_from_html(
    html_source,
):
    import re as _re

    match = _re.search(
        r"<title[^>]*>(.*?)</title>",
        str(
            html_source
            or ""
        ),
        flags=(
            _re.I
            | _re.S
        ),
    )

    if not match:
        return ""

    title = _re.sub(
        r"<[^>]+>",
        " ",
        match.group(
            1
        ),
    )

    return clean_text(
        html_entity_decode(
            title
        )
    )


def augment_platform_identity(
    identity,
    *,
    platform,
    html_source,
):
    import re as _re

    result = normalize_identity_entities(
        identity
    )

    platform = str(
        platform
        or ""
    )

    # Greenhouse's current hosted-job page title has a deterministic
    # current-requisition shape:
    #
    #   Job Application for <EXACT JOB TITLE> at <EXACT EMPLOYER>
    #
    # This is stronger than guessing from URL tenant slugs.
    if platform == "Greenhouse":
        page_title = page_title_from_html(
            html_source
        )

        match = _re.fullmatch(
            r"Job Application for\s+(.+?)\s+at\s+(.+)",
            page_title,
            flags=_re.I,
        )

        if match:
            result = identity_apply_high(
                result,
                "position",
                match.group(
                    1
                ),
                "GREENHOUSE_PAGE_TITLE_CURRENT_REQUISITION",
            )

            result = identity_apply_high(
                result,
                "company",
                match.group(
                    2
                ),
                "GREENHOUSE_PAGE_TITLE_CURRENT_REQUISITION",
            )

    return normalize_identity_entities(
        result
    )


def trim_post_jd_application_tail(
    text,
):
    import re as _re

    value = clean_text(
        html_entity_decode(
            text
            or ""
        )
    )

    if not value:
        return value

    lines = [
        clean_text(
            line
        )
        for line in value.splitlines()
    ]

    lines = [
        line
        for line in lines
        if line
    ]

    # Strong post-JD boundaries only. Do NOT use generic "Apply" because
    # some pages place an Apply button above the description.
    hard_markers = (
        r"^Create a Job Alert$",
        r"^Apply for this job$",
        r"^Autofill my application$",
        r"^Voluntary Self-Identification",
        r"^U\.?S\.? Equal Employment Opportunity information",
    )

    end = len(
        lines
    )

    for index, line in enumerate(
        lines
    ):
        if index < 8:
            continue

        if not any(
            _re.search(
                pattern,
                line,
                flags=_re.I,
            )
            for pattern
            in hard_markers
        ):
            continue

        prefix = "\n".join(
            lines[
                :index
            ]
        )

        job_signals = sum(
            bool(
                _re.search(
                    pattern,
                    prefix,
                    flags=_re.I,
                )
            )
            for pattern
            in (
                r"\bresponsibilit",
                r"\bqualifications?\b",
                r"\brequirements?\b",
                r"\bexperience\b",
                r"\bskills?\b",
            )
        )

        if job_signals >= 2:
            end = index
            break

    return clean_text(
        "\n".join(
            lines[
                :end
            ]
        )
    )


def workday_visible_tenant_name(
    tenant,
    text,
):
    import re as _re

    target = _re.sub(
        r"[^a-z0-9]+",
        "",
        str(
            tenant
            or ""
        ).casefold(),
    )

    if not target:
        return None

    words = _re.findall(
        r"[A-Za-z0-9][A-Za-z0-9&'.-]*",
        str(
            text
            or ""
        ),
    )

    # Corroborate the URL tenant against an exact visible phrase in the
    # current job body. We never return the tenant slug by itself unless
    # it is visibly present in the current requisition.
    for size in range(
        1,
        min(
            6,
            len(
                words
            )
            + 1,
        ),
    ):
        for start in range(
            0,
            len(
                words
            )
            - size
            + 1,
        ):
            phrase = " ".join(
                words[
                    start:
                    start
                    + size
                ]
            )

            compact = _re.sub(
                r"[^a-z0-9]+",
                "",
                phrase.casefold(),
            )

            if compact == target:
                return phrase

    return None


def recursive_first_string(
    value,
    keys,
):
    wanted = {
        str(
            key
        ).casefold()
        for key in keys
    }

    if isinstance(
        value,
        dict,
    ):
        for key, child in value.items():
            if (
                str(
                    key
                ).casefold()
                in wanted
                and isinstance(
                    child,
                    str,
                )
                and clean_text(
                    child
                )
            ):
                return child

        for child in value.values():
            found = recursive_first_string(
                child,
                keys,
            )

            if found:
                return found

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            found = recursive_first_string(
                child,
                keys,
            )

            if found:
                return found

    return None


def fetch_workday_public_job(
    url,
):
    import json as _json
    import re as _re
    import urllib.parse as _urlparse
    import urllib.request as _urlrequest

    parsed = _urlparse.urlparse(
        url
    )

    host = (
        parsed.hostname
        or ""
    )

    if not (
        host.endswith(
            ".myworkdayjobs.com"
        )
        or host.endswith(
            ".myworkdaysite.com"
        )
    ):
        return None, {
            "status":
                "NOT_WORKDAY_URL",
        }

    parts = [
        _urlparse.unquote(
            part
        )
        for part
        in parsed.path.split(
            "/"
        )
        if part
    ]

    if "job" not in parts:
        return None, {
            "status":
                "NO_JOB_SEGMENT",
        }

    job_index = parts.index(
        "job"
    )

    if job_index < 1:
        return None, {
            "status":
                "NO_SITE_SEGMENT",
        }

    site = parts[
        job_index - 1
    ]

    original_job_path = "/".join(
        parts[
            job_index + 1:
        ]
    )

    tenant = host.split(
        "."
    )[0]

    base = (
        f"{parsed.scheme or 'https'}://"
        f"{host}"
        f"/wday/cxs/"
        f"{tenant}/"
        f"{site}"
    )

    requisition_match = _re.search(
        r"_([A-Za-z0-9-]+)$",
        original_job_path,
    )

    requisition_id = (
        requisition_match.group(
            1
        )
        if requisition_match
        else ""
    )

    search_terms = []

    if requisition_id:
        search_terms.append(
            requisition_id
        )

    slug_title = (
        original_job_path.split(
            "_"
        )[0]
        .replace(
            "--",
            ", "
        )
        .replace(
            "-",
            " "
        )
    )

    slug_title = clean_text(
        slug_title
    )

    if slug_title:
        search_terms.append(
            slug_title
        )

    # Also test the direct path first. Some Workday tenants support it
    # without a search discovery step.
    detail_paths = [
        "/job/"
        + original_job_path
    ]

    search_audit = []

    for search_text in search_terms:
        endpoint = (
            base
            + "/jobs"
        )

        payload = _json.dumps({
            "appliedFacets":
                {},

            "limit":
                20,

            "offset":
                0,

            "searchText":
                search_text,
        }).encode(
            "utf-8"
        )

        request = _urlrequest.Request(
            endpoint,
            data=payload,
            headers={
                "User-Agent":
                    "Mozilla/5.0",

                "Accept":
                    "application/json",

                "Content-Type":
                    "application/json",
            },
            method="POST",
        )

        try:
            with _urlrequest.urlopen(
                request,
                timeout=25,
            ) as response:
                search_json = _json.loads(
                    response.read().decode(
                        "utf-8",
                        errors="replace",
                    )
                )

        except Exception as exc:
            search_audit.append({
                "search_text":
                    search_text,

                "status":
                    "ERROR",

                "error":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            })

            continue

        postings = (
            search_json.get(
                "jobPostings"
            )
            or []
        )

        search_audit.append({
            "search_text":
                search_text,

            "status":
                "OK",

            "result_count":
                len(
                    postings
                ),
        })

        for posting in postings:
            if not isinstance(
                posting,
                dict,
            ):
                continue

            external_path = posting.get(
                "externalPath"
            )

            if not isinstance(
                external_path,
                str,
            ):
                continue

            combined = (
                _json.dumps(
                    posting,
                    ensure_ascii=False,
                )
                + " "
                + external_path
            )

            if (
                requisition_id
                and requisition_id.casefold()
                not in combined.casefold()
            ):
                continue

            if external_path not in detail_paths:
                detail_paths.insert(
                    0,
                    external_path,
                )

    detail_errors = []

    for external_path in detail_paths:
        if not str(
            external_path
        ).startswith(
            "/"
        ):
            external_path = (
                "/"
                + str(
                    external_path
                )
            )

        endpoint = (
            base
            + external_path
        )

        request = _urlrequest.Request(
            endpoint,
            headers={
                "User-Agent":
                    "Mozilla/5.0",

                "Accept":
                    "application/json",
            },
        )

        try:
            with _urlrequest.urlopen(
                request,
                timeout=25,
            ) as response:
                detail = _json.loads(
                    response.read().decode(
                        "utf-8",
                        errors="replace",
                    )
                )

        except Exception as exc:
            detail_errors.append({
                "path":
                    external_path,

                "error":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            })

            continue

        title = recursive_first_string(
            detail,
            (
                "title",
                "jobTitle",
            ),
        )

        description = recursive_first_string(
            detail,
            (
                "jobDescription",
                "description",
            ),
        )

        if not description:
            continue

        body = html_to_text(
            html_entity_decode(
                description
            )
        )

        body = trim_post_jd_application_tail(
            body
        )

        if len(
            body.split()
        ) < 80:
            continue

        company = recursive_first_string(
            detail,
            (
                "companyName",
                "company",
                "hiringOrganization",
                "organizationName",
            ),
        )

        if not company:
            company = workday_visible_tenant_name(
                tenant,
                body,
            )

        return {
            "title":
                clean_text(
                    html_entity_decode(
                        title
                        or ""
                    )
                ),

            "company":
                clean_text(
                    html_entity_decode(
                        company
                        or ""
                    )
                ),

            "body":
                body,

            "detail_path":
                external_path,
        }, {
            "status":
                "WORKDAY_PUBLIC_JOB_RESOLVED",

            "tenant":
                tenant,

            "site":
                site,

            "search_audit":
                search_audit,

            "detail_errors":
                detail_errors,
        }

    return None, {
        "status":
            "WORKDAY_PUBLIC_JOB_UNRESOLVED",

        "tenant":
            tenant,

        "site":
            site,

        "search_audit":
            search_audit,

        "detail_errors":
            detail_errors,
    }

#
# Deterministic CURRENT-requisition identity evidence.
#
# High-confidence sources:
#   - schema.org / JSON-LD JobPosting
#   - explicit Company:/Employer:/Job Title:/Position: labels
#   - already-proven "Employer - Details - Position" page-title shape
#
# Supporting sources:
#   - H1
#   - document title / og:title / twitter:title
#
# Nothing is auto-resolved merely because it looks plausible.
# A selected value must also appear in the current visible requisition.
class IdentityHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.page_title_parts = []
        self.h1_values = []
        self.meta = []
        self.ld_json_blocks = []
        self.logo_labels = []

        self._capture_title = False
        self._title_parts = []

        self._h1_depth = 0
        self._h1_parts = []

        self._capture_ld_json = False
        self._ld_json_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        attrs = {
            str(k).lower():
                str(v or "")
            for k, v in attrs
        }

        if tag in {'img','svg','a'} and ('logo' in ' '.join(attrs.get(k,'') for k in ['class','id','alt','title','aria-label']).casefold()):
            for key in ['alt','title','aria-label']:
                label = re.sub(r"\b(?:company\s+)?logo\b", '', attrs.get(key,''), flags=re.I).strip(' -|')
                if label and len(label)<=120:
                    self.logo_labels.append({'value':label,'attribute':key})

        if tag == "title":
            self._capture_title = True
            self._title_parts = []

        if tag == "h1":
            self._h1_depth += 1

            if self._h1_depth == 1:
                self._h1_parts = []

        if tag == "meta":
            key = (
                attrs.get("property")
                or attrs.get("name")
                or ""
            ).strip().casefold()

            content = (
                attrs.get("content")
                or ""
            ).strip()

            if key and content:
                self.meta.append(
                    {
                        "key": key,
                        "content": content,
                    }
                )

        if tag == "script":
            script_type = (
                attrs.get("type")
                or ""
            ).casefold()

            if "ld+json" in script_type:
                self._capture_ld_json = True
                self._ld_json_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "title" and self._capture_title:
            value = clean_text(
                " ".join(
                    self._title_parts
                )
            )

            if value:
                self.page_title_parts.append(
                    value
                )

            self._capture_title = False
            self._title_parts = []

        if tag == "h1" and self._h1_depth:
            self._h1_depth -= 1

            if self._h1_depth == 0:
                value = clean_text(
                    " ".join(
                        self._h1_parts
                    )
                )

                if value:
                    self.h1_values.append(
                        value
                    )

                self._h1_parts = []

        if tag == "script" and self._capture_ld_json:
            value = "".join(
                self._ld_json_parts
            ).strip()

            if value:
                self.ld_json_blocks.append(
                    value
                )

            self._capture_ld_json = False
            self._ld_json_parts = []

    def handle_data(self, data):
        if self._capture_title:
            self._title_parts.append(
                data
            )

        if self._h1_depth:
            self._h1_parts.append(
                data
            )

        if self._capture_ld_json:
            self._ld_json_parts.append(
                data
            )


def identity_key(value):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean_text(
            value
        ).casefold(),
    ).strip()


def identity_confirmed_in_current_job(
    value,
    visible_text,
):
    value_key = identity_key(
        value
    )

    text_key = identity_key(
        visible_text
    )

    return bool(
        value_key
        and value_key in text_key
    )


def iter_json_objects(value):
    if isinstance(
        value,
        dict,
    ):
        yield value

        for child in value.values():
            yield from iter_json_objects(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            yield from iter_json_objects(
                child
            )


def is_jobposting_object(obj):
    value = obj.get(
        "@type"
    )

    if isinstance(
        value,
        str,
    ):
        values = [
            value
        ]

    elif isinstance(
        value,
        list,
    ):
        values = [
            str(x)
            for x in value
        ]

    else:
        values = []

    return any(
        "jobposting"
        == identity_key(
            item
        ).replace(
            " ",
            "",
        )
        for item in values
    )


def resolve_identity_field(
    field,
    candidates,
    visible_text,
):
    relevant = [
        row
        for row in candidates
        if row.get(
            "field"
        ) == field
        and clean_text(
            row.get(
                "value"
            )
        )
    ]

    grouped = {}

    for row in relevant:
        value = clean_text(
            row.get(
                "value"
            )
        )

        key = identity_key(
            value
        )

        if not key:
            continue

        group = grouped.setdefault(
            key,
            {
                "value":
                    value,
                "sources":
                    [],
                "priorities":
                    [],
                "confidences":
                    [],
                "requisition_bound":
                    [],
            },
        )

        group[
            "sources"
        ].append(
            row.get(
                "source"
            )
        )

        group[
            "priorities"
        ].append(
            int(
                row.get(
                    "priority",
                    0,
                )
            )
        )

        group[
            "confidences"
        ].append(
            row.get(
                "confidence",
                "LOW",
            )
        )

        group[
            "requisition_bound"
        ].append(
            bool(
                row.get(
                    "requisition_bound",
                    False,
                )
            )
        )

    rows = []

    for key, group in grouped.items():
        visible_confirmed = (
            identity_confirmed_in_current_job(
                group[
                    "value"
                ],
                visible_text,
            )
        )

        structured_requisition_confirmed = any(
            group.get(
                "requisition_bound",
                []
            )
        )

        confirmed = (
            visible_confirmed
            or structured_requisition_confirmed
        )

        source_count = len(
            set(
                group[
                    "sources"
                ]
            )
        )

        high_source = any(
            confidence == "HIGH"
            for confidence in group[
                "confidences"
            ]
        )

        rows.append(
            {
                "value":
                    group[
                        "value"
                    ],
                "confirmed_in_current_job":
                    confirmed,
                "visible_text_confirmed":
                    visible_confirmed,
                "structured_requisition_confirmed":
                    structured_requisition_confirmed,
                "source_count":
                    source_count,
                "sources":
                    sorted(
                        set(
                            group[
                                "sources"
                            ]
                        )
                    ),
                "priority":
                    max(
                        group[
                            "priorities"
                        ]
                        or [
                            0
                        ]
                    ),
                "has_high_source":
                    high_source,
            }
        )

    rows.sort(
        key=lambda row: (
            bool(
                row[
                    "confirmed_in_current_job"
                ]
            ),
            bool(
                row[
                    "has_high_source"
                ]
            ),
            row[
                "source_count"
            ],
            row[
                "priority"
            ],
        ),
        reverse=True,
    )

    high = [
        row
        for row in rows
        if row[
            "confirmed_in_current_job"
        ]
        and row[
            "has_high_source"
        ]
    ]

    if len(high) == 1:
        chosen = high[
            0
        ]

        return {
            "status":
                "RESOLVED_HIGH",
            "value":
                chosen[
                    "value"
                ],
            "confidence":
                "HIGH",
            "sources":
                chosen[
                    "sources"
                ],
            "confirmed_in_current_job":
                True,
            "alternatives":
                [
                    row
                    for row in rows
                    if identity_key(
                        row[
                            "value"
                        ]
                    )
                    != identity_key(
                        chosen[
                            "value"
                        ]
                    )
                ],
        }

    if len(high) > 1:
        return {
            "status":
                "AMBIGUOUS",
            "value":
                None,
            "confidence":
                "AMBIGUOUS",
            "sources":
                [],
            "confirmed_in_current_job":
                False,
            "alternatives":
                high,
        }

    corroborated = [
        row
        for row in rows
        if row[
            "confirmed_in_current_job"
        ]
        and row[
            "source_count"
        ] >= 2
    ]

    if len(
        corroborated
    ) == 1:
        chosen = (
            corroborated[
                0
            ]
        )

        return {
            "status":
                "RESOLVED_HIGH_CORROBORATED",
            "value":
                chosen[
                    "value"
                ],
            "confidence":
                "HIGH",
            "sources":
                chosen[
                    "sources"
                ],
            "confirmed_in_current_job":
                True,
            "alternatives":
                [
                    row
                    for row in rows
                    if identity_key(
                        row[
                            "value"
                        ]
                    )
                    != identity_key(
                        chosen[
                            "value"
                        ]
                    )
                ],
        }

    return {
        "status":
            "UNRESOLVED",
        "value":
            None,
        "confidence":
            "UNKNOWN",
        "sources":
            [],
        "confirmed_in_current_job":
            False,
        "alternatives":
            rows,
    }


def extract_identity_evidence(
    visible_text,
    html=None,
):
    visible_text = clean_text(
        visible_text
    )

    candidates = []

    #
    # Identity values from title + hiringOrganization inside the SAME
    # substantive schema.org JobPosting object are already bound to the
    # current requisition object. They do not need to be duplicated in
    # rendered visible text (for example when company branding is logo-only).
    # Multiple conflicting JobPosting objects remain ambiguous and therefore
    # still fail closed.
    def add(
        field,
        value,
        source,
        confidence,
        priority,
        requisition_bound=False,
    ):
        value = clean_text(
            value
        )

        if not value:
            return

        row = {
            "field":
                field,
            "value":
                value,
            "source":
                source,
            "confidence":
                confidence,
            "priority":
                priority,
            "requisition_bound":
                bool(
                    requisition_bound
                ),
        }

        dedupe_key = (
            field,
            identity_key(
                value
            ),
            source,
        )

        if any(
            (
                existing[
                    "field"
                ],
                identity_key(
                    existing[
                        "value"
                    ]
                ),
                existing[
                    "source"
                ],
            )
            == dedupe_key
            for existing in candidates
        ):
            return

        candidates.append(
            row
        )

    lines = [
        clean_text(
            line
        )
        for line in visible_text.splitlines()
        if clean_text(
            line
        )
    ]

    # Explicit pasted/current-page labels.
    label_specs = [
        (
            "company",
            re.compile(
                r"^(?:company|employer|"
                r"hiring organization|organization)"
                r"\s*:\s*(.+)$",
                re.I,
            ),
            "VISIBLE_LABELED_COMPANY",
        ),
        (
            "position",
            re.compile(
                r"^(?:job title|position title|"
                r"position)\s*:\s*(.+)$",
                re.I,
            ),
            "VISIBLE_LABELED_POSITION",
        ),
    ]

    for line in lines:
        for field, pattern, source in label_specs:
            match = pattern.match(
                line
            )

            if match:
                add(
                    field,
                    match.group(
                        1
                    ),
                    source,
                    "HIGH",
                    110,
                )

    # Existing proven generic page-title convention.
    for line in lines[
        :20
    ]:
        match = re.match(
            r"^(.+?)\s+-\s+Details\s+-\s+(.+)$",
            line,
            flags=re.I,
        )

        if not match:
            continue

        add(
            "company",
            match.group(
                1
            ),
            "VISIBLE_DETAILS_PAGE_TITLE",
            "HIGH",
            105,
        )

        add(
            "position",
            match.group(
                2
            ),
            "VISIBLE_DETAILS_PAGE_TITLE",
            "HIGH",
            105,
        )

        break

    if html:
        parser = (
            IdentityHTMLParser()
        )

        try:
            parser.feed(
                html
            )
        except Exception:
            # Identity metadata is supplementary. A malformed HTML
            # document must not make JD ingestion fail.
            parser = (
                IdentityHTMLParser()
            )

        # schema.org / JSON-LD JobPosting.
        for block in parser.ld_json_blocks:
            try:
                payload = json.loads(
                    block
                )
            except Exception:
                continue

            for obj in iter_json_objects(
                payload
            ):
                if not is_jobposting_object(
                    obj
                ):
                    continue

                structured_description = clean_text(
                    html_to_text(
                        str(
                            obj.get(
                                "description"
                            )
                            or ""
                        )
                    )
                )

                structured_title = clean_text(
                    str(
                        obj.get(
                            "title"
                        )
                        or ""
                    )
                )

                org = obj.get(
                    "hiringOrganization"
                )

                if isinstance(
                    org,
                    dict,
                ):
                    org_name = org.get(
                        "name"
                    )
                else:
                    org_name = None

                requisition_bound = bool(
                    len(
                        structured_description
                    )
                    >= 150
                    and structured_title
                    and org_name
                )

                add(
                    "position",
                    structured_title,
                    "JSON_LD_JOBPOSTING_TITLE",
                    "HIGH",
                    130,
                    requisition_bound=
                        requisition_bound,
                )

                add(
                    "company",
                    org_name,
                    "JSON_LD_HIRING_ORGANIZATION",
                    "HIGH",
                    130,
                    requisition_bound=
                        requisition_bound,
                )

        # Branding is corroboration; a logo alone never establishes employer.
        for label in parser.logo_labels:
            add('company', label['value'], 'LOGO_'+label['attribute'].upper(), 'LOW', 35)
        for row in parser.meta:
            if row['key']=='og:site_name':
                add('company', row['content'], 'OG_SITE_NAME', 'MEDIUM', 50)
        for block in parser.ld_json_blocks:
            try: payload=json.loads(block)
            except Exception: continue
            for obj in iter_json_objects(payload):
                if obj.get('@type') in {'Organization','Corporation'}:
                    add('company',obj.get('name',''),'ORGANIZATION_SCHEMA','MEDIUM',60)

        # H1 is useful corroboration but not enough alone to auto-fill.
        for value in parser.h1_values[
            :5
        ]:
            add(
                "position",
                value,
                "HTML_H1",
                "MEDIUM",
                70,
            )

        page_titles = list(
            parser.page_title_parts
        )

        for row in parser.meta:
            if row[
                "key"
            ] in {
                "og:title",
                "twitter:title",
            }:
                page_titles.append(
                    row[
                        "content"
                    ]
                )

        # Reuse the proven "Employer - Details - Position" shape
        # from HTML title/meta as high-confidence evidence.
        for value in page_titles:
            match = re.match(
                r"^(.+?)\s+-\s+Details\s+-\s+(.+)$",
                clean_text(
                    value
                ),
                flags=re.I,
            )

            if match:
                add(
                    "company",
                    match.group(
                        1
                    ),
                    "HTML_DETAILS_PAGE_TITLE",
                    "HIGH",
                    115,
                )

                add(
                    "position",
                    match.group(
                        2
                    ),
                    "HTML_DETAILS_PAGE_TITLE",
                    "HIGH",
                    115,
                )

            else:
                # Generic document-title values are supporting evidence
                # only; they are never sufficient alone.
                add(
                    "position",
                    value,
                    "HTML_PAGE_TITLE",
                    "MEDIUM",
                    45,
                )

    company = (
        resolve_identity_field(
            "company",
            candidates,
            visible_text,
        )
    )

    position = (
        resolve_identity_field(
            "position",
            candidates,
            visible_text,
        )
    )

    statuses = {
        company[
            "status"
        ],
        position[
            "status"
        ],
    }

    if "AMBIGUOUS" in statuses:
        status = "AMBIGUOUS"

    elif (
        company[
            "value"
        ]
        and position[
            "value"
        ]
    ):
        status = "COMPLETE_HIGH"

    elif (
        company[
            "value"
        ]
        or position[
            "value"
        ]
    ):
        status = "PARTIAL_HIGH"

    else:
        status = "UNRESOLVED"

    return {
        "schema_version":
            "job-identity-evidence-v1",
        "status":
            status,
        "company":
            company,
        "position":
            position,
        "candidate_count":
            len(
                candidates
            ),
        "candidates":
            candidates,
        "policy": {
            "high_confidence_autofill_eligible":
                status
                in {
                    "COMPLETE_HIGH",
                    "PARTIAL_HIGH",
                },
            "current_requisition_confirmation_required":
                True,
            "silent_guessing_forbidden":
                True,
        },
    }

#
# Ctrl+A careers-page paste policy:
# - preserve the original source separately for audit
# - remove only unmistakable browser/careers UI controls
# - never summarize or rewrite employer content
# - never boundary-trim the page based on guessed JD start/end
# - retain ambiguous lines
#
# This deliberately prefers false negatives (keeping harmless chrome)
# over false positives (deleting real JD content).
KNOWN_CHROME_EXACT = {
    "skip to main content",
    "skip to content",
    "sign in",
    "log in",
    "login",
    "create account",
    "apply",
    "apply now",
    "apply for this job",
    "save",
    "save job",
    "save this job",
    "share",
    "share job",
    "share this job",
    "back to jobs",
    "back to job search",
    "back to search results",
    "search jobs",
    "job search",
    "view jobs",
    "view all jobs",
    "browse jobs",
    "browse all jobs",
    "careers home",
    "career home",
    "candidate home",
    "my profile",
    "my applications",
    "my application",
    "my jobs",
    "saved jobs",
    "job alerts",
    "set up job alerts",
    "cookie settings",
    "cookie preferences",
    "manage cookies",
    "manage cookie preferences",
    "accept all cookies",
    "accept cookies",
    "reject all cookies",
    "reject cookies",
    "manage preferences",
    "open menu",
    "close menu",
}


KNOWN_CHROME_PATTERNS = [
    re.compile(
        r"^(?:sign|log)\s*in\s+to\s+"
        r"(?:apply|continue|save|view).*$",
        re.I,
    ),
    re.compile(
        r"^apply\s+(?:now|today|for this (?:job|position))$",
        re.I,
    ),
    re.compile(
        r"^(?:save|share)\s+(?:job|this job|position)$",
        re.I,
    ),
    re.compile(
        r"^back\s+to\s+(?:jobs?|job search|search results)$",
        re.I,
    ),
    re.compile(
        r"^(?:search|view|browse)\s+(?:all\s+)?"
        r"(?:jobs?|openings|opportunities)$",
        re.I,
    ),
    re.compile(
        r"^(?:my|candidate)\s+"
        r"(?:profile|applications?|dashboard|home)$",
        re.I,
    ),
    re.compile(
        r"^(?:accept|reject|manage)\s+"
        r"(?:all\s+)?(?:cookies?|cookie preferences)$",
        re.I,
    ),
]


def chrome_key(value):
    value = clean_text(
        str(value or "")
    )
    value = value.strip(
        " \t|•·›»<>"
    )
    return value.casefold()


def conservative_ctrl_a_clean(text):
    """
    Remove only unmistakable careers-site UI chrome.

    Returns:
        cleaned_text, audit_dict

    Important:
    An uncertain line is always retained.
    """
    normalized = clean_text(
        text
    )

    lines = normalized.splitlines()

    kept = []
    removed = []

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        stripped = line.strip()

        if not stripped:
            kept.append(line)
            continue

        key = chrome_key(
            stripped
        )

        reason = None

        if key in KNOWN_CHROME_EXACT:
            reason = "KNOWN_UI_CONTROL"

        elif any(
            pattern.fullmatch(
                stripped
            )
            for pattern in KNOWN_CHROME_PATTERNS
        ):
            reason = "KNOWN_UI_CONTROL_PATTERN"

        if reason:
            removed.append({
                "line_number":
                    line_number,
                "text":
                    stripped,
                "reason":
                    reason,
            })
            continue

        kept.append(
            line
        )

    cleaned = clean_text(
        "\n".join(
            kept
        )
    )

    # Fail closed on cleaning itself.
    # Since the cleaner is only supposed to remove UI lines,
    # an empty result means something went wrong: retain everything.
    cleaning_fallback = False

    if normalized and not cleaned:
        cleaned = normalized
        removed = []
        cleaning_fallback = True

    audit = {
        "policy":
            "CONSERVATIVE_CTRL_A_V1",
        "ambiguous_lines_retained":
            True,
        "summarization_or_rewrite":
            False,
        "boundary_trimming":
            False,
        "removed_line_count":
            len(removed),
        "removed_lines":
            removed,
        "cleaning_fallback":
            cleaning_fallback,
        "input_character_count":
            len(normalized),
        "output_character_count":
            len(cleaned),
    }

    return cleaned, audit


def html_to_text(html):
    parser = VisibleTextParser()
    parser.feed(html)
    return clean_text("".join(parser.parts))


def detect_sections(text):
    """
    This is structural detection only.
    It DOES NOT decide P0/P1/P2/P3.
    """
    heading_patterns = {
        "responsibilities": [
            r"^responsibilities$",
            r"^what you(?:'|’)ll do$",
            r"^what you will do$",
            r"^the role$",
            r"^your responsibilities$",
            r"^key responsibilities$",

            r"^main job tasks(?:\s*&\s*|\s+and\s+)responsibilities$",
            r"^job tasks(?:\s*&\s*|\s+and\s+)responsibilities$",
            r"^main job tasks$",
            r"^job responsibilities(?:\s*&\s*|\s+and\s+)duties$"
        ],
        "qualifications": [
            r"^qualifications$",
            r"^requirements$",
            r"^what you(?:'|’)ll need$",
            r"^what you will need$",
            r"^minimum qualifications$",
            r"^minimum requirements$",
            r"^required qualifications$",
            r"^education\s*(?:&|and)\s*experience$",
            r"^key competencies$",
            r"^core competencies$",
            r"^professional competencies$"
        ],
        "preferred": [
            r"^preferred requirements$",
            r"^preferred qualifications$",
            r"^preferred experience$",
            r"^nice to have$",
            r"^nice-to-have$",
            r"^bonus$"
        ],
        "education": [
            r"^education$",
            r"^education requirements$"
        ],
        "benefits": [
            r"^benefits$",
            r"^what we offer$",
            r"^compensation and benefits$"
        ],
        "about": [
            r"^about us$",
            r"^about the company$",
            r"^who we are$"
        ]
    }

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    hits = []

    for i, line in enumerate(lines):
        candidate = line.strip(" :.-").lower()

        for section, patterns in heading_patterns.items():
            if any(re.fullmatch(p, candidate, re.I) for p in patterns):
                hits.append({
                    "line_index": i,
                    "heading": line,
                    "section_type": section
                })

    return hits


def basic_metadata(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    return {
        "character_count": len(text),
        "word_count": len(re.findall(r"\b\w+\b", text)),
        "line_count": len(lines),
        "detected_section_headings": detect_sections(text)
    }

#
# URL ingestion policy:
# - Prefer schema.org JobPosting.description when it can be tied
#   deterministically to the current requisition.
# - Never feed an entire careers/aggregator page downstream merely
#   because the page contains enough visible text.
# - Cookie/consent/login/access interstitials fail closed.
# - When structured JobPosting data is unavailable, retain only a
#   bounded job-body region anchored by ordinary JD headings.
# - No site/company-specific rules.


def structured_jobposting_candidates(html):
    parser = IdentityHTMLParser()

    try:
        parser.feed(
            html
        )
    except Exception:
        return [], {
            "parser_error":
                True,
            "candidate_count":
                0,
        }

    candidates = []
    seen = set()

    context_text = clean_text(
        " ".join(
            list(
                getattr(
                    parser,
                    "page_title_parts",
                    [],
                )
            )
            + list(
                getattr(
                    parser,
                    "h1_values",
                    [],
                )
            )
        )
    )

    context_key = identity_key(
        context_text
    )

    for block in getattr(
        parser,
        "ld_json_blocks",
        [],
    ):
        try:
            payload = json.loads(
                block
            )
        except Exception:
            continue

        for obj in iter_json_objects(
            payload
        ):
            if not is_jobposting_object(
                obj
            ):
                continue

            raw_description = str(
                obj.get(
                    "description"
                )
                or ""
            ).strip()

            if not raw_description:
                continue

            description = html_to_text(
                raw_description
            )

            if len(
                description
            ) < 150:
                continue

            title = clean_text(
                str(
                    obj.get(
                        "title"
                    )
                    or ""
                )
            )

            hiring = obj.get(
                "hiringOrganization"
            )

            company = ""

            if isinstance(
                hiring,
                dict,
            ):
                company = clean_text(
                    str(
                        hiring.get(
                            "name"
                        )
                        or ""
                    )
                )

            elif isinstance(
                hiring,
                str,
            ):
                company = clean_text(
                    hiring
                )

            key = (
                identity_key(
                    company
                ),
                identity_key(
                    title
                ),
                description.casefold(),
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            title_confirmed = bool(
                title
                and identity_key(
                    title
                )
                in context_key
            )

            company_confirmed = bool(
                company
                and identity_key(
                    company
                )
                in context_key
            )

            candidates.append({
                "company":
                    company,
                "title":
                    title,
                "description":
                    description,
                "title_confirmed":
                    title_confirmed,
                "company_confirmed":
                    company_confirmed,
                "context_score":
                    int(
                        title_confirmed
                    )
                    + int(
                        company_confirmed
                    ),
            })

    return candidates, {
        "parser_error":
            False,
        "candidate_count":
            len(
                candidates
            ),
        "page_context":
            context_text,
    }


def select_structured_jobposting_body(
    html,
):
    candidates, audit = (
        structured_jobposting_candidates(
            html
        )
    )

    if not candidates:
        return None, {
            **audit,
            "selection":
                "NONE",
        }

    if len(
        candidates
    ) == 1:
        chosen = candidates[
            0
        ]

        return chosen[
            "description"
        ], {
            **audit,
            "selection":
                "ONLY_JOBPOSTING",
            "company":
                chosen[
                    "company"
                ],
            "title":
                chosen[
                    "title"
                ],
            "context_score":
                chosen[
                    "context_score"
                ],
        }

    ranked = sorted(
        candidates,
        key=lambda row:
            row[
                "context_score"
            ],
        reverse=True,
    )

    best_score = ranked[
        0
    ][
        "context_score"
    ]

    best = [
        row
        for row in ranked
        if row[
            "context_score"
        ] == best_score
    ]

    if (
        best_score >= 1
        and len(
            best
        ) == 1
    ):
        chosen = best[
            0
        ]

        return chosen[
            "description"
        ], {
            **audit,
            "selection":
                "UNIQUE_CONTEXT_MATCH",
            "company":
                chosen[
                    "company"
                ],
            "title":
                chosen[
                    "title"
                ],
            "context_score":
                chosen[
                    "context_score"
                ],
        }

    return None, {
        **audit,
        "selection":
            "AMBIGUOUS_JOBPOSTINGS",
        "best_context_score":
            best_score,
    }


def visible_page_looks_like_interstitial(
    text,
):
    value = clean_text(
        text
    ).casefold()

    interstitial_patterns = [
        r"\baccept all cookies\b",
        r"\breject all cookies\b",
        r"\bmanage cookie preferences\b",
        r"\bcookie preferences\b",
        r"\bprivacy choices\b",
        r"\bconsent preferences\b",
        r"\benable javascript\b",
        r"\baccess denied\b",
        r"\bverify you are human\b",
        r"\bcaptcha\b",
        r"\bsign in to continue\b",
        r"\blog in to continue\b",
    ]

    job_patterns = [
        r"\bresponsibilities\b",
        r"\brequired qualifications\b",
        r"\bminimum qualifications\b",
        r"\brequirements\b",
        r"\bposition summary\b",
        r"\bjob summary\b",
        r"\bexperience\b",
    ]

    interstitial_hits = sum(
        bool(
            re.search(
                pattern,
                value,
                re.I,
            )
        )
        for pattern
        in interstitial_patterns
    )

    job_hits = sum(
        bool(
            re.search(
                pattern,
                value,
                re.I,
            )
        )
        for pattern
        in job_patterns
    )

    return (
        interstitial_hits >= 1
        and job_hits == 0
    ), {
        "interstitial_signal_count":
            interstitial_hits,
        "job_signal_count":
            job_hits,
    }


def bounded_visible_job_body(
    text,
):
    cleaned, cleaning_audit = (
        conservative_ctrl_a_clean(
            text
        )
    )

    lines = [
        clean_text(
            line
        )
        for line in cleaned.splitlines()
        if clean_text(
            line
        )
    ]

    start_patterns = [
        r"^position summary$",
        r"^job summary$",
        r"^role summary$",
        r"^job description$",
        r"^about the role$",
        r"^the role$",
        r"^responsibilities$",
        r"^key responsibilities$",
        r"^your responsibilities$",
        r"^what you(?:'|’)ll do$",
        r"^what you will do$",
        r"^essential functions$",
        r"^primary duties$",
    ]

    stop_patterns = [
        r"^similar jobs$",
        r"^related jobs$",
        r"^recommended jobs$",
        r"^more jobs$",
        r"^other jobs$",
        r"^apply instructions$",
        r"^create free account$",
        r"^already have an account\??(?:\s+log in)?$",
        r"^sign up now(?:\s+access later)?$",
        r"^please log in or sign up to report this job\.?$",
        r"^what you need to know about .+ tech scene$",
        r"^key facts about .+ tech$",
        r"^©\s*\d{4}\b.*$",
    ]

    start = None

    for i, line in enumerate(
        lines
    ):
        candidate = line.strip(
            " :.-"
        )

        if any(
            re.fullmatch(
                pattern,
                candidate,
                re.I,
            )
            for pattern
            in start_patterns
        ):
            start = i
            break

    if start is None:
        return None, {
            "selection":
                "NO_JOB_BODY_ANCHOR",
            "cleaning_audit":
                cleaning_audit,
        }

    end = len(
        lines
    )

    for i in range(
        start + 1,
        len(
            lines
        ),
    ):
        candidate = lines[
            i
        ].strip(
            " :.-"
        )

        if any(
            re.fullmatch(
                pattern,
                candidate,
                re.I,
            )
            for pattern
            in stop_patterns
        ):
            end = i
            break

    body = clean_text(
        "\n".join(
            lines[
                start:end
            ]
        )
    )

    job_signal_count = sum(
        bool(
            re.search(
                pattern,
                body,
                re.I,
            )
        )
        for pattern
        in (
            r"\bresponsibilit",
            r"\bqualifications?\b",
            r"\brequirements?\b",
            r"\bexperience\b",
            r"\bskills?\b",
        )
    )

    if (
        len(
            body
        ) < 150
        or job_signal_count < 2
    ):
        return None, {
            "selection":
                "INSUFFICIENT_BOUNDED_JOB_BODY",
            "character_count":
                len(
                    body
                ),
            "job_signal_count":
                job_signal_count,
            "cleaning_audit":
                cleaning_audit,
        }

    return body, {
        "selection":
            "BOUNDED_VISIBLE_JOB_BODY",
        "start_line":
            start,
        "end_line_exclusive":
            end,
        "character_count":
            len(
                body
            ),
        "job_signal_count":
            job_signal_count,
        "cleaning_audit":
            cleaning_audit,
    }




def _ingest_url_resolved(url):
    ats = probe_ats(
        url
    )

    ats_detection = ensure_ats_behavior_profile(
        ats.get(
            "final_detection"
        ),
        unknown_reason=(
            "ATS could not be resolved from job/application URL evidence."
        ),
    )

    try:
        page = fetch_page(
            url
        )

    except Exception as exc:
        return {
            "status":
                "NEEDS_MANUAL_JD",
            "source_type":
                "url",
            "source_url":
                url,
            "ats":
                ats_detection,
            "fetch_error":
                f"{type(exc).__name__}: {exc}",
            "raw_jd_text":
                None,
            "metadata":
                None,
            "instruction":
                (
                    "URL could not be fetched. Supply the JD text directly. "
                    "Do not infer or fabricate missing job-description content."
                ),
        }

    full_visible_text = html_to_text(
        page[
            "html"
        ]
    )

    identity_evidence = (
        extract_identity_evidence(
            full_visible_text,
            html=page[
                "html"
            ],
        )
    )

    identity_evidence = augment_platform_identity(
        identity_evidence,
        platform=ats_detection.get(
            "platform"
        ),
        html_source=page[
            "html"
        ],
    )

    # Workday public careers pages are frequently JavaScript shells.
    # Resolve the canonical current requisition from the public CXS feed
    # when possible. If that cannot be proven, fail closed instead of
    # treating corporate/footer boilerplate as the job description.
    if (
        ats_detection.get(
            "platform"
        )
        == "Workday Recruiting"
    ):
        workday_job, workday_audit = (
            fetch_workday_public_job(
                url
            )
        )

        if not workday_job:
            return {
                "status":
                    "NEEDS_MANUAL_JD",

                "source_type":
                    "url",

                "source_url":
                    url,

                "final_url":
                    page[
                        "final_url"
                    ],

                "ats":
                    ats_detection,

                "raw_jd_text":
                    None,

                "identity_evidence":
                    identity_evidence,

                "metadata":
                    None,

                "url_extraction_audit":
                    {
                        "policy":
                            "CAREEROPS_STRUCTURED_URL_JD_V1",

                        "mode":
                            "WORKDAY_PUBLIC_JOB_UNRESOLVED",

                        "workday":
                            workday_audit,

                        "whole_visible_page_used_as_jd":
                            False,

                        "interstitial_accepted_as_jd":
                            False,
                    },

                "instruction":
                    (
                        "Workday page was fetched, but Career-Ops could not "
                        "prove the current requisition body through the public "
                        "job feed. Supply the JD text directly."
                    ),
            }

        if workday_job.get(
            "position"
        ):
            identity_evidence = identity_apply_high(
                identity_evidence,
                "position",
                workday_job[
                    "position"
                ],
                "WORKDAY_PUBLIC_JOB_FEED",
            )

        if workday_job.get(
            "title"
        ):
            identity_evidence = identity_apply_high(
                identity_evidence,
                "position",
                workday_job[
                    "title"
                ],
                "WORKDAY_PUBLIC_JOB_FEED",
            )

        if workday_job.get(
            "company"
        ):
            identity_evidence = identity_apply_high(
                identity_evidence,
                "company",
                workday_job[
                    "company"
                ],
                "WORKDAY_PUBLIC_JOB_FEED",
            )

        workday_body = trim_post_jd_application_tail(
            workday_job[
                "body"
            ]
        )

        return {
            "status":
                "INGESTED",

            "source_type":
                "url",

            "source_url":
                url,

            "final_url":
                page[
                    "final_url"
                ],

            "ats":
                ats_detection,

            "raw_jd_text":
                workday_body,

            "identity_evidence":
                normalize_identity_entities(
                    identity_evidence
                ),

            "metadata":
                basic_metadata(
                    workday_body
                ),

            "url_extraction_audit":
                {
                    "policy":
                        "CAREEROPS_STRUCTURED_URL_JD_V1",

                    "mode":
                        "WORKDAY_PUBLIC_JOB_FEED",

                    "workday":
                        workday_audit,

                    "whole_visible_page_used_as_jd":
                        False,

                    "interstitial_accepted_as_jd":
                        False,
                },
        }

    # First choice: schema.org JobPosting.description.
    structured_body, structured_audit = (
        select_structured_jobposting_body(
            page[
                "html"
            ]
        )
    )

    if structured_body:
        structured_body = trim_post_jd_application_tail(
            html_entity_decode(
                structured_body
            )
        )

        identity_evidence = normalize_identity_entities(
            identity_evidence
        )

        return {
            "status":
                "INGESTED",
            "source_type":
                "url",
            "source_url":
                url,
            "final_url":
                page[
                    "final_url"
                ],
            "ats":
                ats_detection,
            "raw_jd_text":
                structured_body,
            "identity_evidence":
                identity_evidence,
            "metadata":
                basic_metadata(
                    structured_body
                ),
            "url_extraction_audit":
                {
                    "policy":
                        "CAREEROPS_STRUCTURED_URL_JD_V1",
                    "mode":
                        "STRUCTURED_JOBPOSTING_DESCRIPTION",
                    "structured":
                        structured_audit,
                    "whole_visible_page_used_as_jd":
                        False,
                    "interstitial_accepted_as_jd":
                        False,
                },
        }

    interstitial, interstitial_audit = (
        visible_page_looks_like_interstitial(
            full_visible_text
        )
    )

    if interstitial:
        return {
            "status":
                "NEEDS_MANUAL_JD",
            "source_type":
                "url",
            "source_url":
                url,
            "final_url":
                page[
                    "final_url"
                ],
            "ats":
                ats_detection,
            "raw_jd_text":
                None,
            "identity_evidence":
                identity_evidence,
            "metadata":
                None,
            "url_extraction_audit":
                {
                    "policy":
                        "CAREEROPS_STRUCTURED_URL_JD_V1",
                    "mode":
                        "INTERSTITIAL_REJECTED",
                    "structured":
                        structured_audit,
                    "interstitial":
                        interstitial_audit,
                    "whole_visible_page_used_as_jd":
                        False,
                    "interstitial_accepted_as_jd":
                        False,
                },
            "instruction":
                (
                    "Fetched URL appears to be a cookie, consent, login, "
                    "access, or verification interstitial rather than a "
                    "provable job description. Supply the JD text directly."
                ),
        }

    # Conservative fallback for pages without usable structured JD data.
    bounded_body, bounded_audit = (
        bounded_visible_job_body(
            full_visible_text
        )
    )

    if bounded_body:
        bounded_body = trim_post_jd_application_tail(
            bounded_body
        )

    if not bounded_body:
        return {
            "status":
                "NEEDS_MANUAL_JD",
            "source_type":
                "url",
            "source_url":
                url,
            "final_url":
                page[
                    "final_url"
                ],
            "ats":
                ats_detection,
            "raw_jd_text":
                None,
            "identity_evidence":
                identity_evidence,
            "metadata":
                None,
            "url_extraction_audit":
                {
                    "policy":
                        "CAREEROPS_STRUCTURED_URL_JD_V1",
                    "mode":
                        "NO_PROVABLE_JOB_BODY",
                    "structured":
                        structured_audit,
                    "interstitial":
                        interstitial_audit,
                    "bounded_visible":
                        bounded_audit,
                    "whole_visible_page_used_as_jd":
                        False,
                    "interstitial_accepted_as_jd":
                        False,
                },
            "instruction":
                (
                    "URL was fetched, but Career-Ops could not isolate a "
                    "trustworthy current-job description from the page. "
                    "Supply the JD text directly rather than using page chrome."
                ),
        }

    return {
        "status":
            "INGESTED",
        "source_type":
            "url",
        "source_url":
            url,
        "final_url":
            page[
                "final_url"
            ],
        "ats":
            ats_detection,
        "raw_jd_text":
            bounded_body,
        "identity_evidence":
            identity_evidence,
        "metadata":
            basic_metadata(
                bounded_body
            ),
        "url_extraction_audit":
            {
                "policy":
                    "CAREEROPS_STRUCTURED_URL_JD_V1",
                "mode":
                    "BOUNDED_VISIBLE_JOB_BODY",
                "structured":
                    structured_audit,
                "interstitial":
                    interstitial_audit,
                "bounded_visible":
                    bounded_audit,
                "whole_visible_page_used_as_jd":
                    False,
                "interstitial_accepted_as_jd":
                    False,
            },
    }


def ingest_text(text, source_type, source_name=None, url=None):
    # Preserve the source supplied to ingestion before any whitespace
    # normalization or conservative careers-page chrome removal.
    #
    # In orchestrated production runs the exact input file is also
    # already retained at run_root/input_jd.txt.
    original_text = str(
        text or ""
    )

    original_artifact = (
        RUNTIME
        / "jd_source_original.txt"
    )

    original_artifact.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_artifact.write_text(
        original_text,
        encoding="utf-8",
    )

    is_html = bool(re.search(r'<(?:html|body|div|p|script|h[1-6])\b', original_text, re.I))
    normalized_text = html_to_text(original_text) if is_html else clean_text(original_text)

    if not normalized_text:
        raise ValueError(
            "JD text is empty."
        )

    cleaned_text, cleaning_audit = (
        conservative_ctrl_a_clean(
            normalized_text
        )
    )

    if not cleaned_text:
        raise ValueError(
            "JD text is empty after conservative cleaning."
        )

    if len(cleaned_text) < 150 or len(re.findall(r'\b\w+\b',cleaned_text)) < 25:
        raise ValueError('JD source contains no substantive job description; provide the full current JD.')
    identity_evidence = extract_identity_evidence(cleaned_text, html=original_text if is_html else None)
    mime_metadata = None
    mime_source = os.environ.get('CAREEROPS_SOURCE_MIME_METADATA')
    if mime_source:
        metadata_source = Path(mime_source)
        if not metadata_source.is_file():
            raise ValueError('Original clipboard MIME evidence is missing.')
        mime_metadata = json.loads(metadata_source.read_text(encoding='utf-8'))
        if mime_metadata.get('schema') != 'windows-clipboard-mime-v1':
            raise ValueError('Unsupported clipboard MIME source metadata.')
        (RUNTIME/'jd_source_clipboard_mime.json').write_text(json.dumps(mime_metadata,indent=2,ensure_ascii=False)+'\n')
    cleaning_audit['input_representation'] = 'HTML' if is_html else 'TEXT'
    cleaning_audit['html_visible_text_extracted'] = is_html
    cleaning_audit['clipboard_mime_evidence'] = str(RUNTIME/'jd_source_clipboard_mime.json') if mime_metadata else None

    result = {
        "status":
            "INGESTED",
        "source_type":
            source_type,
        "source_name":
            source_name,
        "source_url":
            url,

        # Backward-compatible downstream contract:
        # requirement extraction already reads raw_jd_text.
        # It now receives the conservatively cleaned JD.
        "raw_jd_text":
            cleaned_text,

        # Audit pointer only. The full original text is intentionally
        # kept out of jd_intake.json so writer-facing packets do not
        # duplicate dirty browser chrome.
        "original_source_artifact":
            str(
                original_artifact
            ),

        "cleaning_audit":
            cleaning_audit,

        "identity_evidence":
            identity_evidence,

        "metadata":
            basic_metadata(
                cleaned_text
            ),
    }

    if url:
        ats = probe_ats(
            url
        )

        result["ats"] = ensure_ats_behavior_profile(
            ats.get(
                "final_detection"
            ),
            unknown_reason=(
                "ATS could not be resolved from job/application URL evidence."
            ),
        )

    else:
        result["ats"] = ensure_ats_behavior_profile(
            None,
            unknown_reason=(
                "No job/application URL supplied."
            ),
        )

    return result



def ingest_url(url):
    from careerops_url_normalization import normalize_job_url
    original = str(url or '')
    try:
        normalized = normalize_job_url(original)
    except ValueError as exc:
        return {'status': 'NEEDS_MANUAL_JD', 'source_type': 'url', 'source_url': original,
                'original_source_url': original, 'raw_jd_text': None, 'metadata': None,
                'instruction': str(exc), 'url_normalization': {'status': 'FAIL_CLOSED', 'reason': str(exc)}}
    result = _ingest_url_resolved(normalized)
    result['original_source_url'] = original
    result['url_normalization'] = {'status': 'NORMALIZED' if normalized != original else 'UNCHANGED',
                                   'original': original, 'normalized': normalized}
    return result


def main():
    parser = argparse.ArgumentParser(
        description="CareerOps Resume Engine JD ingestion layer"
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--url",
        help="Job posting/application URL"
    )

    group.add_argument(
        "--file",
        help="Path to a plain-text or Markdown JD"
    )

    group.add_argument(
        "--stdin",
        action="store_true",
        help="Read pasted JD text from stdin"
    )

    parser.add_argument(
        "--application-url",
        help=(
            "Optional application URL when using --file or --stdin. "
            "Used only for ATS detection."
        )
    )

    args = parser.parse_args()

    if args.url:
        result = ingest_url(args.url)

    elif args.file:
        p = Path(args.file).expanduser()

        if not p.exists():
            raise SystemExit(f"File not found: {p}")

        result = ingest_text(
            p.read_text(encoding="utf-8", errors="replace"),
            source_type="file",
            source_name=str(p),
            url=args.application_url
        )

    else:
        result = ingest_text(
            sys.stdin.read(),
            source_type="stdin",
            source_name="pasted_jd",
            url=args.application_url
        )

    result["ingested_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["schema_version"] = "jd-intake-v1"

    output = RUNTIME / "jd_intake.json"
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("JD INGESTION:", result["status"])
    print("SOURCE TYPE:", result["source_type"])

    ats = result.get("ats") or {}
    print(
        "ATS:",
        ats.get("platform", "UNKNOWN_ATS"),
        "|",
        ats.get("confidence", "UNKNOWN")
    )

    metadata = result.get("metadata")

    if metadata:
        print("WORDS:", metadata["word_count"])
        print(
            "SECTION HEADINGS:",
            len(metadata["detected_section_headings"])
        )

    print("OUTPUT:", output.relative_to(ROOT))

    if result["status"] != "INGESTED":
        print("ACTION:", result.get("instruction"))
        raise SystemExit(3)


if __name__ == "__main__":
    main()
