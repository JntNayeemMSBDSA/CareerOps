"""Linux public-only regression harness: private home directories and network are absent."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--node",default=shutil.which("node"));args=parser.parse_args()
    if not args.node:raise SystemExit("Node 22+ is required; supply --node /path/to/node")
    node=Path(args.node).resolve();local=ROOT/".local-checks";local.mkdir(exist_ok=True)
    binds=["bwrap","--die-with-parent","--unshare-net"]
    for name in ["/usr","/lib","/lib64","/etc","/var","/run"]:
        if Path(name).exists():binds += ["--ro-bind",name,name]
    binds += ["--symlink","usr/bin","/bin","--ro-bind",str(node.parent.parent),"/opt/node","--bind",str(ROOT),"/work","--tmpfs","/tmp","--proc","/proc","--dev","/dev","--chdir","/work","--clearenv"]
    env={"PATH":"/opt/node/bin:/usr/bin:/bin","HOME":"/tmp","PYTHONDONTWRITEBYTECODE":"1","CAREEROPS_SOURCE_DIR":"examples/source","CAREEROPS_SEMANTIC_CHALLENGER":"0","CAREEROPS_SHARED_SOL_SEMANTIC":"0","CAREEROPS_LI_ADVISORY":"0"}
    for key,value in env.items():binds += ["--setenv",key,value]
    binds += ["--"]
    python="/work/.venv/bin/python";run_id="example_isolated_"+__import__('uuid').uuid4().hex[:12]
    commands=[("isolation",[python,"-B","-c","from pathlib import Path; assert not Path('/home').exists(); print('Private home directories are inaccessible')"]),("unit-tests",[python,"-B","-m","unittest","discover","-s","tests","-p","test_*.py","-v"]),("cli-self-test",[python,"-B","scripts/careerops_career_ops.py","self-test"]),("orchestrator-self-test",[python,"-B","scripts/careerops_production_orchestrator.py","--self-test"]),("fictional-jd-pipeline",[python,"-B","scripts/careerops_career_ops.py","single","--jd-file","examples/jobs/data-analyst.txt","--company","Glasswing Civic Archive","--position","Data Analyst","--run-id",run_id,"--stop-after","pair_packet","--no-prompt"]),("node-tests",["/opt/node/bin/node","--test","tests/rendering.test.mjs"]),("synthetic-rendering",[python,"-B","tests/render_smoke.py"])]
    results=[]
    for name,command in commands:
        result=subprocess.run(binds+command,text=True,capture_output=True,timeout=180)
        (local/(name+".log")).write_text(result.stdout+"\n"+result.stderr)
        results.append({"name":name,"return_code":result.returncode})
        print(name,"PASS" if result.returncode==0 else "FAIL")
        if result.returncode:print((result.stdout+result.stderr)[-5000:])
    manifest=json.loads((ROOT/"data/careerops-engine/runs"/run_id/"manifest.json").read_text())
    execution=manifest["execution"]
    assert execution.get("model_calls",0)==0 and execution.get("writer_calls",0)==0
    assert manifest["stages"]["pair_packet"]["status"]=="PASS"
    report={"checks":results,"network":"disabled","private_home":"not mounted","fixture_run":run_id,"model_calls":0,"writer_calls":0,"pass":all(x["return_code"]==0 for x in results)}
    (local/"isolated-results.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["pass"] else 1
if __name__=="__main__":raise SystemExit(main())
