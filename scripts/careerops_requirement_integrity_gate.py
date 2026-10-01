import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from careerops_runtime import runtime_dir
from careerops_semantic_sidecar import infer_heading as semantic_infer_heading
from careerops_effective_runtime import build_effective_bundle
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runtime_dir(ROOT)
DEFAULT_INTAKE = RUNTIME / 'jd_intake.json'
DEFAULT_REQUIREMENTS = RUNTIME / 'jd_requirements.json'
DEFAULT_OUTPUT = RUNTIME / 'requirement_integrity_gate.json'
SECTION_PATTERNS = {'responsibilities': ['responsibilit(?:y|ies)', 'key responsibilities', 'dut(?:y|ies)', 'essential functions', 'primary duties', 'primary duties/?essential functions', 'specific duties and responsibilities', 'duties and responsibilities', 'job duties', 'main job tasks', 'key accountabilit(?:y|ies)', "what you(?:'|’)ll do(?:\\s+at\\s+.+)?", 'what you will do(?:\\s+at\\s+.+)?', 'the role'], 'qualifications': ['qualifications?', 'requirements?', 'required skills', 'minimum qualifications?', 'minimum requirements?', 'required qualifications?', 'required experience', 'experience description', 'education\\s*(?:&|and)\\s*experience', 'skills and qualifications', 'strong technical skills(?:,\\s*including)?', 'knowledge,?\\s*skills?\\s*(?:and|&)\\s*abilities', 'knowledge and skill requirements', "what you(?:'|’)ll need", 'what you will need', "what you(?:'|’)ll bring(?:\\s+(?:to|at)\\s+.+)?", 'what you will bring(?:\\s+(?:to|at)\\s+.+)?', 'the person'], 'supporting': ['personal attributes', 'personal qualities', 'key competencies', 'core competencies', 'professional competencies'], 'preferred': ['preferred', 'preferred qualifications?', 'desirable(?: qualifications?)?', 'preferred requirements?', 'preferred experience', 'nice to have', 'nice-to-have', 'bonus', 'desired qualities?', 'desired attributes?', 'desired characteristics?'], 'education': ['education', 'required education', 'education description', 'education requirements?'], 'ignore': ['physical demands?', 'physical requirements?', 'visual demands?', 'environment', 'work environment', 'environmental demands?', 'compensation', 'compensation and benefits', 'salary', 'salary range', 'pay range', 'benefits', 'what we offer', 'we offer you', 'why join(?: us)?', "what(?:'|’)s in it for you\\??", 'what is in it for you\\??', 'perks(?: and benefits)?', 'legal disclaimer', 'legal notice', 'equal opportunity(?: employer)?', 'privacy policy', 'privacy notice', 'why work (?:here|with us)', "why you(?:'|’)ll love (?:working )?here", 'interview process', 'hiring process', 'recruit(?:ing|ment) process', 'about us', 'about the company', 'who we are', 'equal opportunity', 'equal employment opportunity', 'eeo statement', 'application instructions?', 'special instructions to applicants', 'create (?:a )?job alert', 'autofill my application', 'submit application', 'powered by']}

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
    "qualifications",
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

    # Generic compound mandatory heading.
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

STRUCTURAL_LEADINS = ['you also have', "you(?:'|’)ll also need", 'you will also need', 'we are looking for', 'the successful candidate', 'the ideal candidate']
HARD_END_BOUNDARIES = ['similar jobs?', 'related jobs?', 'recommended jobs?', 'what you need to know about .+ tech scene', 'key facts about .+ tech', 'read full description', 'apply instructions?', 'create (?:a )?job alert', 'autofill my application', 'submit application', 'create free account', 'already have an account', 'please log in or sign up', 'recruit with .+', 'become an expert contributor', 'our staff writers', 'content descriptions', 'get involved', '©\\s*\\d{4}']
PAGE_CHROME_EXACT = ['apply', 'apply now', 'apply save', 'continue', 'companies', 'jobs', 'tracker', 'articles', 'more', 'join', 'log in', 'tech jobs', 'remote', 'salaries', 'post job', 'current opportunities', 'back to search results', 'search results']
EXPLICIT_P0_SIGNALS = ['\\brequired\\b', '\\bmust\\b', '\\bminimum\\b', '\\bmandatory\\b', '\\bshall\\b', '\\bneed(?:ed|required)?\\b', '\\bdegree\\b', '\\blicen[cs](?:e|ed|ure)\\b', '\\bcertification\\b', "\\b(?:\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(?:\\(\\s*\\d+\\s*\\))?\\s*(?:\\+|plus)?\\s*(?:(?:-|–|—|to)\\s*(?:\\d+|one|two|three|four|five|six|seven|eight|nine|ten))?\\s*years?(?:['’])?(?:\\s+of)?\\s+(?:(?:related|relevant|professional|work|data|analytics?)\\s+)*experience\\b"]
HARD_BLOCKER_SIGNALS = ['\\b(?:does|do|will)\\s+not\\s+(?:accept|support|permit|allow)[^.?!]{0,140}\\b(?:f-?1|opt|stem\\s+opt)\\b', '\\b(?:f-?1|opt|stem\\s+opt)\\b[^.?!]{0,140}\\bnot\\s+(?:accepted|supported|permitted|allowed|eligible)\\b', '\\bmust\\s+not\\s+require\\b[^.?!]{0,120}\\b(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\b[^.?!]{0,100}\\bsponsorship\\b', '\\b(?:does|do|will)\\s+not\\s+(?:provide|offer)\\b[^.?!]{0,120}\\b(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\b[^.?!]{0,100}\\bsponsorship\\b', '\\b(?:must|shall|required\\s+to)\\s+be\\s+(?:a\\s+)?(?:u\\.?s\\.?|united\\s+states)\\s+citizen\\b', '\\b(?:u\\.?s\\.?|united\\s+states)\\s+citizenship\\s+(?:is\\s+)?required\\b', '\\b(?:must|shall|required\\s+to)\\s+be\\s+(?:a\\s+)?(?:u\\.?s\\.?\\s+)?permanent\\s+resident\\b', '\\bgreen\\s+card\\s+(?:is\\s+)?required\\b', '\\bmust\\s+(?:currently\\s+)?(?:hold|possess|maintain)\\s+(?:an?\\s+)?(?:active\\s+|current\\s+)(?:top\\s+secret(?:\\s*/\\s*sci|\\s+sci)?|ts\\s*/\\s*sci|secret)\\s+(?:security\\s+)?clearance\\b', '\\b(?:active|current)\\s+(?:top\\s+secret(?:\\s*/\\s*sci|\\s+sci)?|ts\\s*/\\s*sci|secret)\\s+(?:security\\s+)?clearance\\s+(?:is\\s+)?required\\b', '\\bwithout\\s+(?:(?:the\\s+)?need\\s+for|reliance\\s+on)\\s+(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\s+(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\b(?:\\s+from\\s+(?:an?\\s+)?(?:employer|company))?', '\\bmust\\s+have\\s+(?:an?\\s+)?(?:active\\s+|current\\s+)(?:top\\s+secret(?:\\s*/\\s*sci|\\s+sci)?|ts\\s*/\\s*sci|secret)\\s+(?:security\\s+)?clearance\\b', '\\b(?:active|current)\\s+(?:top\\s+secret(?:\\s*/\\s*sci|\\s+sci)?|ts\\s*/\\s*sci|secret)\\s+(?:security\\s+)?clearance\\s+(?:is\\s+)?mandatory\\b', '\\bno\\s+(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\s+(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\s+(?:is\\s+)?available\\b', '\\brequire\\b[^.?!\\n]{0,100}\\b(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\b[^.?!\\n]{0,100}\\b(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\b[^.?!\\n]{0,100}\\bnot\\s+eligible\\b', '\\bwithout\\s+(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\b[^.?!\\n]{0,80}\\b(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\b', '\\b(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\s+(?:will\\s+not\\s+be|is\\s+not)\\s+available\\b[^.?!\\n]{0,80}\\b(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\b', '\\blimited\\s+to\\s+(?:u\\.?s\\.?|united\\s+states)\\s+citizens?\\b', '\\bpermanent\\s+residents?\\s+only\\b', '\\bmust\\s+already\\s+hold\\s+(?:an?\\s+)?(?:active\\s+|current\\s+)?(?:top\\s+secret(?:\\s*/\\s*sci|\\s+sci)?|ts\\s*/\\s*sci|secret)\\s+(?:security\\s+)?clearance\\b', "\\b(?:cannot|can't|can\\s+not)\\s+(?:provide|offer)\\b[^.?!\\n]{0,100}\\b(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\b[^.?!\\n]{0,80}\\b(?:current\\s+or\\s+future|now\\s+or\\s+(?:in\\s+the\\s+)?future)\\b"]
RESPONSIBILITY_VERBS = {'analyze', 'analyses', 'analyzes', 'analyzing', 'build', 'builds', 'building', 'collaborate', 'collaborates', 'collaborating', 'conduct', 'conducts', 'conducting', 'configure', 'configures', 'configuring', 'coordinate', 'coordinates', 'coordinating', 'create', 'creates', 'creating', 'develop', 'develops', 'developing', 'design', 'designs', 'designing', 'ensure', 'ensures', 'ensuring', 'execute', 'executes', 'executing', 'implement', 'implements', 'implementing', 'lead', 'leads', 'leading', 'maintain', 'maintains', 'maintaining', 'manage', 'manages', 'managing', 'monitor', 'monitors', 'monitoring', 'oversee', 'oversees', 'overseeing', 'partner', 'partners', 'partnering', 'perform', 'performs', 'performing', 'prepare', 'prepares', 'preparing', 'provide', 'provides', 'providing', 'review', 'reviews', 'reviewing', 'support', 'supports', 'supporting', 'troubleshoot', 'troubleshoots', 'troubleshooting', 'use', 'uses', 'using', 'write', 'writes', 'writing'}
STOPWORDS = {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'is', 'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'with', 'will', 'you', 'your'}

def normalize(text):
    text = str(text or '')
    text = text.replace('’', "'").replace('–', '-').replace('—', '-')
    text = re.sub('^[\\s•·▪●○◦*-]+', '', text)
    text = re.sub('^\\(?\\d{1,3}[\\).:-]\\s*', '', text)
    text = re.sub('\\s+', ' ', text)
    return text.strip()

def canon(text):
    return normalize(text).casefold().strip(' :.-')

def tokens(text):
    return {x for x in re.findall('[a-z0-9+#./-]+', canon(text)) if len(x) >= 2 and x not in STOPWORDS}

def fullmatch_any(text, patterns):
    c = canon(text)
    return any((re.fullmatch(pattern, c, flags=re.I) for pattern in patterns))

def search_any(text, patterns):
    return any((re.search(pattern, text, flags=re.I) for pattern in patterns))

# Structured labels and narrative lead-ins preserve source section semantics.
SECTION_PATTERNS['responsibilities'].extend([
 r'essential functions\s*(?:and|&)\s*primary duties',
 r'.{1,180}\b(?:by|responsibilities include|you will|you(?:\'|’)ll)\s*:',
])
SECTION_PATTERNS['qualifications'].extend([
 r'(?:minimum|required) (?:education|(?:years of )?(?:work |leadership )?experience|certifications?)',
 r'(?:we(?:\'|’)re|we are) looking for someone who brings',
])
SECTION_PATTERNS['preferred'].extend([
 r'preferred (?:education|(?:years of )?(?:work |leadership )?experience|certifications?)',
])
SECTION_PATTERNS['ignore'].extend([r'this role is different'])

def heading_type(text):

    c = canon(text)

    for section, patterns in SECTION_PATTERNS.items():
        if any(
            re.fullmatch(
                pattern,
                c,
                flags=re.I,
            )
            for pattern in patterns
        ):
            return section

    structural = semantic_infer_heading(
        text
    )

    structural_map = {
        "RESPONSIBILITY":
            "responsibilities",
        "REQUIRED":
            "qualifications",
        "PREFERRED":
            "preferred",
        "SUPPORTING":
            "supporting",
        "CONTEXT":
            "ignore",
        "APPLICATION":
            "ignore",
    }

    return structural_map.get(
        structural
    )


def is_structural_leadin(text):
    c = canon(text)
    return any((re.search(pattern + '\\s*:?$', c, flags=re.I) for pattern in STRUCTURAL_LEADINS))

def _realworld_integrity_boilerplate(text):
    value = re.sub(
        r"\s+",
        " ",
        str(text or "").strip(),
    )

    low = value.casefold()

    # Explicit P0 eligibility meaning always outranks page-chrome rules.
    if explicit_p0(value):
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
            r"(?:\s*[-–]\s*[\$£€]?\s*[\d,.]+)?"
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

def _careerops_base_is_page_chrome(text):
    c = canon(text)
    if any((re.fullmatch(pattern, c, flags=re.I) for pattern in PAGE_CHROME_EXACT)):
        return True
    if re.fullmatch('\\d+\\s+(?:days?|months?|hours?)\\s+ago', c, flags=re.I):
        return True
    if re.fullmatch('\\d+(?:k)?\\s*-\\s*\\d+(?:k)?\\s+annually', c, flags=re.I):
        return True
    if re.fullmatch('\\d+\\s+locations?', c, flags=re.I):
        return True
    return False

def is_page_chrome(text):

    if _realworld_integrity_boilerplate(
        text
    ):
        return True

    return _careerops_base_is_page_chrome(
        text
    )


def hard_end_boundary(text):
    c = canon(text)
    return any((re.fullmatch(pattern, c, flags=re.I) for pattern in HARD_END_BOUNDARIES))

def explicit_p0(text):
    if re.fullmatch(r'no (?:previous|prior) .{0,40}experience(?: required)?[.]?', normalize(text),re.I):return False
    return search_any(text, EXPLICIT_P0_SIGNALS)

def responsibility_like(text):
    words = re.findall("[A-Za-z']+", normalize(text))
    if not words:
        return False
    first = words[0].casefold()
    if first == 'acting':return True
    if first in RESPONSIBILITY_VERBS:
        return True
    lower = canon(text)
    return lower.startswith('responsible for ') or lower.startswith('responsibility for ') or lower.startswith('this role ') or lower.startswith('this position ') or lower.startswith('the analyst ') or lower.startswith('the incumbent ')
GENERIC_SPONSORSHIP_REVIEW_PATTERNS = ['\\b(?:we|the employer|the company)?\\s*(?:do|does|will)\\s+not\\s+sponsor\\b', '\\b(?:we|the employer|the company)?\\s*(?:do|does|will)\\s+not\\s+(?:provide|offer)\\b[^.\\n]{0,100}\\b(?:employment\\s+|visa\\s+|work\\s+)?sponsorship\\b', "\\b(?:cannot|can't)\\s+(?:(?:provide|offer)\\s+(?:visa\\s+|employment\\s+|work\\s+)?sponsorship|sponsor\\b[^.\\n]{0,100})", '\\b(?:unable|not\\s+able)\\s+to\\s+(?:(?:provide|offer)\\s+(?:visa\\s+|employment\\s+|work\\s+)?sponsorship|sponsor\\b[^.\\n]{0,100})', '\\bno\\s+(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\b', '\\b(?:visa\\s+|employment\\s+|work\\s+|employer\\s+)?sponsorship\\s+is\\s+not\\s+available\\b', '\\b(?:this\\s+role|this\\s+position|the\\s+role|the\\s+position)\\s+is\\s+not\\s+eligible\\s+for\\s+(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\b', "\\b(?:we|the\\s+employer|the\\s+company)?\\s*(?:cannot|can't|can\\s+not)\\s+(?:provide|offer)\\s+(?:employer\\s+|employment\\s+|visa\\s+|work\\s+)?sponsorship\\b"]
EXPLICIT_SPONSORSHIP_EXCLUSION_PATTERNS = ['\\b(?:current\\s+or\\s+future|now\\s+or\\s+in\\s+the\\s+future)\\b[^.\\n]{0,120}\\b(?:employment\\s+|visa\\s+|work\\s+|employer\\s+)?sponsorship\\b', '\\b(?:employment\\s+|visa\\s+|work\\s+|employer\\s+)?sponsorship\\b[^.\\n]{0,120}\\b(?:current\\s+or\\s+future|now\\s+or\\s+in\\s+the\\s+future)\\b', '\\bmust\\s+not\\s+require\\b[^.\\n]{0,120}\\b(?:employment\\s+|visa\\s+|work\\s+|employer\\s+)?sponsorship\\b', '\\b(?:f-?1|opt|stem\\s+opt)\\b']

def generic_sponsorship_review_only(text):
    value = str(text or '')
    generic = any((re.search(pattern, value, flags=re.I) for pattern in GENERIC_SPONSORSHIP_REVIEW_PATTERNS))
    if not generic:
        return False
    explicit = any((re.search(pattern, value, flags=re.I) for pattern in EXPLICIT_SPONSORSHIP_EXCLUSION_PATTERNS))
    return not explicit

def requirement_like(text, section):
    text = normalize(text)
    if not text:
        return False
    if heading_type(text):
        return False
    if is_structural_leadin(text):
        return False
    if is_page_chrome(text):
        return False
    word_count = len(re.findall('\\b\\w+\\b', text))
    if word_count < 3:
        return False
    if section == 'ignore':
        return False
    if re.search('\\b(?:completes?|performs?)\\s+(?:(?:all\\s+)?other|additional)\\s+duties\\b.*\\bas\\s+assigned\\b', text, re.I):
        return False
    if generic_sponsorship_review_only(text):
        return False
    if section is None and re.match("^[A-Z][A-Za-z'’]+(?:\\s+[A-Z][A-Za-z'’]+){1,6}\\s+-\\s+", text):
        return False
    if section in {'qualifications', 'preferred', 'education', 'supporting'}:
        return True
    if section == 'responsibilities':
        return responsibility_like(text) or word_count >= 6
    return explicit_p0(text) or responsibility_like(text) or bool(re.search('\\b(experience|proficiency|knowledge of|ability to|working knowledge|familiarity with)\\b', text, flags=re.I))

HARD_BLOCKER_SIGNALS.extend([r"\bmust\s+not\s+require\b[^.?!\n]{0,100}\bsponsorship\b[^.?!\n]{0,80}\bnow\s+or\s+in\s+(?:the\s+)?future\b",r"\bmust\s+be\s+(?:a\s+)?(?:u\.?s\.?|united\s+states)\s+citizens?\b"])

def expected_priority(text, section):
    lower = canon(text)
    if section == 'ignore':
        return None
    if generic_sponsorship_review_only(text):
        return None
    if re.fullmatch(r'no (?:previous|prior) .{0,40}experience(?: required)?[.]?',normalize(text),re.I):return 'P3'
    if search_any(text, HARD_BLOCKER_SIGNALS):
        return 'P0'
    if section == 'preferred' or re.search('\\b(preferred|desired|nice to have|bonus|a plus)\\b', lower, flags=re.I):
        return 'P3'
    if re.search(r"\bequivalent combinations? of\b.{0,150}\b(?:education|experience)\b.{0,100}\b(?:considered|accepted)\b",text,re.I):return 'P2'
    if section == 'responsibilities':
        return 'P1'
    if section == 'supporting':
        return 'P2'
    if section in {'qualifications', 'education'}:
        return 'P0'
    if explicit_p0(text):
        return 'P0'
    if responsibility_like(text):
        return 'P1'
    return None

def locate_source_lines(raw_jd):
    rows = []
    current_section = None
    words_seen = 0
    hard_boundary_index = None
    seen_substantive_heading = False
    raw_lines = str(raw_jd or '').splitlines()
    for raw_index, raw in enumerate(raw_lines, start=1):
        text = normalize(raw)
        if not text:
            continue
        words = len(re.findall('\\b\\w+\\b', text))
        words_seen += words
        heading = heading_type(text)
        if heading and heading != 'ignore':
            seen_substantive_heading = True
        boundary_context_ready = seen_substantive_heading and words_seen >= 20 or words_seen >= 80
        if hard_boundary_index is None and boundary_context_ready and hard_end_boundary(text):
            hard_boundary_index = raw_index
        if heading:
            current_section = heading
        elif re.match(r'^(?:the\s+)?(?=[A-Za-z /&-]{0,70}\b(?:analyst|engineer|scientist|manager|specialist|director|coordinator|developer|researcher)\b)[A-Za-z][A-Za-z /&-]{2,80}\s+(?:is embedded|will\b|is responsible|works?\b|reports?\b)', text, re.I):
            current_section = 'responsibilities'
        rows.append({'line': raw_index, 'text': text, 'canon': canon(text), 'tokens': tokens(text), 'heading': heading, 'section': current_section, 'after_hard_boundary': hard_boundary_index is not None and raw_index >= hard_boundary_index})
    return (rows, hard_boundary_index)

def build_requirement_rows(ledger):
    rows = []
    for req in ledger.get('requirements', []) or []:
        quote = normalize(req.get('exact_quote', ''))
        rows.append({'requirement_id': req.get('requirement_id'), 'priority': req.get('priority'), 'section': req.get('section'), 'quote': quote, 'canon': canon(quote), 'tokens': tokens(quote)})
    return rows

def best_requirement_match(source_row, requirement_rows):
    exact = [row for row in requirement_rows if row['canon'] and row['canon'] == source_row['canon']]
    if exact:
        return (exact[0], 1.0)
    source_tokens = source_row['tokens']
    if not source_tokens:
        return (None, 0.0)
    best = None
    best_coverage = 0.0
    for row in requirement_rows:
        overlap = len(source_tokens & row['tokens'])
        coverage = overlap / len(source_tokens) if source_tokens else 0.0
        if coverage > best_coverage:
            best = row
            best_coverage = coverage
    return (best, best_coverage)

def compound_source_line(text):
    c = canon(text)
    if 'majority of the following' in c or 'including the following' in c or 'include the following' in c:
        return True
    if text.count(';') >= 1 or re.search(r'[•▪◦]\s+', text[1:]):
        return True
    comma_count = text.count(',')
    if comma_count >= 5 and len(tokens(text)) >= 18 and (explicit_p0(text) or re.search('\\b(experience|knowledge|skills?|ability)\\b', text, flags=re.I)):
        return True
    return False

def _evaluate_source_semantics(intake, ledger):
    raw_jd = str(intake.get('raw_jd_text') or '')
    source_rows, hard_boundary_index = locate_source_lines(raw_jd)
    requirement_rows = build_requirement_rows(ledger)
    source_word_count = len(re.findall('\\b\\w+\\b', raw_jd))
    source_line_count = len(source_rows)
    requirement_count = len(requirement_rows)
    findings = []
    diagnostics = {}
    # Independent typed-field check: a numeric value remains meaningful under
    # its source label even when it is shorter than ordinary prose.
    field_label = None
    for raw in raw_jd.splitlines():
        text = normalize(raw)
        if not text:continue
        if re.fullmatch(r'(?:minimum|required) years of (?:work |leadership )?experience[:.]?',text,re.I):
            field_label=text;continue
        if field_label and re.fullmatch(r'\d+(?:\.\d+)?',text):
            candidates=[r for r in ledger.get('requirements',[]) if normalize(r.get('exact_quote'))==text and normalize(r.get('source_span',{}).get('qualifier_context_quote'))==field_label]
            if not any(r.get('priority')=='P0' and any(re.search(r'\b'+re.escape(text)+r'\s+years?\b',p,re.I) for p in r.get('experience_years_phrases',[])) for r in candidates):
                findings.append({'code':'STRUCTURED_REQUIRED_YEARS_VALUE_MISSING','severity':'BLOCK','source_label':field_label,'exact_source_value':text})
        field_label=None

    if not requirement_rows:
        findings.append({'code': 'NO_SUBSTANTIVE_JOB_REQUIREMENTS', 'severity': 'BLOCK', 'count': 1, 'reason': 'No substantive job requirements were extracted from the source. Supply a complete current job description; empty ledgers cannot authorize downstream planning or writing.'})
    source_canons = {row['canon'] for row in source_rows if row['canon']}
    ungrounded = []
    for req in requirement_rows:
        if not any(req['canon'] and req['canon'] in source for source in source_canons):
            ungrounded.append({'requirement_id': req['requirement_id'], 'priority': req['priority'], 'quote': req['quote']})
    if ungrounded:
        findings.append({'code': 'UNGROUNDED_REQUIREMENT_TEXT', 'severity': 'BLOCK', 'count': len(ungrounded), 'examples': ungrounded[:10]})
    diagnostics['ungrounded_requirement_count'] = len(ungrounded)
    heading_leaks = []
    for req in requirement_rows:
        if heading_type(req['quote']):
            heading_leaks.append({'requirement_id': req['requirement_id'], 'priority': req['priority'], 'quote': req['quote']})
    if heading_leaks:
        findings.append({'code': 'STRUCTURAL_HEADING_BECAME_REQUIREMENT', 'severity': 'BLOCK', 'count': len(heading_leaks), 'examples': heading_leaks[:10]})
    diagnostics['heading_requirement_count'] = len(heading_leaks)
    source_index_by_canon = defaultdict(list)
    for row in source_rows:
        source_index_by_canon[row['canon']].append(row)
    boundary_leaks = []
    chrome_leaks = []
    for req in requirement_rows:
        matches = source_index_by_canon.get(req['canon'], [])
        if any((row['after_hard_boundary'] for row in matches)):
            boundary_leaks.append({'requirement_id': req['requirement_id'], 'priority': req['priority'], 'quote': req['quote']})
        if is_page_chrome(req['quote']):
            chrome_leaks.append({'requirement_id': req['requirement_id'], 'priority': req['priority'], 'quote': req['quote']})
    if boundary_leaks:
        findings.append({'code': 'POST_JD_BOUNDARY_CONTENT_BECAME_REQUIREMENT', 'severity': 'BLOCK', 'count': len(boundary_leaks), 'examples': boundary_leaks[:12]})
    if chrome_leaks:
        findings.append({'code': 'PAGE_CHROME_BECAME_REQUIREMENT', 'severity': 'BLOCK', 'count': len(chrome_leaks), 'examples': chrome_leaks[:12]})
    diagnostics['hard_end_boundary_line'] = hard_boundary_index
    diagnostics['post_boundary_requirement_count'] = len(boundary_leaks)
    diagnostics['page_chrome_requirement_count'] = len(chrome_leaks)
    substantive_source = []
    for row in source_rows:
        if row['after_hard_boundary']:
            continue
        if requirement_like(row['text'], row['section']):
            expected = expected_priority(row['text'], row['section'])
            matched, coverage = best_requirement_match(row, requirement_rows)
            if compound_source_line(row['text']):
                grounded=[q for q in requirement_rows if q['canon'] and q['canon'] in row['canon']]
                union=set().union(*(tokens(q['quote']) for q in grounded)) if grounded else set()
                wanted=tokens(row['text'])
                coverage=max(coverage,len(union & wanted)/max(1,len(wanted)))
            substantive_source.append({**row, 'expected_priority': expected, 'matched_requirement': matched, 'coverage': coverage})
    deduped_substantive_source = []
    duplicate_substantive_source_rows = []
    seen_substantive_concepts = set()
    for row in substantive_source:
        concept_key = (row.get('canon') or canon(row.get('text', '')), row.get('section'), row.get('expected_priority'))
        if concept_key in seen_substantive_concepts:
            duplicate_substantive_source_rows.append({'line': row.get('line'), 'text': row.get('text'), 'section': row.get('section'), 'expected_priority': row.get('expected_priority')})
            continue
        seen_substantive_concepts.add(concept_key)
        deduped_substantive_source.append(row)
    diagnostics['independent_duplicate_source_requirement_count'] = len(duplicate_substantive_source_rows)
    diagnostics['independent_duplicate_source_requirement_examples'] = duplicate_substantive_source_rows[:10]
    substantive_source = deduped_substantive_source
    diagnostics['independent_source_requirement_count'] = len(substantive_source)
    section_counts = Counter((row['section'] for row in substantive_source if row['section']))
    diagnostics['independent_section_counts'] = dict(section_counts)
    section_coverage = {}
    for section in ['responsibilities', 'qualifications', 'preferred', 'education']:
        rows = [row for row in substantive_source if row['section'] == section]
        if not rows:
            continue
        covered = [row for row in rows if row['coverage'] >= 0.78]
        ratio = len(covered) / len(rows)
        section_coverage[section] = {'source_candidates': len(rows), 'covered': len(covered), 'coverage_ratio': round(ratio, 4)}
        minimum_rows = 2 if section in {'responsibilities', 'qualifications'} else 1
        if len(rows) >= minimum_rows and ratio < 0.6:
            findings.append({'code': 'SUBSTANTIVE_SECTION_UNDEREXTRACTED', 'severity': 'BLOCK', 'section': section, 'source_candidates': len(rows), 'covered': len(covered), 'coverage_ratio': round(ratio, 4), 'examples': [{'line': row['line'], 'text': row['text'], 'coverage': round(row['coverage'], 4)} for row in rows if row['coverage'] < 0.78][:8]})
    diagnostics['section_coverage'] = section_coverage
    priority_misses = []
    for row in substantive_source:
        expected = row['expected_priority']
        if expected not in {'P0', 'P1'}:
            continue
        matched = row['matched_requirement']
        if row['coverage'] < 0.78 or matched is None or matched.get('priority') not in {'P0', 'P1'}:
            priority_misses.append({'line': row['line'], 'expected_priority': expected, 'source_text': row['text'], 'coverage': round(row['coverage'], 4), 'matched_requirement_id': matched.get('requirement_id') if matched else None, 'matched_priority': matched.get('priority') if matched else None})
    p0p1_source_count = sum((1 for row in substantive_source if row['expected_priority'] in {'P0', 'P1'}))
    diagnostics['independent_p0_p1_source_count'] = p0p1_source_count
    diagnostics['p0_p1_integrity_miss_count'] = len(priority_misses)
    ledger_p0p1 = sum((1 for req in requirement_rows if req['priority'] in {'P0', 'P1'}))
    if len(priority_misses) >= 2 or (p0p1_source_count >= 3 and ledger_p0p1 == 0 and priority_misses):
        findings.append({'code': 'P0_P1_SOURCE_CONCEPTS_NOT_PRESERVED', 'severity': 'BLOCK', 'count': len(priority_misses), 'ledger_p0_p1_count': ledger_p0p1, 'examples': priority_misses[:10]})
    source_candidate_count = len(substantive_source)
    collapsed = source_word_count >= 250 and source_candidate_count >= 8 and (requirement_count < max(4, int(source_candidate_count * 0.4)))
    if collapsed:
        findings.append({'code': 'LARGE_JD_COLLAPSED_TO_TOO_FEW_REQUIREMENTS', 'severity': 'BLOCK', 'source_word_count': source_word_count, 'source_candidate_count': source_candidate_count, 'requirement_count': requirement_count})
    diagnostics['large_jd_collapse'] = collapsed
    priority_counts = Counter((req['priority'] for req in requirement_rows if req['priority']))
    dominant_priority = None
    dominant_share = 0.0
    if requirement_count:
        dominant_priority, dominant_count = priority_counts.most_common(1)[0]
        dominant_share = dominant_count / requirement_count
    source_major_sections = {row['section'] for row in substantive_source if row['section'] in {'responsibilities', 'qualifications', 'preferred', 'education'}}
    suspicious_priority_collapse = requirement_count >= 10 and dominant_share >= 0.85 and (len(source_major_sections) >= 2)
    all_p2_collapse = requirement_count >= 3 and requirement_count > 0 and (priority_counts.get('P2', 0) == requirement_count) and (p0p1_source_count >= 3)
    if suspicious_priority_collapse or all_p2_collapse:
        findings.append({'code': 'PRIORITY_DISTRIBUTION_COLLAPSE', 'severity': 'BLOCK', 'requirement_count': requirement_count, 'priority_counts': dict(priority_counts), 'dominant_priority': dominant_priority, 'dominant_share': round(dominant_share, 4), 'source_major_sections': sorted(source_major_sections), 'independent_p0_p1_source_count': p0p1_source_count})
    diagnostics['priority_counts'] = dict(priority_counts)
    diagnostics['dominant_priority'] = dominant_priority
    diagnostics['dominant_priority_share'] = round(dominant_share, 4)
    compound_misses = []
    for row in substantive_source:
        if not compound_source_line(row['text']):
            continue
        if row['coverage'] < 0.82:
            matched = row['matched_requirement']
            compound_misses.append({'line': row['line'], 'source_text': row['text'], 'coverage': round(row['coverage'], 4), 'matched_requirement_id': matched.get('requirement_id') if matched else None, 'matched_quote': matched.get('quote') if matched else None})
    if compound_misses:
        findings.append({'code': 'PARTIAL_COMPOUND_REQUIREMENT', 'severity': 'BLOCK', 'count': len(compound_misses), 'examples': compound_misses[:8]})
    diagnostics['partial_compound_count'] = len(compound_misses)
    blocking = [finding for finding in findings if finding.get('severity') == 'BLOCK']
    status = 'PASS' if not blocking else 'FAIL_CLOSED'
    return {'schema_version': 'requirement-integrity-gate-v1', 'gate': 'UNIVERSAL_JD_REQUIREMENT_INTEGRITY', 'status': status, 'failure_class': None if status == 'PASS' else 'REQUIREMENTS', 'model_calls': 0, 'source': {'source_type': intake.get('source_type'), 'source_url': intake.get('source_url'), 'word_count': source_word_count, 'line_count': source_line_count}, 'ledger': {'schema_version': ledger.get('schema_version'), 'requirement_count': requirement_count, 'priority_counts': dict(priority_counts)}, 'checks': {'all_requirement_text_grounded': not ungrounded, 'no_structural_headings_as_requirements': not heading_leaks, 'no_page_chrome_as_requirements': not chrome_leaks, 'no_post_boundary_requirements': not boundary_leaks, 'substantive_sections_preserved': not any((x['code'] == 'SUBSTANTIVE_SECTION_UNDEREXTRACTED' for x in findings)), 'p0_p1_concepts_preserved': not any((x['code'] == 'P0_P1_SOURCE_CONCEPTS_NOT_PRESERVED' for x in findings)), 'no_large_jd_collapse': not collapsed, 'priority_distribution_plausible': not (suspicious_priority_collapse or all_p2_collapse), 'compound_requirements_complete': not compound_misses}, 'diagnostics': diagnostics, 'findings': findings, 'blocking_findings': [x['code'] for x in blocking], 'policy': {'independent_of_extractor_section_labels': True, 'independent_original_jd_comparison': True, 'deterministic_only': True, 'candidate_evidence_used': False, 'market_prior_used': False, 'semantic_model_used': False, 'fail_closed_on_integrity_defect': True}}

def evaluate(intake, ledger):

    #
    # Integrity independently compares ORIGINAL JD to the immutable
    # extractor source ledger. Semantic sidecar/effective requirements
    # remain downstream, exactly as the architecture specifies.

    result = _evaluate_source_semantics(
        intake,
        ledger,
    )

    result.setdefault(
        "diagnostics",
        {},
    )[
        "semantic_sidecar"
    ] = {
        "status":
            "DEFERRED_UNTIL_AFTER_REQUIREMENT_INTEGRITY",
        "source_requirement_count":
            len(
                ledger.get(
                    "requirements",
                    [],
                )
                or []
            ),
        "effective_requirement_count":
            None,
        "unresolved_source_anchor_count":
            None,
        "ambiguous_source_anchor_count":
            None,
        "document_constraint_count":
            None,
    }

    result.setdefault(
        "policy",
        {},
    ).update({
        "semantic_authority":
            "IMMUTABLE_SOURCE_REQUIREMENT_LEDGER",
        "raw_source_ledger_mutated":
            False,
        "semantic_sidecar_stage":
            "DOWNSTREAM_ONLY",
    })

    return result


def load_json(path):
    if not path.exists():
        raise SystemExit(f'Missing required file: {path}')
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    ap = argparse.ArgumentParser(description='Career-Ops V2 universal JD requirement integrity gate.')
    ap.add_argument('--intake', default=str(DEFAULT_INTAKE))
    ap.add_argument('--requirements', default=str(DEFAULT_REQUIREMENTS))
    ap.add_argument('--output', default=str(DEFAULT_OUTPUT))
    ap.add_argument('--no-fail', action='store_true', help='Write/report FAIL_CLOSED without returning non-zero. For deterministic fixture inspection only.')
    args = ap.parse_args()
    intake_path = Path(args.intake)
    requirements_path = Path(args.requirements)
    output_path = Path(args.output)
    intake = load_json(intake_path)
    ledger = load_json(requirements_path)
    result = evaluate(intake, ledger)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('REQUIREMENT INTEGRITY GATE:', result['status'])
    print('SOURCE WORDS:', result['source']['word_count'])
    print('REQUIREMENTS:', result['ledger']['requirement_count'])
    print('BLOCKING FINDINGS:', ', '.join(result['blocking_findings']) if result['blocking_findings'] else 'NONE')
    print('OUTPUT:', output_path)
    if result['status'] != 'PASS' and (not args.no_fail):
        raise SystemExit(1)
if __name__ == '__main__':
    main()
