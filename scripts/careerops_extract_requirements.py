#!/usr/bin/env python3

import json
import os
import re
from pathlib import Path


from careerops_runtime import runtime_dir

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
INPUT = RUNTIME / 'jd_intake.json'
OUTPUT = RUNTIME / 'jd_requirements.json'


SECTION_PATTERNS = {
    "responsibilities": [
        r"roles (?:and|&) responsibilities",
        r"job responsibilities",
        r"accountabilities",
        r"about (?:the|this) role",
        r"(?:[\w]+[ &]+){1,5}analytics",
        r"(?:[\w]+[ &]+){1,5}analysis",
        r"data craft (?:and|&) practice",
        r"responsibilities",
        r"key responsibilities",
        r"primary responsibilities",
        r"your responsibilities",
        r"what you(?:'|’)ll do(?:\s+at\s+.+)?",
        r"what you will do(?:\s+at\s+.+)?",
        r"job summary",
        r"job description",
        r"the job",
        r"you(?:'|’)ll get to",
        r"specific duties and responsib(?:ilities|ilties)",
        r"duties and responsib(?:ilities|ilties)",
        r"essential duties and responsibilities",
        r"essential functions",
        r"primary duties/?essential functions",
        r"primary duties",
        r"job duties",
        r"the role",

        r"main job tasks(?:\s*&\s*|\s+and\s+)responsibilities",
        r"job tasks(?:\s*&\s*|\s+and\s+)responsibilities",
        r"main job tasks",
        r"job responsibilities(?:\s*&\s*|\s+and\s+)duties"
    ],
    "required": [
        r"basic qualifications",
        r"what we(?:'|’)re looking for",
        r"what we are looking for",
        r"the essentials(?:\s*\([^)]{1,100}\))?",
        r"the (?:[^.!?:]{1,80} )?skill set",
        r"job requirements",
        r"experience (?:and|&) skills",
        r"experience and qualifications",
        r"required qualifications",
        r"required experience",
        r"education\s*(?:&|and)\s*experience",

        r"experience description",
        r"licensure description",
        r"license description",
        r"certification description",
        r"license(?:\s+and\s+|/)"
        r"certification(?:s)?(?:\s+description)?",
        r"minimum qualifications",
        r"minimum requirements",
        r"classification minimum requirements",
        r"requirements",
        r"qualifications",
        r"required skills",
        r"skills",
        r"skills and qualifications",
        r"strong technical skills(?:,\s*including)?",
        r"qualifications,\s*knowledge and skill requirements",
        r"knowledge and skill requirements",
        r"knowledge,?\s*skills,?\s*(?:and|&) abilities",
        r"what you(?:'|’)ll need",
        r"what you will need",
        r"what you(?:'|’)ll bring(?:\s+(?:to|at)\s+.+)?",
        r"what you will bring(?:\s+(?:to|at)\s+.+)?",
        r"the person",
        r"mental demands",
        r"technologies"
    ],
    "preferred": [
        r"preferred",
        r"preferred requirements",
        r"preferred qualifications",

        r"desirable(?: qualifications?)?",
        r"preferred experience",
        r"nice to have",
        r"nice-to-have",
        r"bonus",

        r"desired qualities?",
        r"desired attributes?",
        r"desired characteristics?",
    ],
    "education": [
        r"required education",
        r"education",
        r"education description",
        r"education requirements"
    ],
    "supporting": [
        r"personal attributes",
        r"personal qualities",
        r"key competencies",
        r"core competencies",
        r"professional competencies"
    ],
    "ignore": [
        r"fraud(?: alert| notice| warning)?",
        r"description",
        r"how we work",
        r"who we are",
        r"videos to ?watch",
        r"(?:the )?(?:company |corporate )?culture(?: at .+)?",
        r"corporate philanthropy",
        r"what we offer(?: you)?",
        r"recruitment fraud(?: alert| notice)?",
        r"application instructions",
        r"how to apply",
        r"compensation",
        r"salary range",

        # ATS/application-form questions are not JD requirements.
        # Entering this section resets extraction context to "ignore"
        # so neither the heading nor its form questions enter the ledger.
        r"application questions?",
        r"screening questions?",
        r"what(?:'|’)s in it for you\??",
        r"what is in it for you\??",
        r"perks(?: and benefits)?",
        r"legal disclaimer",
        r"legal notice",
        r"equal opportunity(?: employer)?",
        r"privacy policy",
        r"privacy notice",
        r"about us",
        r"about the company",
        r"about you",
        r"why join",
        r"why join the river",
        r"what we offer",
        r"we offer exceptional benefits",
        r"benefits",
        r"your benefits",
        r"stay connected with us",
        r"eeo statement",
        r"physical demands",
        r"visual demands",
        r"environment",
        r"classification",
        r"supervisory",
        r"flsa exempt",
        r"employment type",
        r"compensation",
        r"compensation and application deadline",
        r"application deadline",
        r"expected salary",
        r"the details",
        r"and more",
        r"about .+",
        r"special instructions to applicants",
        r"health assessment required",
        r"advertised",
        r"applications close",
        r"back to search results",
        r"search results",
        r"campaigns",
        r"current opportunities",
        r"powered by pageup",
        r"job search",
        r"refine search",
        r"work type",
        r"categories",
        r"locations",
        r"resources",
        r"send me jobs like these",
        r"privacy agreement",
        r"create (?:a )?job alert",
        r"autofill my application",
        r"submit application",
        r"powered by",
        r"site updated"
    ]
}

SECTION_PATTERNS.setdefault(
    "responsibilities",
    [],
).extend([
    r"essential functions(?:\s*(?:&|and)\s*responsibilities)?",
    r"how you(?:'|’)ll make an impact",
    r"how you will make an impact",
    r"\d{1,3}\s*%\s*:\s*.+",
])

SECTION_PATTERNS.setdefault(
    "required",
    [],
).extend([
    r"required skills(?:\s*(?:&|and)\s*experience)?",
    r"required qualifications(?:\s*(?:&|and)\s*skills)?",
    r"eligibility requirements(?:\s*(?:&|and)\s*program information)?",
    r"qualifications and credentials",
    r"abilities a/?nd competencies essential to the function of the job",
    r"communication and comprehension",
    r"problem solving",
    r"physical and sensory abilities",
    r"experience and skills",
    r"required",

    # Composite structural heading, e.g.
    # "WE'D LOVE TO HEAR FROM YOU IF: Must have:"
    #
    # Full-match + terminal label prevents substantive sentences such as
    # "Must have 5 years of SQL experience" from becoming headings.
    r"(?:[^:]{1,120}:\s*)?"
    r"(?:must\s+have|"
    r"required(?:\s+(?:qualifications?|requirements?|skills?|experience))?|"
    r"minimum\s+(?:qualifications?|requirements?))",
])

SECTION_PATTERNS.setdefault(
    "preferred",
    [],
).extend([
    r"helpful skills(?:\s*(?:&|and)\s*experience)?",
    r"preferred skills(?:\s*(?:&|and)\s*experience)?",
    r"preferred but not required",
])

SECTION_PATTERNS.setdefault(
    "supporting",
    [],
).extend([
    r"additional information",
    r"driving requirements",
])

SECTION_PATTERNS.setdefault(
    "ignore",
    [],
).extend([
    r"a little about us",
    r"a little about you",
    r"position overview",
    r"supervisory responsibilities",
    r"working conditions",
    r"work environment",
    r"time type",
    r"location",
    r"location and workplace flexibility",
    r"compensation\s*(?:&|and)\s*benefits",
    r"additional benefits may include",
    r"pay range",
    r"salary range",
    r"equal employment opportunity",
    r"accessibility support",
    r"how to apply",
    r"disclaimer",
    r"make a career at carter(?:'|’)s",
    r"job posting segment",
    r"job posting primary business",
    r"primary job posting category",
    r"primary city,?\s*state,?\s*region,?\s*postal code",
    r"alternate city,?\s*state,?\s*region,?\s*postal code",
    r"date posted",
    r"use of artificial intelligence in hiring",
    r"employment type",
    r"[a-z]{2,8}\s+(?:i|ii|iii|iv)(?:/(?:i|ii|iii|iv))*",
])



# Exact-mention dictionary only.
# No semantic inference occurs here.
TECH_TERMS = [
    "Go", "C", "C++", "C#", ".NET", "R Shiny", "RShiny", "PowerBI",
    "SQL",
    "Python",
    "R",
    "SAS",
    "SPSS",
    "Stata",
    "Excel",
    "Power BI",
    "Tableau",
    "Looker",
    "Qlik",
    "Snowflake",
    "Databricks",
    "BigQuery",
    "Redshift",
    "PostgreSQL",
    "Postgres",
    "MySQL",
    "SQL Server",
    "Oracle",
    "DuckDB",
    "Spark",
    "PySpark",
    "Hadoop",
    "dbt",
    "Airflow",
    "Alteryx",
    "Power Query",
    "DAX",
    "VBA",
    "AWS",
    "Azure",
    "GCP",
    "S3",
    "Git",
    "GitHub",
    "Docker",
    "Kubernetes",
    "Jira",
    "Confluence",
    "PeopleSoft",
    "Epic",
    "Epic Cadence",
    "Epic Template Management",
    "Electronic Health Record",
    "EHR",
    "SQL Developer",
    "Microsoft Office",
    "Microsoft Word",
    "Google Apps",
    "Salesforce",
    "GA4",
    "Google Analytics",
    "TensorFlow",
    "PyTorch",
    "scikit-learn",
    "sklearn",
    "pandas",
    "NumPy",
    "SciPy",
    "XGBoost",
    "BERT",
    "ETL",
    "ELT",
    "API",
    "REST",
    "JSON",
    "CSV",
    "Parquet"
]


WORK_PRODUCT_TERMS = [
    "dashboard",
    "dashboards",
    "report",
    "reports",
    "reporting",
    "data pipeline",
    "data pipelines",
    "pipeline",
    "pipelines",
    "data model",
    "data models",
    "semantic model",
    "semantic models",
    "forecast",
    "forecasting",
    "analysis",
    "analytics",
    "visualization",
    "visualizations",
    "dataset",
    "datasets",
    "database",
    "databases",
    "data warehouse",
    "data warehouses",
    "data mart",
    "data marts",
    "KPI",
    "KPIs",
    "metrics",
    "model",
    "models",
    "documentation",
    "business requirements",
    "user stories",
    "UAT",
    "test cases"
]


METHOD_TERMS = [
    "regression",
    "classification",
    "clustering",
    "machine learning",
    "statistical analysis",
    "predictive modeling",
    "predictive analytics",
    "A/B testing",
    "hypothesis testing",
    "data validation",
    "quality assurance",
    "QA",
    "data cleaning",
    "data transformation",
    "data integration",
    "data governance",
    "data modeling",
    "dimensional modeling",
    "star schema",
    "normalization",
    "forecasting",
    "segmentation",
    "optimization",
    "root cause analysis"
]


REQUIRED_SIGNALS = [
    r"\brequired\b",
    r"\bmust\b",
    r"\bminimum\b",
    r"\bneed(?:ed)?\b",
    r"\bshall\b"
]

PREFERRED_SIGNALS = [
    r"\bpreferred\b",
    r"\bdesired\b",
    r"\bdesirable\b",
    r"\bnice to have\b",
    r"\bnice-to-have\b",
    r"\bbonus\b",
    r"\ba plus\b",
    r"^plus:?$"
]


WORK_AUTH_PATTERNS = [
    r"authorized to work",
    r"work authorization",
    r"employment authorization",
    r"visa sponsorship",
    r"sponsorship",
    r"sponsor",
    r"\\bOPT\\b",
    r"\\bSTEM\\s+OPT\\b",
    r"\\bH-?1B\\b",
    r"immigration sponsorship"
]


from careerops_eligibility_patterns import ACTIVE_CLEARANCE_PATTERN
HARD_BLOCKER_PATTERNS = [
    ACTIVE_CLEARANCE_PATTERN,
    r"\bmust\s+not\s+require\b[^.?!\n]{0,100}\bsponsorship\b[^.?!\n]{0,80}\bnow\s+or\s+in\s+(?:the\s+)?future\b",
    r"\bmust\s+be\s+(?:a\s+)?(?:u\.?s\.?|united\s+states)\s+citizens?\b",

    r"\bwithout\s+(?:current\s+or\s+future|now\s+or\s+in\s+the\s+future)\s+(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b",
    r"without (?:current or future )?sponsorship",
    r"without sponsorship",
    r"will not sponsor",
    r"does not sponsor",
    r"do not sponsor",
    r"no sponsorship",
    r"not eligible for sponsorship",
    r"cannot provide sponsorship",
    r"cannot sponsor",
    r"unable to sponsor",
    r"unable to provide sponsorship",
    r"not able to sponsor",
    r"must be (?:a )?U\.?S\.? citizen",
    r"U\.?S\.? citizenship required",
    r"must be a permanent resident",
    r"green card required",
    r"security clearance required",
    r"active security clearance",
    r"must possess .* clearance",

    # Explicit eligibility exclusions only. Questions, positive sponsorship
    # language, generic 'clearance' business terms, and 'ability to obtain'
    # language are intentionally NOT treated as automatic blockers.
    r"\b(?:must|shall|required\s+to)\s+be\s+(?:a\s+)?(?:u\.?s\.?|united\s+states)\s+citizen\b",
    r"\b(?:u\.?s\.?|united\s+states)\s+citizenship\s+(?:is\s+)?required\b",
    r"\b(?:must|shall)\s+(?:have|hold)\s+(?:u\.?s\.?|united\s+states)\s+citizenship\b",
    r"\bmust\s+(?:currently\s+)?(?:hold|possess|maintain)\s+(?:an?\s+)?(?:active\s+|current\s+)?(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)\s+(?:security\s+)?clearance\b",
    r"\b(?:active|current)\s+(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)\s+(?:security\s+)?clearance\s+(?:is\s+)?required\b",
    r"\b(?:does|do|will)\s+not\s+(?:accept|support|permit|allow)\b[^.\n]{0,100}\b(?:f-?1|opt|stem\s+opt)\b",
    r"\b(?:f-?1|opt|stem\s+opt)\b[^.\n]{0,100}\b(?:is|are)\s+not\s+(?:accepted|supported|permitted|allowed)\b",
    r"\b(?:does|do|will|can|cannot|can\s+not)\s+not?\s*(?:provide|offer)\b[^.\n]{0,100}\b(?:employment\s+|visa\s+|work\s+)?sponsorship\b",
    r"\b(?:does|do|will|can)\s+not\s+(?:provide|offer)\b[^.\n]{0,100}\b(?:employment\s+|visa\s+|work\s+)?sponsorship\b",
    r"\b(?:unable|not\s+able)\s+to\s+sponsor\b",
    r"\b(?:no|without)\s+(?:current\s+or\s+future\s+)?(?:employment\s+|visa\s+|work\s+)?sponsorship\b",
    r"\b(?:current\s+or\s+future|now\s+or\s+in\s+the\s+future)\s+(?:employment\s+|visa\s+|work\s+)?sponsorship\s+(?:is\s+)?(?:not\s+available|unavailable)\b",
    r"\bmust\s+not\s+require\b[^.\n]{0,80}\b(?:current\s+or\s+future\s+|now\s+or\s+future\s+)?(?:visa\s+|employment\s+|work\s+)?sponsorship\b",

    r"\bwithout\s+(?:(?:the\s+)?need\s+for|reliance\s+on)\s+"
    r"(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\s+"
    r"(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b"
    r"(?:\s+from\s+(?:an?\s+)?(?:employer|company))?",

    r"\bmust\s+have\s+(?:an?\s+)?(?:active\s+|current\s+)"
    r"(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)"
    r"\s+(?:security\s+)?clearance\b",
    r"\b(?:active|current)\s+"
    r"(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)"
    r"\s+(?:security\s+)?clearance\s+(?:is\s+)?mandatory\b",

    r"\bno\s+(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\s+(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\s+(?:is\s+)?available\b",
    r"\brequire\b[^.?!\n]{0,100}\b(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b[^.?!\n]{0,100}\b(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\b[^.?!\n]{0,100}\bnot\s+eligible\b",
    r"\bwithout\s+(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b[^.?!\n]{0,80}\b(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\b",
    r"\b(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\s+(?:will\s+not\s+be|is\s+not)\s+available\b[^.?!\n]{0,80}\b(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\b",
    r"\blimited\s+to\s+(?:u\.?s\.?|united\s+states)\s+citizens?\b",
    r"\bpermanent\s+residents?\s+only\b",
    r"\bmust\s+already\s+hold\s+(?:an?\s+)?(?:active\s+|current\s+)?(?:top\s+secret(?:\s*/\s*sci|\s+sci)?|ts\s*/\s*sci|secret)\s+(?:security\s+)?clearance\b",

    r"\b(?:cannot|can't|can\s+not)\s+(?:provide|offer)\b"
    r"[^.?!\n]{0,100}"
    r"\b(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b"
    r"[^.?!\n]{0,80}"
    r"\b(?:current\s+or\s+future|now\s+or\s+(?:in\s+the\s+)?future)\b",
]


CLEARANCE_PATTERNS = [
    r"security clearance",
    r"secret\s*(?:\(or higher\)\s*)?clearance",
    r"top secret",
    r"TS/SCI",
    r"public trust"
]


DEGREE_PATTERNS = [
    r"\bassociate(?:'s)? degree\b",
    r"\bbachelor(?:(?:'s|’s)(?:\s+degree)?|\s+degree)\b",
    r"\bBS\b",
    r"\bBA\b",
    r"\bB\.S\.\b",
    r"\bB\.A\.\b",
    r"\bmaster(?:(?:'s|’s)(?:\s+degree)?|\s+degree)\b",
    r"\bmaster\s+of\s+(?:science|arts|business administration)\b",

    #
    # Bare "MS" is ambiguous with Microsoft terminology such as
    # "MS Suite" / "MS Office". Treat it as education only when the
    # local wording itself supplies degree context.
    r"\bMS\b(?=\s*(?:degree\b|in\b|preferred\b|required\b|,?\s+or\b|/))",
    r"\bMA\b",
    r"\bMBA\b",
    r"\bPh\.?D\.?\b",
    r"\bdoctorate\b",
    r"\bdegree\b"
]


def clean_line(line):
    line = line.strip()
    line = re.sub(r"^[\-\*\u2022▪◦]+\s*", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def normalize_title_candidate(line):
    """
    Remove common job-site page-title decoration without
    semantically rewriting the actual role title.
    """
    title = clean_line(line)

    m = re.match(r"^.+?\s+-\s+Details\s+-\s+(.+)$", title, flags=re.I)
    if m:
        title = m.group(1).strip()

    title = re.sub(
        r"\s+Job Details\s*\|\s*.+$",
        "",
        title,
        flags=re.I,
    )

    # Remove generic careers-site publisher decoration.
    title = re.sub(
        r"\s*\|\s*[^|]{1,80}\bCareers\s*$",
        "",
        title,
        flags=re.I,
    ).strip()

    if re.search(
        r"\|\s*Built In\s*$",
        title,
        flags=re.I,
    ):
        title = re.sub(
            r"\s*\|\s*Built In\s*$",
            "",
            title,
            flags=re.I,
        ).strip()

        if " - " in title:
            title = title.rsplit(
                " - ",
                1,
            )[0].strip()

    return title.strip()


# Structured labels and narrative lead-ins preserve source section semantics.
SECTION_PATTERNS['responsibilities'].extend([
 r'essential functions\s*(?:and|&)\s*primary duties',
 r'.{1,180}\b(?:by|responsibilities include|you will|you(?:\'|’)ll)\s*:',
])
SECTION_PATTERNS['required'].extend([
 r'(?:minimum|required) (?:education|(?:years of )?(?:work |leadership )?experience|certifications?)',
 r'(?:we(?:\'|’)re|we are) looking for someone who brings',
])
SECTION_PATTERNS['preferred'].extend([
 r'preferred (?:education|(?:years of )?(?:work |leadership )?experience|certifications?)',
])
SECTION_PATTERNS['ignore'].extend([r'this role is different',r'compensation (?:at|with) .+',r'flsa status',r'(?:department|division) name',r'job (?:title|description summary)'])

def heading_type(line):
    candidate = clean_line(line)

    #
    # Pasted JDs may preserve Markdown ATX heading markers such as
    # "## Qualifications". Formatting markers must not change section
    # semantics or requirement priority. Normalize only inside heading
    # recognition; requirement text itself remains source-faithful.
    candidate = re.sub(
        r"^\s*#{1,6}\s*",
        "",
        candidate,
    )

    # Also tolerate optional closing ATX markers:
    # "## Qualifications ##".
    candidate = re.sub(
        r"\s+#{1,6}\s*$",
        "",
        candidate,
    )

    candidate = candidate.strip(" :.-").lower()

    for section, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.fullmatch(pattern, candidate, re.I):
                return section

    return None


def contains_any(text, patterns):
    return any(re.search(p, text, re.I) for p in patterns)


TECH_TERMS = list(dict.fromkeys(TECH_TERMS + ["Windows"]))

def exact_term_matches(text, terms):
    hits = []

    for term in terms:
        suffix = r"(?![\w+#])" if term == 'C' else r"(?!\w)"
        pattern = r"(?<!\w)" + re.escape(term) + suffix

        if re.search(pattern, text, re.I):
            hits.append(term)

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(hits))


NUMBER_WORD_PATTERN = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty)"
)


def extract_years(text):
    """
    Extract explicit experience-duration language while preserving
    the exact JD phrase.

    Supports both numeric and written numbers:
      2 years
      two years
      3-5 years
      three to five years
      at least two years
    """
    number = rf"(?:\d+|{NUMBER_WORD_PATTERN})"

    #
    # Preserve common explicit minimum-duration serializations:
    #   between two and four years
    #   2 years+
    #   2 years + of relevant experience
    #   5 years+ professional experience
    #
    # Extraction only. This does NOT decide whether the experience
    # is occupationally relevant to the routed role.
    patterns = [
        rf"\bbetween\s+{number}\s+and\s+{number}\s+years?\b",
        (
            rf"\b{number}\s+years?\s*\+"
            rf"(?=\s*(?:"
            rf"of\b|"
            rf"experience\b|"
            rf"(?:relevant|related|professional|work)\s+experience\b|"
            rf"$"
            rf"))"
        ),
        rf"\b{number}\s*\+\s*years?\b",
        rf"\b{number}\s*(?:-|–|—|to)\s*{number}\s*years?\b",
        rf"\bminimum(?: of)?\s+{number}\s+years?\b",
        rf"\bat least\s+{number}\s+years?\b",
        rf"\b{number}\s+years?\s+of\b",
        rf"\b{number}\s+years?\s+experience\b",
        (
            rf"\b{number}\s+years?\s+"
            rf"(?:relevant|related|professional|work)\s+experience\b"
        ),
        (
            rf"\b{number}\s+years?\s+of\s+"
            rf"(?:relevant|related|professional|work)\s+experience\b"
        ),
    ]

    #
    # ATS/vendor tables may serialize the qualification label before
    # the duration:
    #   Relevant experience | 3 Years | Required
    patterns.insert(
        0,
        (
            rf"\b(?:(?:relevant|related|professional|work)\s+)?"
            rf"experience\s*(?:\||:|[-–—])\s*"
            rf"{number}\s+years?\b"
        ),
    )

    found = []

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            text,
            flags=re.I
        ):
            phrase = match.group(0).strip()

            if phrase.casefold() not in {
                x.casefold()
                for x in found
            }:
                found.append(phrase)

    # Remove shorter overlapping captures.
    #
    # Example:
    #   "two years of"
    #   "two years of relevant experience"
    #
    # Preserve only the more specific phrase.
    cleaned = []

    for phrase in found:
        phrase_key = phrase.casefold()

        is_shorter_overlap = any(
            phrase_key != other.casefold()
            and phrase_key in other.casefold()
            and len(phrase_key) < len(other.casefold())
            for other in found
        )

        if not is_shorter_overlap:
            cleaned.append(phrase)

    return cleaned



def extract_education(text):
    hits = []

    for pattern in DEGREE_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            hits.append(m.group(0))

    return list(dict.fromkeys(hits))


def extract_matching_phrases(text, patterns):
    hits = []

    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            if patterns is HARD_BLOCKER_PATTERNS and ('clearance' in m.group().casefold() or pattern == ACTIVE_CLEARANCE_PATTERN):
                if re.search(r'\b(?:ability|eligible|eligibility)\s+to\s+(?:obtain|get)|\b(?:no|not)\s+(?:security\s+)?clearance\s+(?:is\s+)?required', text, re.I):
                    continue
            hits.append(m.group(0))

    return list(dict.fromkeys(hits))

#
# CareerOps policy:
# - generic employer no-sponsorship statement -> REVIEW_ONLY
# - explicit current/future sponsorship exclusion -> HARD BLOCK
# - explicit F-1 / OPT / STEM OPT exclusion -> HARD BLOCK
#
# This helper deliberately does not make candidate-specific conclusions.
GENERIC_SPONSORSHIP_REVIEW_PATTERNS = [
    r"\b(?:we|the employer|the company)?\s*"
    r"(?:do|does|will)\s+not\s+sponsor\b",

    r"\b(?:we|the employer|the company)?\s*"
    r"(?:do|does|will)\s+not\s+"
    r"(?:provide|offer)\b[^.\n]{0,100}"
    r"\b(?:employment\s+|visa\s+|work\s+)?sponsorship\b",

    r"\b(?:cannot|can't)\s+"
    r"(?:(?:provide|offer)\s+"
    r"(?:visa\s+|employment\s+|work\s+)?sponsorship"
    r"|sponsor\b[^.\n]{0,100})",

    r"\b(?:unable|not\s+able)\s+to\s+"
    r"(?:(?:provide|offer)\s+"
    r"(?:visa\s+|employment\s+|work\s+)?sponsorship"
    r"|sponsor\b[^.\n]{0,100})",

    r"\bno\s+(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b",

    r"\b(?:visa\s+|employment\s+|work\s+|employer\s+)?sponsorship\s+is\s+not\s+available\b",
    r"\b(?:this\s+role|this\s+position|the\s+role|the\s+position)\s+is\s+not\s+eligible\s+for\s+(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b",

    r"\b(?:we|the\s+employer|the\s+company)?\s*"
    r"(?:cannot|can't|can\s+not)\s+(?:provide|offer)\s+"
    r"(?:employer\s+|employment\s+|visa\s+|work\s+)?sponsorship\b",
]


EXPLICIT_SPONSORSHIP_EXCLUSION_PATTERNS = [
    r"\b(?:current\s+or\s+future|now\s+or\s+in\s+the\s+future)\b"
    r"[^.\n]{0,120}\b(?:employment\s+|visa\s+|work\s+|employer\s+)?"
    r"sponsorship\b",

    r"\b(?:employment\s+|visa\s+|work\s+|employer\s+)?sponsorship\b"
    r"[^.\n]{0,120}"
    r"\b(?:current\s+or\s+future|now\s+or\s+in\s+the\s+future)\b",

    r"\bmust\s+not\s+require\b[^.\n]{0,120}"
    r"\b(?:employment\s+|visa\s+|work\s+|employer\s+)?sponsorship\b",

    r"\b(?:f-?1|opt|stem\s+opt)\b",
]


def generic_sponsorship_review_only(text):
    value = str(text or "")

    generic = any(
        re.search(
            pattern,
            value,
            flags=re.I,
        )
        for pattern
        in GENERIC_SPONSORSHIP_REVIEW_PATTERNS
    )

    if not generic:
        return False

    explicit = any(
        re.search(
            pattern,
            value,
            flags=re.I,
        )
        for pattern
        in EXPLICIT_SPONSORSHIP_EXCLUSION_PATTERNS
    )

    return not explicit


def structured_required_qualification(text):
    """
    Detect explicit ATS/vendor required qualification rows without
    reclassifying ordinary required wording inside core duties.

    A trailing structured Required marker is authoritative here only
    when the same row contains independently parseable education or
    experience-duration evidence.
    """
    value = str(
        text
        or ""
    ).strip()

    marker = bool(
        re.search(
            r"(?:\|\s*required|\(\s*required\s*\))\s*$",
            value,
            flags=re.I,
        )
    )

    if not marker:
        return False

    return bool(
        extract_education(
            value
        )
        or extract_years(
            value
        )
    )


def classify_priority(section, text):
    from careerops_eligibility_patterns import active_clearance_requirement
    if active_clearance_requirement(text):return "P0", "explicit_active_clearance"
    if re.search(r"\b(?:position requires|must have|minimum of)\b",text,re.I) and (extract_education(text) or extract_years(text)):return "P0", "explicit_qualification"
    preferred = contains_any(text, PREFERRED_SIGNALS)
    required = contains_any(text, REQUIRED_SIGNALS)
    hard_blocker = bool(extract_matching_phrases(text, HARD_BLOCKER_PATTERNS))

    if generic_sponsorship_review_only(
        text
    ):
        hard_blocker = False

    #
    # Explicit work-authorization / citizenship / clearance exclusions
    # are mandatory eligibility constraints regardless of the section
    # that happened to precede them on a careers page.
    if hard_blocker:
        return "P0", "explicit_hard_blocker"

    #
    # This intentionally precedes inherited responsibilities semantics,
    # but only for rows independently proven to be qualifications.
    if structured_required_qualification(
        text
    ):
        return (
            "P0",
            "structured_required_qualification",
        )

    if preferred and re.search(r"\b(?:experience|knowledge|skills?|proficiency|familiarity)\b",text,re.I):
        return "P3", "explicit_preferred_qualification"
    if re.search(r"\bequivalent combinations? of\b.{0,150}\b(?:education|experience)\b.{0,100}\b(?:considered|accepted)\b",text,re.I):
        return "P2", "alternative_qualification_path"

    # Responsibilities describe the actual core work.
    #
    # Section semantics win over incidental wording inside a duty
    # sentence. For example, "steps required to develop..." is still
    # a responsibility, not a P0 qualification.
    if section == "responsibilities":
        return "P1", "core_responsibility"

    if (
        section is None
        and re.search(
            r"\bprimary responsibility of (?:this|the) position\b",
            text,
            re.I,
        )
    ):
        return "P1", "core_responsibility_outside_section"

    if re.search(r"\b(?:not required|no (?:prior|previous) .{0,60}experience (?:is )?required)\b",text,re.I):
        return "P3", "explicitly_optional_experience"

    # Explicit preferred language always wins outside responsibilities.
    if section == "preferred" or preferred:
        return "P3", "preferred_or_nice_to_have_language"

    # Explicit required/minimum/must language is mandatory.
    if required:
        return "P0", "explicit_required_language"

    # Items under required/minimum qualification sections are mandatory.
    if section in {"required", "education"}:
        return "P0", "required_section"

    return "P2", "supporting_or_unclassified_requirement"

def _realworld_structural_only_line(line):
    value = clean_line(
        line
    ).strip(" :.-")

    if re.fullmatch(
        r"\d{1,3}\s*%\s*:\s*.+",
        value,
        re.I,
    ):
        return True

    if re.fullmatch(
        r"[A-Z]{2,8}\s+(?:I|II|III|IV)(?:/(?:I|II|III|IV))*",
        value,
    ):
        return True

    return False


def _realworld_careers_boilerplate(line):
    value = clean_line(line)
    low = value.casefold()

    # Hard eligibility truth outranks presentation/chrome filtering.
    if contains_any(
        value,
        HARD_BLOCKER_PATTERNS,
    ):
        return False

    if re.fullmatch(
        r"#li-[a-z0-9_-]+",
        low,
        re.I,
    ):
        return True

    if re.fullmatch(
        (
            r"[\$£€]\s*[\d,.]+"
            r"(?:\s*[-–—]\s*[\$£€]?\s*[\d,.]+)?"
            r"(?:\s*(?:usd|cad|gbp|eur))?"
        ),
        value,
        re.I,
    ):
        return True

    patterns = [
        r"^salary range for this role is\s*:",
        r"^the salary range for this position\b",
        r"^the pay rate for this role\b",
        r"^this is a full-time position offering\s+[\$£€]",
        r"^the compensation for this position is\s+[\$£€]",
        r"^compensation is determined based on factors\b",
        r"^our benefits package includes\b",
        r"^additional benefits may include\s*:?\s*$",
        r"^select benefits may be provided\b",
        r"^the position may also be eligible for comprehensive benefits\b",
        r"^ranges will change based on country and state of residence\b",
        r"\bfor information about our benefits\b",
        r"\bto learn more about our benefits\b",

        r"\bequal opportunity employer\b",
        r"\ball qualified applicants\b.*\bwithout regard to\b",
        r"\bemployment decisions are made without regard to\b",

        r"\breasonable accommodations?\b.*\b(?:apply|application|interview|positions?)\b",
        r"\bdrug[\s-]*free\b.*\bworkplace\b",
        r"\btobacco[\s-]*free\b.*\bworkplace\b",

        r"^we may use automated or artificial intelligence enabled tools\b",
        r"\buse of artificial intelligence in hiring\b",
        r"^by submitting your application, you agree\b",
        r"\bcandidate privacy policy\b",
        r"\bprivacy policy\b.*\bapplication\b",

        r"^please submit your resume\b",
        r"^applicants are encouraged to include\b",
        r"^we highly encourage applicants to print a copy of this job description\b",
        r"^note:\s*this job description is not intended to be all-inclusive\b",
        r"^the above statements are intended to describe the general nature\b",
        r"^job description\.$",
    ]

    return any(
        re.search(
            pattern,
            value,
            re.I,
        )
        for pattern in patterns
    )

def _careerops_base_looks_like_requirement(line, section):
    if not line:
        return False

    # Skip extremely short fragments.
    if len(line) < 3:
        return False

    # Structural section headers are not requirements.
    if heading_type(line):
        return False

    # Section-introduction prose is structural, not a candidate
    # requirement.
    if re.fullmatch(
        r"(?:the\s+)?qualifications,?\s*knowledge,?\s*(?:and\s+)?"
        r"skill\s+requirements\s+for\s+this\s+position\s+include:?",
        line,
        re.I,
    ):
        return False

    # Generic catch-all duty language carries no tailoring signal.
    if re.fullmatch(
        r"(?:completes?|performs?)\s+(?:(?:all\s+)?other|additional)\s+duties"
        r"(?:\s+or\s+analysis\s+projects)?"
        r"(?:\s+and\s+responsibilities)?\s+as\s+assigned"
        r"(?:\s+by\b[^.;:]*)?\.?",
        line,
        re.I,
    ):
        return False

    # Explicit non-tailoring sections must never leak into the
    # requirement ledger through generic signals such as "minimum"
    # or "ability to".
    if section == "ignore":
        return False

    # Inside a recognized requirement/responsibility section,
    # retain substantive lines.
    if section in {
        "responsibilities",
        "required",
        "preferred",
        "education",
        "supporting"
    }:
        return True

    # Outside sections, retain lines only when they have strong
    # requirement/responsibility signals.
    outside_signals = [
        r"\brequired\b",
        r"\bpreferred\b",
        r"\bmust\b",
        r"\bminimum\b",
        r"\bexperience\b",
        r"\bresponsible for\b",
        r"\bability to\b",
        r"\bproficiency\b",
        r"\bknowledge of\b",
        r"\bdegree\b",
        r"^(?:Analy[sz]ing|Building|Partnering|Acting|Leading|Developing|Creating|Managing|Supporting|Maintaining)\b"
    ]

    return contains_any(line, outside_signals)

def looks_like_requirement(line, section):
    from careerops_eligibility_patterns import active_clearance_requirement
    if active_clearance_requirement(line):return True

    if not line:
        return False

    # Eligibility truth always survives careers-site filtering.
    if extract_matching_phrases(line, HARD_BLOCKER_PATTERNS):
        return True

    if _realworld_structural_only_line(
        line
    ):
        return False

    if _realworld_careers_boilerplate(
        line
    ):
        return False

    if section == "supporting":
        return True

    return _careerops_base_looks_like_requirement(
        line,
        section,
    )

def structural_ledger_quality_risk(
    intake,
    raw_lines,
    requirements,
    priority_counts,
):
    """
    Detect a likely structural parsing collapse without requiring every
    legitimate JD to contain recognized headings.

    Fail closed only when:
      - the JD is substantial,
      - ingest found zero known headings,
      - extraction classified no requirement under any section,
      - every retained requirement is P2/unclassified,
      - and multiple short heading-like lines contain common
        responsibility/qualification heading concepts.
    """
    metadata = (
        intake.get(
            "metadata",
            {},
        )
        or {}
    )

    word_count = int(
        metadata.get(
            "word_count",
            0,
        )
        or 0
    )

    line_count = int(
        metadata.get(
            "line_count",
            len(raw_lines),
        )
        or len(raw_lines)
    )

    detected = (
        metadata.get(
            "detected_section_headings",
            [],
        )
        or []
    )

    classified = [
        row
        for row in requirements
        if row.get(
            "section"
        )
        not in {
            None,
            "",
            "unclassified",
        }
    ]

    heading_hint = re.compile(
        r"\b("
        r"responsibilit(?:y|ies)|"
        r"dut(?:y|ies)|"
        r"tasks?|"
        r"accountabilit(?:y|ies)|"
        r"qualifications?|"
        r"requirements?|"
        r"experience|"
        r"education|"
        r"competenc(?:y|ies)|"
        r"skills?|"
        r"job summary|"
        r"job description"
        r")\b",
        re.I,
    )

    heading_like = []

    for raw in raw_lines:
        line = clean_line(
            raw
        ).strip()

        if not line:
            continue

        words = (
            line.rstrip(":")
            .split()
        )

        if not (
            len(line) <= 100
            and 1 <= len(words) <= 12
        ):
            continue

        if not heading_hint.search(
            line
        ):
            continue

        if (
            line.endswith(":")
            or not re.search(
                r"[.!?]$",
                line,
            )
        ):
            heading_like.append(
                line
            )

    all_p2 = (
        bool(requirements)
        and priority_counts.get(
            "P2",
            0,
        )
        == len(requirements)
    )

    suspicious = (
        word_count >= 200
        and line_count >= 15
        and len(detected) == 0
        and len(classified) == 0
        and all_p2
        and len(
            dict.fromkeys(
                heading_like
            )
        )
        >= 2
    )

    return {
        "status":
            (
                "FAIL_CLOSED"
                if suspicious
                else "PASS"
            ),
        "word_count":
            word_count,
        "line_count":
            line_count,
        "ingest_heading_count":
            len(detected),
        "classified_requirement_count":
            len(classified),
        "all_requirements_p2":
            all_p2,
        "heading_like_candidates":
            list(
                dict.fromkeys(
                    heading_like
                )
            )[:20],
        "reason":
            (
                "Substantial structured-looking JD collapsed to "
                "zero recognized headings and an all-P2 "
                "unclassified requirement ledger."
                if suspicious
                else None
            ),
    }


def source_units(raw_lines):
    """Split copied bullet/semicolon units, retaining physical source spans."""
    import hashlib
    field_heading = ""
    for number,raw in enumerate(raw_lines,1):
        if re.fullmatch(r"(?:minimum|required|preferred) (?:education|(?:years of )?(?:work |leadership )?experience|certifications?)[:.]?", clean_line(raw), re.I):
            field_heading = clean_line(raw)
        elif heading_type(raw):
            field_heading = ""
        if not raw.strip():continue
        split_at = [m.end() for m in re.finditer(r"(?:[•▪◦]\s+|;\s+)",raw) if m.start()>0]
        # Optional follow-on sentences cannot demote preceding tenure.
        for match in re.finditer(r"(?<=[.?!])\s+(?=[A-Z])",raw):
            following = re.split(r'(?<=[.?!])\s+',raw[match.end():],maxsplit=1)[0]
            if re.search(r'\b(?:a plus|preferred|nice.to.have|desirable)\b',following,re.I):
                split_at.append(match.end())
        boundaries=[0]+sorted(set(split_at))+[len(raw)]
        contexts=list(re.finditer(r"Must\s+(?:also\s+)?have\s+\d+\s+years?\s+of\s+experience\s+with\s+each\s+of\s+the\s+following\s*:",raw,re.I))
        for start,end in zip(boundaries,boundaries[1:]):
            segment=raw[start:end]
            chunk=segment.strip(' \t\r\n;•▪◦')
            if not chunk:continue
            offset=start+segment.find(chunk)
            # Retain physical bounds even when copied spacing is normalized.
            raw_chunk=chunk
            bullet=re.match(r'^[\-*•▪◦]+\s*',chunk)
            if bullet:
                offset+=bullet.end();raw_chunk=chunk[bullet.end():]
            exact=clean_line(raw_chunk)
            prior=[m for m in contexts if m.start()<=start]
            context=prior[-1].group() if prior else ''
            if field_heading and not heading_type(exact):
                context = field_heading
            yield number,exact,{'physical_line':number,'start_char':offset,'end_char':offset+len(raw_chunk),'original_line_sha256':hashlib.sha256(raw.encode()).hexdigest(),'qualifier_context_quote':context}

def main():
    if not INPUT.exists():
        raise SystemExit(
            "Missing jd_intake.json. Run careerops_ingest_jd.py first."
        )

    intake = json.loads(INPUT.read_text())

    if intake.get("status") != "INGESTED":
        raise SystemExit(
            "JD intake is not INGESTED. Supply usable JD text first."
        )

    jd = intake.get("raw_jd_text") or ""

    raw_lines = jd.splitlines()

    first_nonempty = next(
        (
            line.strip()
            for line in raw_lines
            if line.strip()
        ),
        "",
    )

    is_builtin_page = bool(
        re.search(
            r"\|\s*Built In\s*$",
            first_nonempty,
            flags=re.I,
        )
    )

    if is_builtin_page:
        marker_lines = [
            clean_line(line)
            .strip(" :.-")
            .casefold()
            for line in raw_lines
        ]

        try:
            job_start = marker_lines.index(
                "the job"
            )
            details_start = marker_lines.index(
                "the details",
                job_start + 1,
            )
        except ValueError:
            job_start = None
            details_start = None

        if (
            job_start is not None
            and details_start is not None
            and details_start > job_start
        ):
            jd = "\n".join(
                [
                    first_nonempty,
                    *raw_lines[
                        job_start:details_start
                    ],
                ]
            )

    raw_lines = jd.splitlines()

    #
    # Production orchestration already owns authoritative company/title
    # identity. Use that position when supplied. Standalone extractor use
    # retains the historical title-detection fallback.
    title = (
        os.environ.get(
            "CAREEROPS_JOB_POSITION",
            "",
        ).strip()
        or None
    )

    current_section = None
    requirements = []
    blockers = []
    work_auth = []
    clearance = []

    req_num = 1

    for index, raw, source_span in source_units(raw_lines):
        line = clean_line(raw)

        #
        # Production orchestration owns canonical employer/title identity.
        # Explicit pasted identity labels are metadata, not job requirements,
        # even when they appear beneath a recognized JD section.
        if re.match(
            r"^(?:company|employer|job\s+title|position)\s*:",
            line,
            re.I,
        ):
            continue

        section_hit = heading_type(line)

        if section_hit:
            current_section = section_hit
            continue

        # First substantive line before a section is a title candidate.
        if title is None and current_section is None:
            title = normalize_title_candidate(line)
            continue

        # Capture blocker/auth language even if it appears outside a normal
        # qualifications section.
        auth_hits = extract_matching_phrases(
            line,
            WORK_AUTH_PATTERNS
        )

        blocker_hits = extract_matching_phrases(
            line,
            HARD_BLOCKER_PATTERNS
        )

        # Generic employer no-sponsorship wording is retained as
        # work-authorization/context evidence, but it must not enter
        # potential_hard_blockers. The semantic/effective layer owns
        # its REVIEW_ONLY interpretation.
        if generic_sponsorship_review_only(
            line
        ):
            blocker_hits = []

        clearance_hits = extract_matching_phrases(
            line,
            CLEARANCE_PATTERNS
        )

        if auth_hits:
            work_auth.append({
                "line": index,
                "exact_quote": line,
                "signals": auth_hits
            })

        if clearance_hits:
            clearance.append({
                "line": index,
                "exact_quote": line,
                "signals": clearance_hits
            })

        if blocker_hits:
            blockers.append({
                "line": index,
                "exact_quote": line,
                "signals": blocker_hits
            })

        # A role introduction can resume responsibilities after a company
        # description. Match the current title, rather than company prose.
        role_intro = bool(title and (re.match(
            r"^(?:the\s+)?" + re.escape(title) +
            r"\s+(?:is embedded|will\b|is responsible|works?\b|reports?\b)",
            line, re.I) or re.search(
            r"\b(?:we|our partner|the company) (?:are|is) (?:looking for|seeking)\b.{0,80}"+re.escape(title),line,re.I)))
        if role_intro:
            current_section = "responsibilities"
        numeric_field = bool(re.fullmatch(r"\d+(?:\.\d+)?",line) and re.search(r"years of .*experience",source_span["qualifier_context_quote"],re.I))
        if not numeric_field and not looks_like_requirement(line, current_section):
            continue

        unit_section=current_section
        if (source_span['qualifier_context_quote'] and not re.match(r'preferred',source_span['qualifier_context_quote'],re.I)) or (re.search(r'\b(?:position requires|must have)\b',line,re.I) and (extract_years(line) or extract_education(line))):unit_section='required'
        priority, basis = classify_priority(unit_section,line)
        if re.fullmatch(r"no (?:previous|prior) .{0,40}experience(?: required)?[.]?",line,re.I):
            priority,basis="P3","EXPLICIT_NO_EXPERIENCE_REQUIRED"
        if unit_section in {None,"unclassified"} and re.match(r"^(?:Analy[sz]ing|Building|Partnering|Acting|Leading|Developing|Creating|Managing|Supporting|Maintaining)\b",line,re.I):
            unit_section,priority,basis="responsibilities","P1","HEADINGLESS_RESPONSIBILITY_ACTION"

        tools = exact_term_matches(line, TECH_TERMS)
        products = exact_term_matches(
            line,
            WORK_PRODUCT_TERMS
        )
        methods = exact_term_matches(
            line,
            METHOD_TERMS
        )

        requirement = {
            "requirement_id": f"REQ-{req_num:03d}",
            "priority": priority,
            "priority_basis": basis,
            "section": unit_section or "unclassified",
            "source_span": source_span,
            "jd_line": index,
            "exact_quote": line,

            # Normalized copy is intentionally conservative.
            # No semantic rewriting occurs yet.
            "normalized_requirement": line,

            "exact_tools_technologies": tools,
            "exact_work_products": products,
            "exact_methods": methods,
            "experience_years_phrases": ([line + " years of work experience"] if numeric_field else extract_years(line) or extract_years(source_span["qualifier_context_quote"])),
            "education_phrases": extract_education(line),
            "work_authorization_phrases": auth_hits,
            "clearance_phrases": clearance_hits,
            "hard_blocker_phrases": blocker_hits,

            # Semantic mapping is deliberately deferred.
            "semantic_equivalents": []
        }

        requirements.append(requirement)
        req_num += 1

    # Final structural cleanup.
    cleaned_requirements = []
    seen_requirement_quotes = {}

    for req in requirements:
        quote = re.sub(
            r"\s+",
            " ",
            req.get("exact_quote", "")
        ).strip()

        section = req.get("section")

        # Labels such as "Reporting & Analytics:" are headings, not requirements.
        if (
            section in {
                "responsibilities",
                "required",
                "preferred",
                "education",
                "supporting",
            }
            and quote.endswith(":")
            and len(quote.split()) <= 10
        ):
            continue

        # Narrative qualification lead-ins are structural prose,
        # not candidate requirements. Examples:
        #   "... You also have:"
        #   "... You will also need:"
        #   "... We are looking for:"
        #
        # Keep actual short requirements that happen to contain
        # ordinary punctuation; only remove explicit lead-in forms.
        normalized_quote = quote.casefold().replace("’", "'")

        qualification_leadin_endings = (
            "you also have:",
            "you'll also need:",
            "you will also need:",
            "we are looking for:",
        )

        if (
            section in {"required", "preferred", "education"}
            and normalized_quote.endswith(
                qualification_leadin_endings
            )
        ):
            continue

        key = quote.casefold()

        # Repeated qualification text should appear only once.
        # The strongest occurrence owns repeated wording. Retain every physical source.
        if key and key in seen_requirement_quotes:
            prior=seen_requirement_quotes[key]
            spans=prior.get("duplicate_source_spans",[prior["source_span"]])+[req["source_span"]]
            if req["priority"] < prior["priority"]:
                cleaned_requirements[cleaned_requirements.index(prior)] = req
                seen_requirement_quotes[key]=req
                req["duplicate_source_spans"]=spans
            else:prior["duplicate_source_spans"]=spans
            continue

        if key:
            seen_requirement_quotes[key]=req

        cleaned_requirements.append(req)

    requirements = cleaned_requirements

    for i, req in enumerate(requirements, 1):
        req["requirement_id"] = f"REQ-{i:03d}"

    priority_counts = {
        p: sum(
            1 for r in requirements
            if r["priority"] == p
        )
        for p in ["P0", "P1", "P2", "P3"]
    }

    structure_quality = structural_ledger_quality_risk(
        intake,
        raw_lines,
        requirements,
        priority_counts,
    )

    if structure_quality["status"] == "FAIL_CLOSED":
        print(
            "REQUIREMENT LEDGER QUALITY: FAIL_CLOSED"
        )
        print(
            "REASON:",
            structure_quality["reason"],
        )
        print(
            "HEADING-LIKE CANDIDATES:",
            " | ".join(
                structure_quality[
                    "heading_like_candidates"
                ]
            ),
        )
        raise RuntimeError(
            "Requirement ledger failed structural quality validation"
        )

    exact_tools = list(dict.fromkeys(
        tool
        for r in requirements
        for tool in r["exact_tools_technologies"]
    ))

    work_products = list(dict.fromkeys(
        item
        for r in requirements
        for item in r["exact_work_products"]
    ))

    methods = list(dict.fromkeys(
        item
        for r in requirements
        for item in r["exact_methods"]
    ))

    output = {
        "schema_version": "jd-requirements-v1",
        "target_role_title_candidate": title,
        "source_type": intake.get("source_type"),
        "source_url": intake.get("source_url"),
        "ats": intake.get("ats"),

        "requirement_count": len(requirements),
        "priority_counts": priority_counts,

        "requirements": requirements,

        "aggregate_exact_terms": {
            "tools_technologies": exact_tools,
            "work_products": work_products,
            "methods": methods
        },

        "work_authorization_language": work_auth,
        "clearance_language": clearance,
        "potential_hard_blockers": blockers,
        "structural_quality": structure_quality,

        "policy": {
            "exact_quote_required_for_every_requirement": True,
            "semantic_inference_performed": False,
            "market_prior_applied": False,
            "candidate_evidence_used": False,
            "fit_decision_performed": False
        }
    }

    OUTPUT.write_text(
        json.dumps(output, indent=2, ensure_ascii=False)
    )

    print("REQUIREMENT LEDGER: CREATED")
    print("TARGET ROLE:", title or "UNKNOWN")
    print("TOTAL REQUIREMENTS:", len(requirements))
    print(
        "PRIORITIES:",
        " | ".join(
            f"{p}={priority_counts[p]}"
            for p in ["P0", "P1", "P2", "P3"]
        )
    )
    print(
        "TOOLS:",
        ", ".join(exact_tools) if exact_tools else "NONE"
    )
    print(
        "WORK PRODUCTS:",
        ", ".join(work_products) if work_products else "NONE"
    )
    print(
        "HARD BLOCKERS:",
        len(blockers)
    )
    print("OUTPUT:", OUTPUT.relative_to(ROOT))

    print("\nLEDGER:")
    for r in requirements:
        print(
            f"{r['requirement_id']} "
            f"{r['priority']} "
            f"[{r['section']}] "
            f"{r['exact_quote']}"
        )


if __name__ == "__main__":
    main()
