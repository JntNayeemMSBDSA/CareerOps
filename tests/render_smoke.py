"""Synthetic HTML/payload and LibreOffice DOCX rendering smoke; no writer or release."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    runtime=ROOT/".local-checks/render/runtime";runtime.mkdir(parents=True,exist_ok=True)
    facts=json.loads((ROOT/"examples/source/candidate_facts.json").read_text())
    source={"summary":"Analytics engineer applying SQL, Python and source reconciliation to fictional museum reporting.","experience":[{"block_id":row["block_id"],"company":row["organization"],"title":row["title"],"dates":row["period"],"bullets":[bullet]} for row,bullet in zip(facts["experience_blocks"],["Validated 240,000 fictional ticket events in DuckDB and Parquet with SQL reconciliation and pytest checks.","Designed Power BI dashboards for 27 fictional delivery zones using DAX measures and SQL reconciliation."])],"projects":[{"entity_id":"PRJ-101","name":"Library return-risk classifier","bullets":["Evaluated a logistic classifier on 8,400 synthetic loans using stratified cross-validation and leakage checks."]},{"entity_id":"PRJ-102","name":"Community garden measurement study","bullets":["Analyzed 96 synthetic garden plots with bootstrap confidence intervals and input validation."]}],"skills":[{"category":"Programming & Data Analysis","terms":["SQL","Python","pandas","NumPy","SQL Joins"]},{"category":"BI & Spreadsheet Analytics","terms":["Power BI","DAX","Power Query","Excel","Dashboard Development"]}],"education":facts["education"]}
    (runtime/"generated_resume_content.json").write_text(json.dumps(source))
    (runtime/"role_routing.json").write_text(json.dumps({"input":{"target_title_candidate":"Data Analyst"}}))
    (runtime/"summary_route.json").write_text(json.dumps({"mode":"ONE_LINE"}))
    env=os.environ.copy();env.update(CAREEROPS_SOURCE_DIR="examples/source",CAREEROPS_RUNTIME_DIR=str(runtime),CAREEROPS_RESUME_INPUT=str(runtime/"generated_resume_content.json"),CAREEROPS_RESUME_OUTPUT=str(runtime/"synthetic-resume.docx"))
    subprocess.run([sys.executable,"-B","scripts/careerops_build_cv_payload.py"],cwd=ROOT,env=env,check=True)
    validation=json.loads((runtime/"career_ops_cv_payload_validation.json").read_text());assert not validation["adapter_errors"] and validation["career_ops_exit_code"]==0
    env["CAREEROPS_RESUME_INPUT"]=str(runtime/"career_ops_cv_payload.json")
    subprocess.run([sys.executable,"-B","scripts/careerops_docx_renderer.py"],cwd=ROOT,env=env,check=True)
    audit=json.loads((runtime/"docx_layout/synthetic-resume/layout_audit.json").read_text());assert audit["pass"] and audit["pages"]==1
    print("Synthetic HTML/payload and rendered DOCX layout: PASS; no model or release")
if __name__=="__main__":main()
