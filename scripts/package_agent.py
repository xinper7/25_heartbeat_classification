"""Export model-only handover bundle, excluding business data and secrets."""
import json,hashlib,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];source=ROOT/'runtime/agent';out=ROOT/'runtime/exports';out.mkdir(parents=True,exist_ok=True)
allowed=['base','adapter','v2/adapter']
files=[]
for folder in allowed:
 files.extend(p for p in (source/folder).rglob('*') if p.is_file() and '.cache' not in p.parts)
for name in ['active_adapter.json','training_metrics.json','agent_finetune_data.json','eval_data.json','router_comparison_v2.json','train.log','training-v2.log','v2/training_metrics.json','v2/agent_finetune_data.json','v2/eval_data.json']:
 p=source/name
 if p.is_file():files.append(p)
assert (source/'base/model.safetensors').is_file()
manifest={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
archive=out/'agent-handover.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as z:
 for p in files:z.write(p,'agent/'+p.relative_to(source).as_posix())
 z.writestr('SHA256.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(archive) as z:
 for name,digest in manifest.items():assert hashlib.sha256(z.read('agent/'+name)).hexdigest()==digest
print(json.dumps(dict(bundle=str(archive),files=len(files),bytes=archive.stat().st_size)))
