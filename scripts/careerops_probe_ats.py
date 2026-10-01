#!/usr/bin/env python3

import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

from careerops_detect_ats import (detect as detect_url, VALID_PLATFORMS, attach_behavior_profile)

# Strong vendor fingerprints only.
# These are searched in HTML/source attributes, not ordinary job-description wording.
FINGERPRINTS = {
    "Workday Recruiting": [
        r"myworkdayjobs\.com",
        r"myworkdaysite\.com",
        r"/wday/",
        r"workdaycdn\.com"
    ],
    "Greenhouse": [
        r"boards\.greenhouse\.io",
        r"job-boards\.greenhouse\.io",
        r"greenhouse\.io/embed",
        r"greenhouse-job-board"
    ],
    "SAP SuccessFactors Recruiting": [
        r"successfactors\.com",
        r"career\d*\.successfactors",
        r"/sfcareer/"
    ],
    "Oracle Cloud HCM Recruiting": [
        r"oraclecloud\.com.*candidateexperience",
        r"/hcmui/candidateexperience",
        r"candidateexperience"
    ],
    "iCIMS": [
        r"icims\.com",
        r"careers-[^\"']+\.icims\.com",
        r"icims_iframe"
    ],
    "Avature": [
        r"avature\.net",
        r"avature\.com"
    ],
    "Eightfold AI": [
        r"eightfold\.ai",
        r"eightfold\.com"
    ],
    "SmartRecruiters": [
        r"smartrecruiters\.com",
        r"jobs\.smartrecruiters"
    ],
    "Oracle Taleo": [
        r"taleo\.net",
        r"careersection"
    ],
    "Ashby": [
        r"ashbyhq\.com",
        r"jobs\.ashbyhq"
    ],
    "Lever": [
        r"jobs\.lever\.co",
        r"api\.lever\.co",
        r"lever-postings"
    ],
    "USAJobs / USA Staffing": [
        r"usajobs\.gov",
        r"usastaffing\.gov"
    ],
    "Phenom": [
        r"phenompeople\.com",
        r"phenom\.com"
    ],
    "UKG Pro Recruiting / UltiPro": [
        r"ultipro\.com",
        r"recruiting\d*\.ultipro",
        r"ukg\.com.*recruit"
    ],
    "PageUp": [
        r"pageuppeople\.com",
        r"pageup\.com"
    ],
    "Cornerstone Recruiting": [
        r"csod\.com",
        r"cornerstoneondemand"
    ],
    "Workable": [
        r"apply\.workable\.com",
        r"workable\.com/j/"
    ],
    "BambooHR Recruiting": [
        r"bamboohr\.com/careers",
        r"bamboohr\.com/jobs"
    ],
    "Jobvite": [
        r"jobs\.jobvite\.com",
        r"jobvite\.com"
    ],
    "ADP Recruiting / Recruiting Management": [
        r"workforcenow\.adp\.com",
        r"adp\.com.*recruitment"
    ],
    "Dayforce Recruiting": [
        r"dayforcehcm\.com",
        r"jobs\.dayforce"
    ],
    "Paylocity Recruiting": [
        r"recruiting\.paylocity\.com"
    ],
    "Paycom Recruiting": [
        r"paycomonline\.net"
    ],
    "PeopleAdmin / TalentEd": [
        r"peopleadmin\.com",
        r"tedk12\.com"
    ],
    "NEOGOV": [
        r"governmentjobs\.com",
        r"neogov\.com"
    ],
    "IBM Kenexa / BrassRing": [
        r"brassring\.com",
        r"kenexa\.com"
    ],
    "JazzHR": [
        r"applytojob\.com",
        r"jazz\.co"
    ],
    "Teamtailor": [
        r"teamtailor\.com"
    ],
    "Recruitee": [
        r"recruitee\.com"
    ],
    "Personio Recruiting": [
        r"jobs\.personio\.(com|de)",
        r"personio\.com.*career"
    ],
    "ClearCompany": [
        r"clearcompany\.com"
    ],
    "Paycor Recruiting": [
        r"recruiting\.paycor\.com"
    ],
    "Rippling Recruiting": [
        r"ats\.rippling\.com",
        r"rippling\.com.*jobs"
    ],
    "ApplicantPro": [
        r"applicantpro\.com"
    ],
    "ApplicantStack": [
        r"applicantstack\.com"
    ],
    "Breezy HR": [
        r"breezy\.hr"
    ],
    "Pinpoint": [
        r"pinpointhq\.com"
    ],
    "Comeet": [
        r"comeet\.com"
    ],
    "Zoho Recruit": [
        r"recruit\.zoho\.com",
        r"zohorecruit"
    ],
    "Bullhorn ATS": [
        r"bullhornstaffing\.com",
        r"bullhorn\.com"
    ],
    "CEIPAL": [
        r"ceipal\.com"
    ],
    "Recruit CRM": [
        r"recruitcrm\.io"
    ],
    "CATS ATS": [
        r"catsone\.com"
    ],
    "PCRecruiter": [
        r"pcrecruiter\.net"
    ],
    "JobScore": [
        r"careers\.jobscore\.com"
    ],
    "Hireology": [
        r"hireology\.com"
    ],
    "TalentReef": [
        r"talentreef\.com"
    ],
    "Fountain": [
        r"fountain\.com"
    ],
    "Paradox": [
        r"paradox\.ai",
        r"paradox\.olivia"
    ],
    "Radancy / Symphony Talent": [
        r"radancy\.com",
        r"symphonytalent\.com"
    ]
}

for platform in FINGERPRINTS:
    if platform not in VALID_PLATFORMS:
        raise RuntimeError(
            f"Fingerprint platform missing from ATS roster: {platform}"
        )


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml"
        }
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        final_url = response.geturl()
        status = getattr(response, "status", None)
        content_type = response.headers.get("Content-Type", "")

        # Enough for ATS fingerprints while preventing huge downloads.
        raw = response.read(3_000_000)

        charset = response.headers.get_content_charset() or "utf-8"
        try:
            html = raw.decode(charset, errors="replace")
        except LookupError:
            html = raw.decode("utf-8", errors="replace")

        return {
            "final_url": final_url,
            "status": status,
            "content_type": content_type,
            "html": html
        }


def scan_html(html):
    hits = []

    for platform, patterns in FINGERPRINTS.items():
        matched = []

        for pattern in patterns:
            if re.search(pattern, html, re.I):
                matched.append(pattern)

        if matched:
            hits.append({
                "platform": platform,
                "patterns": matched,
                "hit_count": len(matched)
            })

    hits.sort(
        key=lambda x: (x["hit_count"], len(x["patterns"])),
        reverse=True
    )

    return hits


def choose(initial, final, html_hits):
    # Strongest evidence: direct/final ATS-host URL.
    candidates = []

    if initial["platform"] != "UNKNOWN_ATS":
        candidates.append({
            "source": "INPUT_URL",
            "platform": initial["platform"],
            "confidence": initial["confidence"],
            "priority": 100 if initial["confidence"] == "EXACT" else 80,
            "evidence": initial.get("evidence")
        })

    if final["platform"] != "UNKNOWN_ATS":
        candidates.append({
            "source": "FINAL_REDIRECT_URL",
            "platform": final["platform"],
            "confidence": final["confidence"],
            "priority": 110 if final["confidence"] == "EXACT" else 90,
            "evidence": final.get("evidence")
        })

    # Page-source fingerprints are strong but slightly below vendor-host evidence.
    for h in html_hits:
        candidates.append({
            "source": "HTML_FINGERPRINT",
            "platform": h["platform"],
            "confidence": "HIGH_CONFIDENCE",
            "priority": 70 + min(h["hit_count"], 5),
            "evidence": h["patterns"]
        })

    if not candidates:
        return attach_behavior_profile({
            "platform": "UNKNOWN_ATS",
            "confidence": "UNKNOWN",
            "reason": (
                "No reliable URL, redirect, or HTML ATS fingerprint found."
            ),
            "evidence": []
        })

    candidates.sort(key=lambda x: x["priority"], reverse=True)
    best = candidates[0]

    # Agreement across multiple evidence sources strengthens result.
    agreeing = [
        c for c in candidates
        if c["platform"] == best["platform"]
    ]

    sources = sorted(set(c["source"] for c in agreeing))

    confidence = best["confidence"]

    if len(sources) >= 2 and confidence != "EXACT":
        confidence = "HIGH_CONFIDENCE"

    return attach_behavior_profile({
        "platform": best["platform"],
        "confidence": confidence,
        "reason": "ATS identified from strongest available evidence",
        "evidence_sources": sources,
        "evidence": agreeing,
        "alternatives": [
            c for c in candidates
            if c["platform"] != best["platform"]
        ]
    })


def probe(url):
    initial = detect_url(url)

    result = {
        "input_url": url,
        "initial_url_detection": initial
    }

    try:
        page = fetch(url)
    except Exception as e:
        result["fetch"] = {
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }

        result["final_detection"] = attach_behavior_profile({
            "platform": initial["platform"],
            "confidence": initial["confidence"],
            "reason": (
                "Page fetch failed; using URL evidence only."
            ),
            "evidence": initial.get("evidence", [])
        })

        return result

    final_detection = detect_url(page["final_url"])
    html_hits = scan_html(page["html"])

    result["fetch"] = {
        "success": True,
        "status": page["status"],
        "content_type": page["content_type"],
        "final_url": page["final_url"],
        "redirected": page["final_url"] != initial.get(
            "normalized_url", url
        ),
        "html_bytes_scanned": len(page["html"].encode(
            "utf-8", errors="ignore"
        ))
    }

    result["final_url_detection"] = final_detection
    result["html_fingerprints"] = html_hits[:10]
    result["final_detection"] = choose(
        initial,
        final_detection,
        html_hits
    )

    return result


def main():
    if len(sys.argv) != 2:
        print(
            'Usage: python3 scripts/careerops_probe_ats.py "<JOB_URL>"',
            file=sys.stderr
        )
        raise SystemExit(2)

    result = probe(sys.argv[1])

    out_dir = Path(
        "data/careerops-engine/runtime"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "last_ats_probe.json").write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
