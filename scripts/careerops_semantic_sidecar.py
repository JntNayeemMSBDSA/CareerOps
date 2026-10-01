import argparse
import hashlib
import json
import re
from pathlib import Path

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def normalize(value):
    value = str(value or '')
    value = value.replace('\r\n', '\n').replace('\r', '\n').replace('’', "'").casefold()
    value = re.sub('^[*•▪◦‣⁃]\\s+', '', value)
    value = re.sub('\\s+', ' ', value)
    return value.strip(' \t\r\n.:;-•▪◦‣⁃')

def heading_key(value):
    value = normalize(value)
    value = value.replace('&', ' and ')
    value = re.sub("[^a-z0-9'+]+", ' ', value)
    return re.sub('\\s+', ' ', value).strip()

def infer_heading(text):
    original = str(text or '').strip()
    key = heading_key(original)
    if not key:
        return None
    words = key.split()
    if len(words) > 20 or len(original) > 180:
        return None
    if original.endswith(('.', '?', '!')):
        return None
    if re.fullmatch(r"(?:job responsibilities|(?:[\w]+[ ]+){1,5}analytics|(?:[\w]+[ ]+){1,5}analysis|data craft and practice)", key):
        return 'RESPONSIBILITY'
    if re.fullmatch(r"(?:basic qualifications|job requirements|experience and skills)", key):
        return 'REQUIRED'
    if re.fullmatch(r"(?:description|how we work|who we are|videos to ?watch|(?:the )?(?:company |corporate )?culture(?: at .+)?|corporate philanthropy|what we offer(?: you)?|about .+)", key):
        return 'CONTEXT'
    if re.fullmatch('(?:licenses?|licences?|licensure|certifications?)(?:\\s+and\\s+(?:licenses?|licences?|certifications?))?\\s+required', key):
        return 'REQUIRED'
    if re.fullmatch('(?:preferred|preferred qualifications?|preferred experience|preferred skills?|desired|desired qualifications?|desired experience|desired qualities?|desired attributes?|desired characteristics?|desirable|desirable qualifications?|desirable experience|nice to have|nice to haves|bonus qualifications?)', key):
        return 'PREFERRED'
    if re.fullmatch('(?:primary duties?|duties|essential functions?|primary duties essential functions|responsibility|responsibilities|accountabilities|what you ll do|what you will do|your impact|key activities|job duties)', key):
        return 'RESPONSIBILITY'
    if re.fullmatch('(?:required|minimum|mandatory)\\s+(?:education|experience|qualifications?|requirements?|skills?|knowledge|abilities|competencies|licenses?|licences?|licensure|certifications?|education and experience|experience and education)', key):
        return 'REQUIRED'
    if re.fullmatch('(?:requirements?|qualifications?|minimum qualifications?|minimum requirements?|education requirements?|experience requirements?|education and experience|experience and education|skills and qualifications|skills qualifications|qualifications knowledge and skill requirements|qualifications knowledge and skills requirements|qualifications knowledge and skill|qualifications knowledge and skills|what you ll need|what you will need|what it takes|what you ll bring|what you will bring|about you|the person|who you are)', key):
        return 'REQUIRED'
    if re.fullmatch('(?:skills?|knowledge skills and abilities|knowledge skills abilities|key competencies|core competencies|technical competencies|skills and abilities|mental demands?|technologies|technology skills?|technical skills?)', key):
        return 'SUPPORTING'
    if re.fullmatch('(?:application questions?|screening questions?|how to apply|application process)', key):
        return 'APPLICATION'
    if re.fullmatch('(?:job summary|position summary|role summary|job description|position description|role description|position overview|role overview|job overview|about us|about the company|our company|our story|company overview|notes to candidate)', key):
        return 'CONTEXT'
    if re.match('^(?:benefits?|perks?|compensation|pay range|salary range|location|work location|job location|workplace|schedule|work schedule|hours|physical demands?|visual demands?|environment|work environment|contact|faq|share this job|position id|posting details|special instructions to applicants)(?:\\b|$)', key):
        return 'CONTEXT'
    if re.fullmatch('(?:equal opportunity|equal employment|eeo|privacy|accommodation|legal notice)', key):
        return 'CONTEXT'
    return None

def source_sections(raw_jd):
    lines = str(raw_jd or '').splitlines()
    current = None
    current_heading_line = None
    current_heading_text = None
    mapping = {}
    for number, raw in enumerate(lines, start=1):
        stripped = str(raw or '').strip()
        heading = infer_heading(stripped)
        if heading:
            current = heading
            current_heading_line = number
            current_heading_text = stripped
            mapping[number] = {'section': current, 'is_heading': True, 'heading_line': current_heading_line, 'heading_text': current_heading_text}
            continue
        mapping[number] = {'section': current, 'is_heading': False, 'heading_line': current_heading_line, 'heading_text': current_heading_text}
    return (lines, mapping)

def ledger_section_family(value):
    key = normalize(value)
    if not key:
        return None
    if key in {'required', 'education', 'experience', 'minimum', 'qualifications', 'license', 'certification'}:
        return 'REQUIRED'
    if key in {'responsibility', 'responsibilities', 'duties', 'duty'}:
        return 'RESPONSIBILITY'
    if key in {'preferred', 'desired'}:
        return 'PREFERRED'
    if key in {'supporting', 'skills', 'competencies', 'ksa'}:
        return 'SUPPORTING'
    if key in {'context', 'ignore', 'benefits', 'compensation', 'location', 'schedule'}:
        return 'CONTEXT'
    return None

def requirement_signal(text):
    c = normalize(text)
    return bool(re.search("\\b(required|must|minimum|mandatory|shall)\\b|\\bbachelor'?s?\\b|\\bmaster'?s?\\b|\\bdoctorate\\b|\\b(?:one|two|three|four|five|six|seven|eight|nine|ten)(?:\\s+to\\s+(?:one|two|three|four|five|six|seven|eight|nine|ten))?\\s+years?\\b|\\b\\d+\\s*(?:to|-|–|—)\\s*\\d+\\s+years?\\b|\\b\\d+\\+?\\s+years?\\b", c))

def explicit_preference_signal(text):
    return bool(re.search('\\b(preferred|desired|desirable|nice to have|nice-to-have|a plus)\\b', normalize(text)))

def normalized_window(lines, start, end):
    return normalize(' '.join((str(lines[i] or '').strip() for i in range(start, end) if str(lines[i] or '').strip())))

def candidate_source_anchors(lines, section_map, row):
    quote = row.get('exact_quote', '')
    target = normalize(quote)
    if not target:
        return []
    ledger_family = ledger_section_family(row.get('section'))
    candidates = []

    def add(start, end, method, method_score):
        meta = section_map.get(start, {})
        raw_section = meta.get('section')
        score = method_score
        if ledger_family and raw_section == ledger_family:
            score += 30
        if explicit_preference_signal(quote) and raw_section == 'PREFERRED':
            score += 30
        candidates.append({'start_line': start, 'end_line': end, 'method': method, 'base_score': score, 'raw_section': raw_section, 'heading_line': meta.get('heading_line'), 'heading_text': meta.get('heading_text')})
    # A canonical span is trusted only after hashing the original physical
    # line and checking that its slice yields this exact source quote.
    span = row.get('source_span') or {}
    number = span.get('physical_line')
    if isinstance(number, int) and 1 <= number <= len(lines):
        original = lines[number - 1]
        start, end = span.get('start_char'), span.get('end_char')
        if (hashlib.sha256(original.encode()).hexdigest() == span.get('original_line_sha256')
                and isinstance(start, int) and isinstance(end, int)
                and 0 <= start < end <= len(original)
                and normalize(original[start:end]) == target):
            add(number, number, 'EXACT_SOURCE_SPAN', 100)
            candidates[-1].update(start_char=start, end_char=end)
            return candidates
    exact = []
    for index, line in enumerate(lines, start=1):
        if normalize(line) == target:
            exact.append(index)
    if exact:
        for index in exact:
            add(index, index, 'EXACT_RAW_LINE', 100)
        return candidates
    for width in range(2, 8):
        if width > len(lines):
            break
        for zero_start in range(0, len(lines) - width + 1):
            joined = normalized_window(lines, zero_start, zero_start + width)
            if joined == target:
                add(zero_start + 1, zero_start + width, 'EXACT_RAW_WINDOW', 95)
    if candidates:
        return candidates
    if len(target) >= 45:
        for index, line in enumerate(lines, start=1):
            candidate = normalize(line)
            if candidate and (target in candidate or candidate in target):
                add(index, index, 'RAW_LINE_CONTAINMENT', 65)
    return candidates

def _transition_score(previous, current):
    if previous is None:
        return 0.0
    prev_line = previous.get('start_line')
    curr_line = current.get('start_line')
    if prev_line is None or curr_line is None:
        return -100.0
    if curr_line < prev_line:
        return -1000000.0
    gap = curr_line - prev_line
    return -min(gap, 500) * 0.002

def align_requirement_sequence(lines, section_map, rows):
    if not rows:
        return []
    candidate_sets = []
    for row in rows:
        candidates = candidate_source_anchors(lines, section_map, row)
        if not candidates:
            candidates = [{'start_line': None, 'end_line': None, 'method': 'UNRESOLVED', 'base_score': -10000.0, 'raw_section': None, 'heading_line': None, 'heading_text': None}]
        candidate_sets.append(candidates)
    dp = []
    back = []
    for i, candidates in enumerate(candidate_sets):
        row_scores = []
        row_back = []
        for j, candidate in enumerate(candidates):
            base = float(candidate.get('base_score', 0.0))
            if i == 0:
                row_scores.append(base)
                row_back.append(None)
                continue
            best_score = None
            best_k = None
            for k, previous in enumerate(candidate_sets[i - 1]):
                prior = dp[i - 1][k]
                transition = _transition_score(previous, candidate)
                if transition <= -999999:
                    continue
                score = prior + base + transition
                if best_score is None or score > best_score:
                    best_score = score
                    best_k = k
            if best_score is None:
                best_score = base - 100000.0
                best_k = None
            row_scores.append(best_score)
            row_back.append(best_k)
        dp.append(row_scores)
        back.append(row_back)
    last_index = max(range(len(dp[-1])), key=lambda j: dp[-1][j])
    selected = [None] * len(rows)
    cursor = last_index
    for i in range(len(rows) - 1, -1, -1):
        selected[i] = dict(candidate_sets[i][cursor])
        previous_cursor = back[i][cursor]
        if i > 0 and previous_cursor is None:
            selected[i]['sequence_alignment_failed'] = True
            cursor = max(range(len(candidate_sets[i - 1])), key=lambda j: candidate_sets[i - 1][j].get('base_score', -10000))
        elif i > 0:
            cursor = previous_cursor
    for i, selected_candidate in enumerate(selected):
        candidates = candidate_sets[i]
        selected_candidate['candidate_count'] = len(candidates)
        semantic_signatures = {(candidate.get('raw_section'), candidate.get('heading_text')) for candidate in candidates if candidate.get('start_line') is not None}
        selected_candidate['ambiguous'] = bool(selected_candidate.get('sequence_alignment_failed') or (len(semantic_signatures) > 1 and len(candidates) > 1 and (selected_candidate.get('start_line') is None)))
        selected_candidate['confidence'] = 'HIGH' if selected_candidate.get('start_line') is not None and (not selected_candidate['ambiguous']) and (selected_candidate.get('method') in {'EXACT_RAW_LINE', 'EXACT_RAW_WINDOW', 'EXACT_SOURCE_SPAN'}) else 'MEDIUM' if selected_candidate.get('start_line') is not None else 'NONE'
    return selected

def resolve_source_anchor(lines, section_map, row):
    aligned = align_requirement_sequence(lines, section_map, [row])
    return aligned[0]

def fallback_find_line(lines, quote):
    target = normalize(quote)
    if not target:
        return None
    for index, line in enumerate(lines, start=1):
        if normalize(line) == target:
            return index
    for width in range(2, 8):
        for zero_start in range(0, max(0, len(lines) - width + 1)):
            if normalized_window(lines, zero_start, zero_start + width) == target:
                return zero_start + 1
    return None

def choose_semantic_section(row, anchor):
    raw_section = anchor.get('raw_section')
    ledger_section = ledger_section_family(row.get('section'))
    quote = row.get('exact_quote', '')
    if explicit_preference_signal(quote):
        return ('PREFERRED', 'EXPLICIT_INLINE_PREFERENCE')
    if raw_section in {'REQUIRED', 'RESPONSIBILITY', 'PREFERRED', 'SUPPORTING', 'APPLICATION'}:
        return (raw_section, 'RAW_HEADING')
    if raw_section == 'CONTEXT' and ledger_section in {'REQUIRED', 'RESPONSIBILITY', 'PREFERRED', 'SUPPORTING'}:
        if requirement_signal(quote) or ledger_section in {'RESPONSIBILITY', 'PREFERRED'}:
            return (ledger_section, 'LEDGER_CORROBORATED_OVER_INHERITED_CONTEXT')
    if raw_section == 'CONTEXT':
        return ('CONTEXT', 'RAW_CONTEXT_HEADING')
    if ledger_section:
        return (ledger_section, 'LEDGER_SECTION_FALLBACK')
    return (None, 'NO_SECTION_EVIDENCE')

def fallback_find_line(lines, quote):
    target = normalize(quote)
    if not target:
        return None
    for index, line in enumerate(lines, start=1):
        if normalize(line) == target:
            return index
    for width in range(2, 7):
        for zero_start in range(0, max(0, len(lines) - width + 1)):
            joined = normalized_window(lines, zero_start, zero_start + width)
            if joined == target or (len(target) >= 40 and target in joined):
                return zero_start + 1
    return None

def company_history(text):
    return bool(re.match('^(?:for\\s+(?:over|more than)\\s+\\d+\\s+years|(?:we|our|the company|the organization)\\b)', normalize(text)))

def obvious_context(text):
    c = normalize(text)
    return bool(re.search('^\\$[\\d,]+|^\\d+\\s*-\\s*\\d+\\s*(?:usd|dollars?)|\\bpay range\\b|\\bsalary range\\b|\\bposition location\\b|\\bwork location\\b|\\bmonday through friday\\b', c))

def relation_for(text):
    c = normalize(text)
    if re.search('\\b(substitut|in lieu of)\\w*\\b', c):
        return 'SUBSTITUTION'
    if re.search('\\b(equivalent combination|or equivalent)\\b', c):
        return 'EQUIVALENT'
    if re.search('\\bplus\\b', c):
        return 'AND'
    if 'and/or' in c:
        return 'OR'
    if re.search('\\bor\\b', c):
        return 'OR'
    if re.search('\\band\\b', c):
        return 'AND'
    return 'ATOMIC'

def classify(row, source_section):
    quote = row.get('exact_quote', '')
    c = normalize(quote)
    original_priority = row.get('priority')
    hard_blockers = row.get('hard_blocker_phrases', []) or []
    if hard_blockers:
        return {'semantic_class': 'HARD_BLOCK', 'effective_priority': 'P0', 'modality': 'REQUIRED', 'active_for_decision': True, 'confidence': 'HIGH', 'reason_codes': ['EXPLICIT_HARD_BLOCKER_PHRASE']}
    if re.search('^\\s*(?:salary|pay|compensation)(?:\\s+range)?\\s*:?\\s*\\$\\s*\\d', str(quote or ''), flags=re.I):
        return {'semantic_class': 'CONTEXT', 'effective_priority': None, 'modality': 'METADATA', 'active_for_decision': False, 'confidence': 'HIGH', 'reason_codes': ['COMPENSATION_METADATA']}
    if re.search('^\\s*internal\\s+(?:applicants?|candidates?|employees?)\\b', str(quote or ''), flags=re.I):
        return {'semantic_class': 'CONTEXT', 'effective_priority': None, 'modality': 'CONDITIONAL_APPLICABILITY', 'active_for_decision': False, 'confidence': 'HIGH', 'reason_codes': ['INTERNAL_APPLICANT_SCOPE_ONLY']}
    if c in {'none', 'n/a', 'na', 'not applicable', 'not required'}:
        return {'semantic_class': 'CONTEXT', 'effective_priority': None, 'modality': 'EMPTY_VALUE', 'active_for_decision': False, 'confidence': 'HIGH', 'reason_codes': ['STRUCTURAL_EMPTY_VALUE']}
    if source_section == 'APPLICATION' and quote.rstrip().endswith('?'):
        return {'semantic_class': 'APPLICATION_QUESTION', 'effective_priority': None, 'modality': 'QUESTION', 'active_for_decision': False, 'confidence': 'HIGH', 'reason_codes': ['APPLICATION_QUESTION_SECTION']}
    if source_section == 'CONTEXT':
        return {'semantic_class': 'CONTEXT', 'effective_priority': None, 'modality': 'METADATA', 'active_for_decision': False, 'confidence': 'HIGH', 'reason_codes': ['CONTEXT_SECTION']}
    if explicit_preference_signal(quote):
        return {'semantic_class': 'PREFERRED', 'effective_priority': 'P3', 'modality': 'PREFERRED', 'active_for_decision': True, 'confidence': 'HIGH', 'reason_codes': ['EXPLICIT_INLINE_PREFERENCE']}
    if source_section == 'PREFERRED':
        return {'semantic_class': 'PREFERRED', 'effective_priority': 'P3', 'modality': 'PREFERRED', 'active_for_decision': True, 'confidence': 'HIGH', 'reason_codes': ['PREFERRED_SECTION']}
    if original_priority == 'P0' and row.get('priority_basis') == 'structured_required_qualification':
        return {'semantic_class': 'REQUIRED', 'effective_priority': 'P0', 'modality': 'REQUIRED', 'active_for_decision': True, 'confidence': 'HIGH', 'reason_codes': ['SOURCE_STRUCTURED_REQUIRED_QUALIFICATION']}
    if source_section == 'RESPONSIBILITY':
        return {'semantic_class': 'RESPONSIBILITY', 'effective_priority': 'P1', 'modality': 'CORE_WORK', 'active_for_decision': True, 'confidence': 'HIGH', 'reason_codes': ['RESPONSIBILITY_SECTION']}
    if source_section == 'SUPPORTING':
        return {'semantic_class': 'SUPPORTING', 'effective_priority': 'P2', 'modality': 'SUPPORTING', 'active_for_decision': True, 'confidence': 'HIGH', 'reason_codes': ['KSA_OR_COMPETENCY_SECTION']}
    if source_section == 'REQUIRED':
        return {'semantic_class': 'REQUIRED', 'effective_priority': 'P0', 'modality': 'REQUIRED', 'active_for_decision': True, 'confidence': 'HIGH', 'reason_codes': ['REQUIRED_SECTION']}
    if re.search("\\b(required|must|minimum|mandatory|shall)\\b|\\bbachelor'?s?\\b|\\bmaster'?s?\\b", c):
        return {'semantic_class': 'REQUIRED', 'effective_priority': 'P0', 'modality': 'REQUIRED', 'active_for_decision': True, 'confidence': 'MEDIUM', 'reason_codes': ['INLINE_REQUIRED_SIGNAL']}
    semantic_class = {'P0': 'REQUIRED', 'P1': 'RESPONSIBILITY', 'P2': 'SUPPORTING', 'P3': 'PREFERRED'}.get(original_priority, 'UNKNOWN')
    return {'semantic_class': semantic_class, 'effective_priority': original_priority, 'modality': 'SOURCE_LEDGER_FALLBACK', 'active_for_decision': True, 'confidence': 'LOW', 'reason_codes': ['SOURCE_LEDGER_FALLBACK']}

def build_sidecar(intake, ledger, intake_sha=None, ledger_sha=None):
    raw_jd = intake.get('raw_jd_text', '')
    lines, section_map = source_sections(raw_jd)
    rows = ledger.get('requirements', []) or []
    anchors = align_requirement_sequence(lines, section_map, rows)
    annotations = []
    disagreements = []
    unresolved_source_anchors = []
    ambiguous_source_anchors = []
    for row, anchor in zip(rows, anchors):
        requirement_id = row.get('requirement_id')
        semantic_section, section_basis = choose_semantic_section(row, anchor)
        semantic = classify(row, semantic_section)
        semantic['proposed_priority']=semantic.get('effective_priority')
        semantic['effective_priority']=row.get('priority')
        semantic['canonical_section']=row.get('section')
        relation = relation_for(row.get('exact_quote', ''))
        disagreement = bool(semantic.get('effective_priority') != row.get('priority') or semantic.get('active_for_decision') is False)
        annotation = {'requirement_id': requirement_id, 'exact_quote': row.get('exact_quote', ''), 'source_priority': row.get('priority'), 'ledger_section': row.get('section'), 'ledger_jd_line': row.get('jd_line'), 'source_anchor_start_line': anchor.get('start_line'), 'source_anchor_end_line': anchor.get('end_line'), 'source_anchor_method': anchor.get('method'), 'source_anchor_confidence': anchor.get('confidence'), 'source_anchor_candidate_count': anchor.get('candidate_count', 0), 'source_anchor_ambiguous': anchor.get('ambiguous', False), 'raw_source_section': anchor.get('raw_section'), 'raw_heading_line': anchor.get('heading_line'), 'raw_heading_text': anchor.get('heading_text'), 'source_section': semantic_section, 'source_section_basis': section_basis, **semantic, 'qualification_relation': relation, 'disagreement_with_source_ledger': disagreement}
        annotations.append(annotation)
        if anchor.get('start_line') is None:
            unresolved_source_anchors.append(requirement_id)
        if anchor.get('ambiguous'):
            ambiguous_source_anchors.append(requirement_id)
        if disagreement:
            disagreements.append(requirement_id)
    return {'schema_version': 'career-ops-jd-semantic-sidecar-v1.4', 'mode': 'SHADOW_ONLY', 'policy': {'raw_jd_rewritten': False, 'source_ledger_modified': False, 'requirement_ids_preserved': True, 'semantic_layer_may_delete_requirement': False, 'semantic_layer_may_authorize_rejection': False, 'quote_anchor_precedes_numeric_line_hint': True, 'global_monotonic_source_alignment': True, 'duplicate_physical_occurrence_is_not_automatically_semantic_ambiguity': True, 'ledger_section_is_corroborating_evidence': True, 'short_requirement_sentences_are_not_headings': True, 'explicit_preference_overrides_broad_required_parent_section': True, 'supporting_capability_is_active_but_non_rejection_priority': True, 'source_alignment_uncertainty_requires_review': True}, 'source': {'source_type': intake.get('source_type'), 'source_url': intake.get('source_url'), 'target_role_title_candidate': ledger.get('target_role_title_candidate'), 'intake_sha256': intake_sha, 'ledger_sha256': ledger_sha, 'requirement_count': len(rows)}, 'annotations': annotations, 'unresolved_source_anchor_ids': unresolved_source_anchors, 'unresolved_source_anchor_count': len(unresolved_source_anchors), 'ambiguous_source_anchor_ids': ambiguous_source_anchors, 'ambiguous_source_anchor_count': len(ambiguous_source_anchors), 'disagreement_requirement_ids': disagreements, 'disagreement_count': len(disagreements)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--intake', required=True)
    parser.add_argument('--requirements', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    intake_path = Path(args.intake)
    requirements_path = Path(args.requirements)
    output_path = Path(args.output)
    intake = json.loads(intake_path.read_text(encoding='utf-8'))
    ledger = json.loads(requirements_path.read_text(encoding='utf-8'))
    result = build_sidecar(intake, ledger, sha256(intake_path), sha256(requirements_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('SEMANTIC SIDECAR: CREATED')
    print('MODE:', result['mode'])
    print('SOURCE REQUIREMENTS:', result['source']['requirement_count'])
    print('ANNOTATIONS:', len(result['annotations']))
    print('DISAGREEMENTS:', result['disagreement_count'])
    print('OUTPUT:', output_path)
if __name__ == '__main__':
    main()
