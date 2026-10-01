#!/usr/bin/env python3

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "config/ats_platforms.json"
BEHAVIOR_INVENTORY = (
    ROOT / "config/ats_behavior_profiles.json"
)

platforms = json.loads(ROSTER.read_text())["platforms"]
VALID_PLATFORMS = {x["platform"] for x in platforms}

behavior_inventory = json.loads(
    BEHAVIOR_INVENTORY.read_text(encoding="utf-8")
)

BEHAVIOR_FAMILIES = behavior_inventory["behavior_families"]

BEHAVIOR_PROFILES = {
    item["platform"]: item
    for item in behavior_inventory["platform_profiles"]
}

UNKNOWN_BEHAVIOR_PROFILE = behavior_inventory["unknown_profile"]

_missing_profiles = VALID_PLATFORMS - set(BEHAVIOR_PROFILES)
_extra_profiles = set(BEHAVIOR_PROFILES) - VALID_PLATFORMS

if _missing_profiles or _extra_profiles:
    raise RuntimeError(
        "ATS behavior inventory does not match canonical roster. "
        f"missing={sorted(_missing_profiles)} "
        f"extra={sorted(_extra_profiles)}"
    )

for _platform, _profile in BEHAVIOR_PROFILES.items():
    _family = _profile["behavior_family"]

    if _family not in BEHAVIOR_FAMILIES:
        raise RuntimeError(
            f"Undefined ATS behavior family for {_platform}: {_family}"
        )

_unknown_family = UNKNOWN_BEHAVIOR_PROFILE["behavior_family"]

if _unknown_family not in BEHAVIOR_FAMILIES:
    raise RuntimeError(
        "UNKNOWN_ATS references undefined behavior family: "
        f"{_unknown_family}"
    )


# Strong vendor-hosted URL signatures only.
# Do NOT add speculative employer-specific mappings here.
SIGNATURES = [
    # Workday
    {
        "platform": "Workday Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)myworkdayjobs\.com$",
            r"(^|\.)myworkdaysite\.com$"
        ],
        "paths": []
    },

    # Greenhouse
    {
        "platform": "Greenhouse",
        "confidence": "EXACT",
        "hosts": [
            r"^boards\.greenhouse\.io$",
            r"^job-boards\.greenhouse\.io$"
        ],
        "paths": []
    },

    # SAP SuccessFactors
    {
        "platform": "SAP SuccessFactors Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)successfactors\.com$"
        ],
        "paths": []
    },

    # Oracle Cloud HCM
    {
        "platform": "Oracle Cloud HCM Recruiting",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)oraclecloud\.com$"
        ],
        "paths": [
            r"/hcmUI/CandidateExperience",
            r"/CandidateExperience"
        ]
    },

    # iCIMS
    {
        "platform": "iCIMS",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)icims\.com$"
        ],
        "paths": []
    },

    # Avature
    {
        "platform": "Avature",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)avature\.net$"
        ],
        "paths": []
    },

    # Eightfold
    {
        "platform": "Eightfold AI",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)eightfold\.ai$"
        ],
        "paths": []
    },

    # SmartRecruiters
    {
        "platform": "SmartRecruiters",
        "confidence": "EXACT",
        "hosts": [
            r"^jobs\.smartrecruiters\.com$"
        ],
        "paths": []
    },

    # Oracle Taleo
    {
        "platform": "Oracle Taleo",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)taleo\.net$"
        ],
        "paths": []
    },

    # Ashby
    {
        "platform": "Ashby",
        "confidence": "EXACT",
        "hosts": [
            r"^jobs\.ashbyhq\.com$"
        ],
        "paths": []
    },

    # Lever
    {
        "platform": "Lever",
        "confidence": "EXACT",
        "hosts": [
            r"^jobs\.lever\.co$"
        ],
        "paths": []
    },

    # USAJobs
    {
        "platform": "USAJobs / USA Staffing",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)usajobs\.gov$"
        ],
        "paths": []
    },

    # Phenom
    {
        "platform": "Phenom",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)phenompeople\.com$"
        ],
        "paths": []
    },

    # UKG / UltiPro
    {
        "platform": "UKG Pro Recruiting / UltiPro",
        "confidence": "EXACT",
        "hosts": [
            r"^recruiting\.ultipro\.com$",
            r"^recruiting2\.ultipro\.com$",
            r"(^|\.)ukg\.com$"
        ],
        "paths": []
    },

    # PageUp
    {
        "platform": "PageUp",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)pageuppeople\.com$"
        ],
        "paths": []
    },

    # Cornerstone
    {
        "platform": "Cornerstone Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)csod\.com$"
        ],
        "paths": []
    },

    # Workable
    {
        "platform": "Workable",
        "confidence": "EXACT",
        "hosts": [
            r"^apply\.workable\.com$"
        ],
        "paths": []
    },

    # BambooHR
    {
        "platform": "BambooHR Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)bamboohr\.com$"
        ],
        "paths": [
            r"/careers",
            r"/jobs"
        ]
    },

    # Jobvite
    {
        "platform": "Jobvite",
        "confidence": "EXACT",
        "hosts": [
            r"^jobs\.jobvite\.com$"
        ],
        "paths": []
    },

    # ADP
    {
        "platform": "ADP Recruiting / Recruiting Management",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"^workforcenow\.adp\.com$",
            r"(^|\.)adp\.com$"
        ],
        "paths": [
            r"/recruitment",
            r"/mascsr"
        ]
    },

    # Dayforce
    {
        "platform": "Dayforce Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"^jobs\.dayforcehcm\.com$"
        ],
        "paths": []
    },

    # Paylocity
    {
        "platform": "Paylocity Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"^recruiting\.paylocity\.com$"
        ],
        "paths": []
    },

    # Paycom
    {
        "platform": "Paycom Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)paycomonline\.net$"
        ],
        "paths": []
    },

    # PeopleAdmin / TalentEd
    {
        "platform": "PeopleAdmin / TalentEd",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)peopleadmin\.com$",
            r"(^|\.)tedk12\.com$"
        ],
        "paths": []
    },

    # NEOGOV
    {
        "platform": "NEOGOV",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)governmentjobs\.com$",
            r"(^|\.)neogov\.com$"
        ],
        "paths": []
    },

    # BrassRing
    {
        "platform": "IBM Kenexa / BrassRing",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)brassring\.com$"
        ],
        "paths": []
    },

    # JazzHR
    {
        "platform": "JazzHR",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)applytojob\.com$",
            r"(^|\.)jazz\.co$"
        ],
        "paths": []
    },

    # Teamtailor
    {
        "platform": "Teamtailor",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)teamtailor\.com$"
        ],
        "paths": []
    },

    # Recruitee
    {
        "platform": "Recruitee",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)recruitee\.com$"
        ],
        "paths": []
    },

    # Personio
    {
        "platform": "Personio Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)jobs\.personio\.com$",
            r"^jobs\.personio\.de$"
        ],
        "paths": []
    },

    # ClearCompany
    {
        "platform": "ClearCompany",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)clearcompany\.com$"
        ],
        "paths": [
            r"/careers",
            r"/jobs"
        ]
    },

    # Paycor
    {
        "platform": "Paycor Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"^recruiting\.paycor\.com$"
        ],
        "paths": []
    },

    # Rippling
    {
        "platform": "Rippling Recruiting",
        "confidence": "EXACT",
        "hosts": [
            r"^ats\.rippling\.com$"
        ],
        "paths": []
    },

    # ApplicantPro
    {
        "platform": "ApplicantPro",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)applicantpro\.com$"
        ],
        "paths": []
    },

    # ApplicantStack
    {
        "platform": "ApplicantStack",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)applicantstack\.com$"
        ],
        "paths": []
    },

    # Breezy
    {
        "platform": "Breezy HR",
        "confidence": "EXACT",
        "hosts": [
            r"(^|\.)breezy\.hr$"
        ],
        "paths": []
    },

    # Pinpoint
    {
        "platform": "Pinpoint",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)pinpointhq\.com$"
        ],
        "paths": []
    },

    # Comeet
    {
        "platform": "Comeet",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)comeet\.com$"
        ],
        "paths": []
    },

    # Zoho
    {
        "platform": "Zoho Recruit",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"^recruit\.zoho\.com$"
        ],
        "paths": []
    },

    # CEIPAL
    {
        "platform": "CEIPAL",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"^jobs\.ceipal\.com$",
            r"(^|\.)ceipal\.com$"
        ],
        "paths": []
    },

    # Recruit CRM
    {
        "platform": "Recruit CRM",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)recruitcrm\.io$"
        ],
        "paths": []
    },

    # CATS
    {
        "platform": "CATS ATS",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)catsone\.com$"
        ],
        "paths": []
    },

    # PCRecruiter
    {
        "platform": "PCRecruiter",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)pcrecruiter\.net$"
        ],
        "paths": []
    },

    # JobScore
    {
        "platform": "JobScore",
        "confidence": "EXACT",
        "hosts": [
            r"^careers\.jobscore\.com$"
        ],
        "paths": []
    },

    # Hireology
    {
        "platform": "Hireology",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"^careers\.hireology\.com$",
            r"(^|\.)hireology\.com$"
        ],
        "paths": []
    },

    # TalentReef
    {
        "platform": "TalentReef",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"^apply\.talentreef\.com$",
            r"(^|\.)talentreef\.com$"
        ],
        "paths": []
    },

    # Fountain
    {
        "platform": "Fountain",
        "confidence": "HIGH_CONFIDENCE",
        "hosts": [
            r"(^|\.)fountain\.com$"
        ],
        "paths": []
    }
]


def normalize_url(raw):
    raw = raw.strip()
    if not raw:
        return ""

    if "://" not in raw:
        raw = "https://" + raw

    return raw


def _detect_raw(url):
    raw = normalize_url(url)

    try:
        parsed = urlparse(raw)
    except Exception:
        parsed = None

    if not parsed or not parsed.hostname:
        return {
            "input_url": url,
            "platform": "UNKNOWN_ATS",
            "confidence": "UNKNOWN",
            "evidence": [],
            "reason": "Invalid or unparseable URL"
        }

    host = parsed.hostname.lower().strip(".")
    path = parsed.path or ""
    full = raw.lower()

    results = []

    for sig in SIGNATURES:
        if sig["platform"] not in VALID_PLATFORMS:
            raise RuntimeError(
                f"Signature platform absent from ATS roster: {sig['platform']}"
            )

        host_hits = [
            pattern for pattern in sig["hosts"]
            if re.search(pattern, host, re.I)
        ]

        path_hits = [
            pattern for pattern in sig["paths"]
            if re.search(pattern, path, re.I)
        ]

        if not host_hits:
            continue

        # When path signatures exist, require one for conservative matching
        # unless this is an exact vendor-owned host.
        if sig["paths"] and not path_hits:
            exact_vendor_tokens = (
                "oraclecloud.com",
                "adp.com",
                "bamboohr.com",
                "clearcompany.com"
            )

            if not any(host.endswith(x) for x in exact_vendor_tokens):
                continue

        score = {
            "EXACT": 100,
            "HIGH_CONFIDENCE": 80,
            "POSSIBLE": 50
        }.get(sig["confidence"], 0)

        results.append({
            "platform": sig["platform"],
            "confidence": sig["confidence"],
            "score": score,
            "host_matches": host_hits,
            "path_matches": path_hits
        })

    if not results:
        # Conservative token fallback only.
        token_candidates = []

        for p in platforms:
            name = p["platform"].lower()
            tokens = {
                t for t in re.findall(r"[a-z0-9]+", name)
                if len(t) >= 5
            }

            matched = sorted(t for t in tokens if t in full)

            if matched:
                token_candidates.append({
                    "platform": p["platform"],
                    "matched_tokens": matched
                })

        if len(token_candidates) == 1:
            c = token_candidates[0]

            return {
                "input_url": url,
                "normalized_url": raw,
                "hostname": host,
                "platform": c["platform"],
                "confidence": "POSSIBLE",
                "evidence": [
                    "Platform-name token appeared in URL",
                    *c["matched_tokens"]
                ],
                "reason": (
                    "Insufficient vendor-host evidence for exact identification. "
                    "Requires redirect/page-source/application-flow verification."
                )
            }

        return {
            "input_url": url,
            "normalized_url": raw,
            "hostname": host,
            "platform": "UNKNOWN_ATS",
            "confidence": "UNKNOWN",
            "evidence": [],
            "reason": (
                "No strong ATS URL signature found. "
                "Do not guess. Continue with redirect/page-source/application-flow detection."
            )
        }

    results.sort(key=lambda x: x["score"], reverse=True)

    best = results[0]

    return {
        "input_url": url,
        "normalized_url": raw,
        "hostname": host,
        "platform": best["platform"],
        "confidence": best["confidence"],
        "evidence": {
            "host_matches": best["host_matches"],
            "path_matches": best["path_matches"]
        },
        "alternatives": results[1:],
        "reason": "Matched known ATS vendor URL signature"
    }



def get_behavior_profile(platform):
    """
    Resolve a detected ATS platform to the canonical Career-Ops V2
    behavior profile.

    Every canonical ATS roster entry has an exact profile.
    Unresolved/unknown ATS values use the conservative UNKNOWN_ATS
    fallback. This function never invents employer-specific settings.
    """
    if platform in BEHAVIOR_PROFILES:
        return {
            "profile_source": "EXACT_PLATFORM",
            "profile": BEHAVIOR_PROFILES[platform]
        }

    return {
        "profile_source": "UNKNOWN_FALLBACK",
        "profile": UNKNOWN_BEHAVIOR_PROFILE
    }


def attach_behavior_profile(result):
    """
    Add ATS behavior intelligence without removing or changing any
    existing detector output fields.
    """
    enriched = dict(result)

    platform = enriched.get("platform") or "UNKNOWN_ATS"
    resolved = get_behavior_profile(platform)
    profile = resolved["profile"]

    enriched["behavior_profile_supported"] = True
    enriched["behavior_profile_source"] = resolved["profile_source"]
    enriched["behavior_family"] = profile["behavior_family"]
    enriched["simulation_profile"] = profile["simulation_profile"]
    enriched["known_dimensions"] = list(
        profile.get("known_dimensions", [])
    )
    enriched["feature_state"] = profile.get("feature_state")
    enriched["behavior_confidence"] = profile.get("confidence")
    enriched["never_assume"] = list(
        profile.get("never_assume", [])
    )
    enriched["behavior_profile"] = profile

    return enriched


def detect(url):
    """
    Public detector entrypoint.

    Detection remains deterministic and unchanged.
    V2 behavior intelligence is attached only after platform detection.
    """
    return attach_behavior_profile(_detect_raw(url))

def main():
    if len(sys.argv) != 2:
        print(
            'Usage: python3 scripts/careerops_detect_ats.py "<JOB_URL>"',
            file=sys.stderr
        )
        raise SystemExit(2)

    result = detect(sys.argv[1])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
