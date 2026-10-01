"""Copy authenticated document quartets to a clean, flat collection.

This has delivery authority only. It never mutates canonical artifacts, gates,
release decisions or model state. Receipts and staging stay outside Daily Output.
"""
from pathlib import Path
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from zoneinfo import ZoneInfo

KEYS=("resume_pdf","resume_docx","cover_pdf","cover_docx")
ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish_validated_result(result, *, root=ROOT):
    root=Path(root).resolve();rid=str(result.get("run_id", ""))
    if result.get("status") not in {"RELEASE_READY","USER_OVERRIDE_GENERATED"}:
        return {"status":"NOT_ELIGIBLE","authority":"DELIVERY_ONLY","model_calls":0,"writer_calls":0}
    if not re.fullmatch(r"[A-Za-z0-9._-]+",rid) or rid in {".",".."}:raise ValueError("Invalid parent identity")
    from careerops_run_outcome import emit_run_outcome
    # Re-resolve through the official authority, never accept caller-supplied
    # status, canonical paths or override-child mappings as authentication.
    result=emit_run_outcome(rid, result.get("process_rc"), root=root, export_daily_output=False)
    if result.get("status") not in {"RELEASE_READY","USER_OVERRIDE_GENERATED"}:
        return {"status":"NOT_ELIGIBLE","authority":"DELIVERY_ONLY","model_calls":0,"writer_calls":0}
    delivered=result.get("delivery",{})
    if delivered.get("status")!="AVAILABLE" or set(delivered.get("files",{}))!=set(KEYS):
        return {"status":"INCOMPLETE_AUTHENTICATED_QUARTET","authority":"DELIVERY_ONLY","model_calls":0,"writer_calls":0}
    if delivered.get("open_actions",{}).get("run_id")!=rid:raise ValueError("Cross-job delivery identity")
    override=result["status"]=="USER_OVERRIDE_GENERATED"
    expected="USER_OVERRIDE_UNRELEASED" if override else "RELEASED"
    if delivered.get("disposition")!=expected or override and result.get("release_ready"):raise ValueError("Delivery disposition conflict")
    directory=root/"Daily Output";receipts=root/"data/careerops-engine/daily_output"
    if directory.is_symlink() or receipts.is_symlink():raise ValueError("Output directory redirected")
    directory.mkdir(exist_ok=True);receipts.mkdir(parents=True,exist_ok=True)
    if directory.resolve()!=directory or receipts.resolve()!=receipts:raise ValueError("Output directory redirected")
    # No source-output hardlinks: editing a Daily Output Word copy must never
    # modify its canonical run artifact or invalidate its audit hashes.
    token=hashlib.sha256(rid.encode()).hexdigest()[:14]
    label=re.sub(r"[^A-Za-z0-9._-]+","_",rid).strip("._-")[-72:]
    date=datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    flag="__UNRELEASED" if override else ""
    rows={};created=[]
    with (receipts/"publication.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        # Existing user content is never silently deleted or overwritten.
        unexpected=[p.name for p in directory.iterdir() if not p.is_file() or p.suffix.lower() not in {".pdf",".docx"}]
        if unexpected:raise ValueError("DAILY_OUTPUT_HAS_NON_DOCUMENT_CONTENT: "+", ".join(unexpected))
        quartet=hashlib.sha256(json.dumps({k:v["sha256"] for k,v in delivered["files"].items()},sort_keys=True).encode()).hexdigest()[:16]
        receipt_path=receipts/(token+"_"+quartet+".json")
        if receipt_path.is_file():
            prior=json.loads(receipt_path.read_text())
            if prior.get("parent_run_id")==rid and set(prior.get("files",{}))==set(KEYS):
                valid=True
                for key,row in prior["files"].items():
                    path=Path(row.get("daily_output_path", ""))
                    if path.parent!=directory or path.is_symlink() or not path.is_file() or digest(path)!=delivered["files"][key]["sha256"] or row.get("sha256")!=delivered["files"][key]["sha256"]:
                        valid=False;break
                    if digest(delivered["files"][key]["linux_path"])!=row["sha256"]:valid=False;break
                if valid:return {**prior,"receipt_path":str(receipt_path),"already_present":True}
        with tempfile.TemporaryDirectory(prefix="publish_",dir=receipts) as temporary:
            staged={}
            for key in KEYS:
                source=Path(delivered["files"][key]["linux_path"]).resolve();expected_hash=delivered["files"][key]["sha256"]
                if not source.is_file() or digest(source)!=expected_hash:raise ValueError("Source artifact changed before copy: "+key)
                # File/package and parent/child authentication belong to the
                # official delivery builder; this verifies the bound bytes again.
                if not source.is_relative_to(root/"data/careerops-engine/runs"):raise ValueError("Source outside canonical runs")
                ext=".pdf" if key.endswith("pdf") else ".docx"
                name=f"{date}__{label}__{token}{flag}__{key}__{expected_hash[:12]}{ext}"
                destination=directory/name
                if destination.is_symlink():raise ValueError("Daily document redirected")
                if destination.exists() and digest(destination)!=expected_hash:raise ValueError("Existing daily document has different bytes")
                path=Path(temporary)/name;shutil.copyfile(source,path)
                if digest(path)!=expected_hash or digest(source)!=expected_hash:raise ValueError("Document copy hash mismatch")
                staged[key]=(path,destination)
                rows[key]={"artifact_path":str(source),"daily_output_path":str(destination),"sha256":expected_hash,
                           "disposition":expected,"independent_copy":True,"original_parent_run_id":rid}
            try:
                for key,(path,destination) in staged.items():
                    if not destination.exists():os.replace(path,destination);created.append(destination)
                    if digest(destination)!=rows[key]["sha256"]:raise ValueError("Published document changed")
            except Exception:
                # Remove only newly created, exact copies from this failed
                # transaction; pre-existing documents are preserved.
                for destination in created:
                    if destination.is_file() and not destination.is_symlink() and digest(destination) in {x["sha256"] for x in rows.values()}:destination.unlink()
                raise
        receipt={"schema_version":"careerops-daily-output-v1","status":"COPIED","parent_run_id":rid,
                 "directory":str(directory),"files":rows,"disposition":expected,"authority":"DELIVERY_ONLY",
                 "may_release":False,"model_calls":0,"writer_calls":0,"rendering_calls":0}
        quartet=hashlib.sha256(json.dumps({k:v["sha256"] for k,v in rows.items()},sort_keys=True).encode()).hexdigest()[:16]
        receipt_path=receipts/(token+"_"+quartet+".json")
        temporary_receipt=receipt_path.with_suffix(".tmp")
        temporary_receipt.write_text(json.dumps(receipt,indent=2)+"\n");os.replace(temporary_receipt,receipt_path)
    return {**receipt,"receipt_path":str(receipt_path)}
