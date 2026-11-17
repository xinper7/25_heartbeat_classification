import importlib.util,json,hashlib,io
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('ensure_agent',Path(__file__).resolve().parents[2]/'scripts/ensure_agent.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def install(folder):
 for name in ['base/config.json','base/model.safetensors','adapter/adapter_config.json','adapter/adapter_model.safetensors']:
  path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'weights')
def test_ready_skips_network(tmp_path,monkeypatch):
 monkeypatch.setattr(module,'ROOT',tmp_path);install(tmp_path/'runtime/agent')
 monkeypatch.setattr(module.urllib.request,'urlopen',lambda *a,**k:pytest.fail('unexpected download'))
 module.main()
def test_partial_directory_not_overwritten(tmp_path,monkeypatch):
 monkeypatch.setattr(module,'ROOT',tmp_path);(tmp_path/'runtime/agent').mkdir(parents=True)
 with pytest.raises(RuntimeError,match='refusing overwrite'):module.main()
def test_download_verified_before_import(tmp_path,monkeypatch):
 monkeypatch.setattr(module,'ROOT',tmp_path);monkeypatch.delenv('GITHUB_TOKEN',raising=False)
 data=b'fake archive';config=tmp_path/'artifacts/agent';config.mkdir(parents=True)
 (config/'release.json').write_text(json.dumps(dict(repository='owner/repo',tag='test',asset='model.zip',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())))
 def response(req,**kwargs):
  return io.BytesIO(json.dumps({'assets':[{'name':'model.zip','browser_download_url':'https://example.test/model'}]}).encode() if '/releases/' in req.full_url else data)
 monkeypatch.setattr(module.urllib.request,'urlopen',response)
 calls=[]
 def imported(*a,**k):calls.append(a);install(tmp_path/'runtime/agent')
 monkeypatch.setattr(module.subprocess,'run',imported);module.main();assert len(calls)==1
 assert (tmp_path/'runtime/downloads/model.zip').read_bytes()==data
