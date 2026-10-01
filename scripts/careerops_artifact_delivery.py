"""Deliver exact current-run files for review; has no release authority."""
from pathlib import Path
import subprocess,shutil,os,hashlib,base64,json,argparse,re,zipfile
ROOT=Path(__file__).resolve().parents[1]
KEYS=('resume_pdf','resume_docx','cover_pdf','cover_docx')
def canonical_windows_path(value):
    text=str(value).strip()
    unc=text.startswith('\\\\')
    text=re.sub(r'\\+',lambda match:'\\',text)
    return ('\\'+text) if unc else text

def windows_api_path(value):
    target=canonical_windows_path(value)
    if target.startswith('\\\\?\\'):return target
    return ('\\\\?\\UNC\\'+target[2:]) if target.startswith('\\\\') else ('\\\\?\\'+target)

def windows_path(path):
    path=Path(path).resolve()
    if os.name=='nt':return canonical_windows_path(path)
    converter=shutil.which('wslpath')
    if converter:
        try:
            p=subprocess.run([converter,'-w',str(path)],capture_output=True,text=True,timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if p.returncode==0 and p.stdout.strip():return canonical_windows_path(p.stdout)
    return None

def build_delivery(run,manifest,outcome,override=None):
    run=Path(run).resolve();root=run.parents[3];files={};issues=[]
    rows={}
    if outcome.get('status')=='USER_OVERRIDE_GENERATED':rows=(override or {}).get('outputs',{})
    else:
        for kind in ['resume','cover']:
            artifacts=manifest.get('stages',{}).get(kind+'_render',{}).get('artifacts',{})
            for ext in ['pdf','docx']:rows[kind+'_'+ext]=artifacts.get(ext,{})
    allowed_output = run/'output'
    if outcome.get('status')=='USER_OVERRIDE_GENERATED' and (override or {}).get('generation_run_id'):
        child=run.parent/(override['generation_run_id'])
        if (child/'manifest.json').is_file() and (override or {}).get('automatic_manifest_sha256')==hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest() and json.loads((child/'manifest.json').read_text()).get('automatic_parent_run')==run.name:
            allowed_output=child/'output'
    for key in KEYS:
        row=rows.get(key,{})
        if not row.get('path'):continue
        p=Path(row['path']);p=(p if p.is_absolute() else root/p).resolve()
        if not p.is_relative_to(allowed_output) or not p.is_file():issues.append(key+': missing or cross-run file');continue
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=row.get('sha256'):issues.append(key+': artifact hash mismatch');continue
        if key.endswith('_pdf') and not p.read_bytes().startswith(b'%PDF-'):
            issues.append(key+': invalid PDF signature');continue
        if key.endswith('_docx'):
            try:
                with zipfile.ZipFile(p) as z:
                    if not {'[Content_Types].xml','word/document.xml'}.issubset(z.namelist()) or z.testzip():
                        raise ValueError('Invalid Word package')
            except (OSError,ValueError,zipfile.BadZipFile):
                issues.append(key+': invalid DOCX package');continue
        files[key]={'linux_path' :str(p),'windows_path':windows_path(p),'sha256':digest,'size_bytes':p.stat().st_size}
    folders=sorted({str(Path(row['linux_path']).parent) for row in files.values()})
    folder=folders[0] if len(folders)==1 else None
    return {'schema_version':'careerops-artifact-delivery-v1','status':'AVAILABLE' if len(files)==4 and not issues else 'INCOMPLETE' if files or issues else 'NOT_GENERATED','disposition':'RELEASED' if outcome.get('release_ready') else 'USER_OVERRIDE_UNRELEASED' if outcome.get('override_generated') else 'UNRELEASED','authority':'DELIVERY_ONLY','may_release':False,'canonical_storage':'Linux/WSL','files':files,'folder':{'linux_path':folder,'windows_path':windows_path(folder) if folder else None},'open_actions':{'command_owner':str(ROOT/'scripts/careerops_artifact_delivery.py'),'run_id':run.name,'open_folder_flag':'--open-folder','open_file_flag':'--open-file <artifact_key>','automatic_open':False},'issues':issues,'model_calls':0}

# Windows shell APIs and filesystem APIs use different path representations.
# Files use the default association; directories use explicit Explorer navigation.
_SHELL_HELPER = r"""
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class CareerOpsShell {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool DefineDosDevice(uint flags,string name,string target);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern uint QueryDosDevice(string name,StringBuilder target,int size);
 // Keep aliases usable by asynchronous readers/Explorer. Preserve occupied
 // drive letters; reuse only an exact mapping. Normal WSL files use hard links.
 public static string FileAlias(string path) {
  using(var mutex=new System.Threading.Mutex(false,@"Local\CareerOpsFilesystemAliases")) {
   bool held=false;
   try {
    try {held=mutex.WaitOne(10000);}catch(System.Threading.AbandonedMutexException){held=true;}
    if(!held)throw new InvalidOperationException("FILESYSTEM_ALIAS_BUSY");
    string parent=System.IO.Path.GetDirectoryName(path),leaf=System.IO.Path.GetFileName(path);
    string target=parent.StartsWith(@"\\")?@"\??\UNC\"+parent.Substring(2):@"\??\"+parent;
    for(char letter='Z';letter>='D';letter--) {
     string drive=letter+":";StringBuilder found=new StringBuilder(32768);
     uint size=QueryDosDevice(drive,found,found.Capacity);
     if(size!=0) {if(String.Equals(found.ToString(),target,StringComparison.OrdinalIgnoreCase))return drive+@"\"+leaf;continue;}
     if(Marshal.GetLastWin32Error()!=2)continue;
     if(DefineDosDevice(1,drive,target))return drive+@"\"+leaf;
    }
    throw new InvalidOperationException("NO_FREE_FILESYSTEM_ALIAS; existing mappings preserved");
   }finally{if(held)mutex.ReleaseMutex();}
  }
 }
}
"""


def local_windows_path(value):
    target=canonical_windows_path(value)
    if target.lower().startswith('\\\\?\\unc\\'):target='\\\\'+target[8:]
    elif target.startswith('\\\\?\\'):target=target[4:]
    drive=bool(re.match(r'^[A-Za-z]:\\',target))
    unc=bool(re.match(r'^\\\\[^\\:]+\\[^\\:]+(?:\\|$)',target))
    if not (drive or unc) or target.startswith('\\\\.\\') or any(c in target for c in ('\x00','\r','\n')):
        return None
    tail=target[3:] if drive else target[2:]
    if ':' in tail or any(part in ('.','..') for part in tail.split('\\')):return None
    return target


def short_artifact_alias(source,expected_sha256):
    """A hard link is the same file/inode, not a generated copy or a symlink.
    Original ownership/package/hash checks remain in build_delivery. Revalidate
    identity here and again in Windows before invoking the default association.
    """
    source=Path(source).resolve()
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected_sha256:raise ValueError('ARTIFACT_HASH_CHANGED_BEFORE_OPEN')
    directory=ROOT/'output/windows-open'
    directory.mkdir(parents=True,exist_ok=True)
    if directory.resolve()!=directory:raise ValueError('DELIVERY_ALIAS_DIRECTORY_REDIRECTED')
    token=hashlib.sha256((str(source)+'\0'+expected_sha256).encode()).hexdigest()
    stem=re.sub(r'[^\w .-]','_',source.stem)[:32]
    alias=directory/(stem+'_'+token+source.suffix.lower())
    try:os.link(source,alias)
    except FileExistsError:pass
    if alias.is_symlink() or not alias.is_file() or not source.samefile(alias):raise ValueError('DELIVERY_ALIAS_IDENTITY_MISMATCH')
    # wslpath resolves a final symlink; constructing from the directory keeps
    # the intended short name explicit, even if conversion changes in future.
    parent=windows_path(directory)
    if not parent:raise ValueError('WINDOWS_ALIAS_PATH_UNAVAILABLE')
    target=canonical_windows_path(parent+'\\'+alias.name)
    if len(target)>=260:raise ValueError('WINDOWS_ALIAS_ROOT_TOO_LONG')
    return target,{'linux_path':str(alias),'same_file':True,'sha256':expected_sha256,'kind':'IDENTICAL_FILE_HARD_LINK'}


def open_windows(target,*,linux_path=None,expected_sha256=None):
    base={'owner':'DELIVERY_OS_ASSOCIATION','rendering_defect':False,'rerender':False,'model_calls':0,'writer_calls':0}
    if not target:return {**base,'status':'WINDOWS_PATH_UNAVAILABLE','owner':'DELIVERY_PATH_CONVERSION'}
    target=local_windows_path(target)
    if not target:return {**base,'status':'NOT_A_LOCAL_ARTIFACT','owner':'DELIVERY_PATH_VALIDATION'}
    ps=shutil.which('powershell.exe')
    if not ps:return {**base,'status':'WINDOWS_OPEN_UNAVAILABLE','owner':'DELIVERY_OS_INTEGRATION'}
    forwarded=target;alias=None
    if linux_path and len(target)>=260:
        try:
            if canonical_windows_path(windows_path(linux_path))!=target:raise ValueError('ARTIFACT_PATH_IDENTITY_MISMATCH')
            forwarded,alias=short_artifact_alias(linux_path,expected_sha256)
        except (OSError,ValueError,TypeError) as exc:
            return {**base,'status':'DELIVERY_ALIAS_FAILED','detail':str(exc),'original_windows_path':target}
    literal=lambda s:"'"+str(s).replace("'","''")+"'"
    # Inputs are literals, not shell arguments/code. File launches have no
    # parameters; the configured association (including a PDF browser) decides.
    script="""$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
Add-Type -TypeDefinition @'
"""+_SHELL_HELPER+"\n'@\n"+"$original="+literal(target)+";$native="+literal(windows_api_path(target))+";$forwarded="+literal(forwarded)+";$expected="+literal(expected_sha256 or '')+r"""
function FileHash($path) {
 $stream=[IO.File]::OpenRead($path);$algorithm=[Security.Cryptography.SHA256]::Create()
 try {return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant()} finally {$stream.Dispose();$algorithm.Dispose()}
}
try {
 $directory=[IO.Directory]::Exists($native);$file=[IO.File]::Exists($native)
 if (-not ($directory -or $file)) {throw 'ARTIFACT_NO_LONGER_EXISTS'}
 $hash=$null;$mode=$null
 if($directory) {
  if($forwarded.Length -ge 260){$forwarded=[CareerOpsShell]::FileAlias($original)}
  if(-not [IO.Directory]::Exists($forwarded)){throw 'FORWARDED_FOLDER_UNAVAILABLE'}
  $mode='EXPLORER_FOLDER'
  $folderStart=New-Object Diagnostics.ProcessStartInfo;$folderStart.FileName='explorer.exe';$folderStart.UseShellExecute=$false;$folderStart.Arguments=([char]34+$forwarded+[char]34)
  $process=[Diagnostics.Process]::Start($folderStart);if($process){$process.Dispose()}
 } else {
  $hash=FileHash $native;if($expected -and $hash -ne $expected){throw 'ARTIFACT_HASH_CHANGED_BEFORE_OPEN'}
  if($forwarded.Length -ge 260){$forwarded=[CareerOpsShell]::FileAlias($original)}
  if($forwarded.Length -ge 260){throw 'FILESYSTEM_ALIAS_TOO_LONG'}
  $forwardHash=FileHash $forwarded;if($forwardHash -ne $hash){throw 'FORWARDED_FILE_HASH_MISMATCH'}
  $mode='DEFAULT_FILE_ASSOCIATION'
  $start=New-Object Diagnostics.ProcessStartInfo;$start.FileName=$forwarded;$start.UseShellExecute=$true;$start.ErrorDialog=$false;$start.Arguments=''
  $process=[Diagnostics.Process]::Start($start);if($process){$process.Dispose()}
 }
 @{status='OPEN_REQUESTED';mode=$mode;original_windows_path=$original;forwarded_windows_path=$forwarded;sha256=$hash;target_verified=$true;association_handoff=$true}|ConvertTo-Json -Compress
 exit 0
} catch {
 @{status='OS_OPEN_OR_ASSOCIATION_FAILED';original_windows_path=$original;detail=$_.Exception.Message;hresult=$_.Exception.HResult;target_verified=$false;association_handoff=$false}|ConvertTo-Json -Compress
 exit 1
}
"""
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        native_env=dict(os.environ);native_env.pop('PSModulePath',None)
        p=subprocess.run([ps,'-NoProfile','-NonInteractive','-STA','-EncodedCommand',encoded],env=native_env,capture_output=True,text=True,timeout=45)
        receipt=json.loads(p.stdout.strip())
        if receipt.get('original_windows_path')!=target:raise ValueError('NATIVE_RECEIPT_TARGET_MISMATCH')
        if p.returncode==0 and (receipt.get('status')!='OPEN_REQUESTED' or not receipt.get('target_verified') or not receipt.get('association_handoff')):raise ValueError('UNVERIFIED_NATIVE_OPEN')
        if p.returncode==0 and expected_sha256 and receipt.get('sha256')!=expected_sha256:raise ValueError('NATIVE_RECEIPT_HASH_MISMATCH')
    except (OSError,subprocess.TimeoutExpired,ValueError,TypeError) as exc:
        return {**base,'status':'OS_OPEN_OR_ASSOCIATION_FAILED','detail':str(exc),'original_windows_path':target}
    return {**base,**receipt,'return_code':p.returncode,'alias':alias,'reader_display_verified':False}


def open_delivery(delivery,*,artifact_key=None):
    if artifact_key:
        row=delivery['files'].get(artifact_key,{})
        return open_windows(row.get('windows_path'),linux_path=row.get('linux_path'),expected_sha256=row.get('sha256'))
    return open_windows(delivery['folder'].get('windows_path'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);parser.add_argument('--open-folder',action='store_true');parser.add_argument('--open-file',choices=KEYS)
    args=parser.parse_args()
    from careerops_run_outcome import emit_run_outcome
    outcome=emit_run_outcome(args.run_id,root=ROOT);delivery=outcome['delivery'];print(json.dumps(delivery,indent=2))
    if args.open_folder or args.open_file:
        result=open_delivery(delivery,artifact_key=args.open_file);print(json.dumps(result,indent=2));return 0 if result['status']=='OPEN_REQUESTED' else 1
    return 0
if __name__=='__main__':raise SystemExit(main())
