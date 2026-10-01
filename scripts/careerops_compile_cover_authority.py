"""Compile the existing compact cover authority without duplicating inventories."""
import hashlib,json
from pathlib import Path

def compile_cover_authority(path):
 path=Path(path);rules=json.loads(path.read_text())
 return {'schema_version':'compiled-cover-authority-v1','source_path':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'purpose':rules['purpose'],'paragraph_contract':rules['paragraph_contract'],
         'evidence_selection':rules['evidence_selection'],'numerical_evidence':rules['numerical_evidence'],
         'writing':rules['writing'],'truth_rules':rules['truth_rules'],'jd_terminology':rules['jd_terminology'],
         'draft_checklist':[
          'Open with concrete candidate work; name the exact employer and application title.',
          'Develop one dominant story in paragraph 2, the longest paragraph: problem, context, personal judgment, mechanics, validation, supported output, and role analogy.',
          'Use two supported numerical anchors with their correct units and owner when the plan supplies them.',
          'Make paragraph 3 depend on this employer output, dataset, stakeholder or product; test whether swapping the employer makes it inaccurate.',
          'Vary sentence lengths and syntax. Read the letter aloud as natural professional American English.',
          'Use technical tools inside the story, without inventory sentences or future keyword stacks.',
          'Do not paraphrase resume bullets into successive sentences. Do not invent familiarity, employer praise, or facts.',
         ],'source_rules_changed':False,'second_model_analysis':False}
