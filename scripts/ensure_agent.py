"""Install pinned release models once; never overwrite an existing model directory."""
import hashlib,json,os,subprocess,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def ready(folder):
 try:
  active=json.loads((folder/'active_adapter.json').read_text()) if (folder/'active_adapter.json').exists() else {}
  adapter=(folder/active.get('directory','adapter')).resolve()
  return adapter.is_relative_to(folder.resolve()) and all((folder/'base'/f).is_file() for f in ['config.json','model.safetensors']) and all((adapter/f).is_file() for f in ['adapter_config.json','adapter_model.safetensors'])
 except (ValueError,OSError):return False
def main():
 target=ROOT/'runtime/agent'
 if ready(target):print('Agent models already installed; no download needed.');return
 if target.exists():raise RuntimeError('Incomplete runtime/agent exists. Back it up and move it aside before installing; refusing overwrite.')
 spec=json.loads((ROOT/'artifacts/agent/release.json').read_text());repo=spec['repository'];headers={'User-Agent':'Cardio-Model-Installer'}
 token=os.environ.get('GITHUB_TOKEN')
 if token:headers['Authorization']='Bearer '+token
 url=f"https://api.github.com/repos/{repo}/releases/tags/{spec['tag']}"
 def request(url,headers=headers):
  req=urllib.request.Request(url,headers={k:v for k,v in headers.items() if k!='Authorization'})
  if headers.get('Authorization'):req.add_unredirected_header('Authorization',headers['Authorization'])
  return urllib.request.urlopen(req,timeout=120)
 with request(url) as r:release=json.load(r)
 asset=next((a for a in release['assets'] if a['name']==spec['asset']),None)
 if not asset:raise RuntimeError('Published model attachment is missing')
 download=asset['url'] if token else asset['browser_download_url'];download_headers=headers|({'Accept':'application/octet-stream'} if token else {})
 folder=ROOT/'runtime/downloads';folder.mkdir(parents=True,exist_ok=True);archive=folder/spec['asset'];part=archive.with_suffix('.part')
 def valid(path):
  if not path.exists() or path.stat().st_size!=spec['bytes']:return False
  with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()==spec['sha256']
 if not valid(archive):
  print('Downloading Agent model bundle (about 1.03 GB); first install only.',flush=True)
  count=0
  with request(download,download_headers) as response,part.open('wb') as stream:
   while chunk:=response.read(4*1024*1024):stream.write(chunk);count+=len(chunk)
  if not valid(part):raise RuntimeError('Download checksum mismatch; incomplete file retained for diagnosis')
  part.replace(archive)
 subprocess.run([sys.executable,str(ROOT/'scripts/import_agent_bundle.py'),str(archive)],check=True)
 if not ready(target):raise RuntimeError('Imported model readiness check failed')
if __name__=='__main__':main()
