"""Verify and install handover models into an absent runtime/agent directory."""
import argparse,hashlib,json,zipfile,shutil,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('archive');args=p.parse_args();target=ROOT/'runtime/agent'
if target.exists():raise RuntimeError('runtime/agent already exists; back it up and move it aside first')
staging=ROOT/'runtime'/('agent-import-'+uuid.uuid4().hex)
with zipfile.ZipFile(args.archive) as z:
 manifest=json.loads(z.read('SHA256.json'))
 for name,digest in manifest.items():
  path=(staging/name).resolve()
  if not path.is_relative_to(staging.resolve()):raise RuntimeError('Invalid archive path')
  if hashlib.sha256(z.read('agent/'+name)).hexdigest()!=digest:raise RuntimeError('Checksum mismatch: '+name)
 for name in manifest:
  path=staging/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read('agent/'+name))
if not (staging/'base/model.safetensors').exists():raise RuntimeError('Base weights missing')
staging.rename(target)
print('Verified model bundle installed; restart the API before using automatic routing.')
