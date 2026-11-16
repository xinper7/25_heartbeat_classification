"""Local snapshot and non-destructive restore into a new directory. Contains private data."""
import argparse, hashlib, json, os, sqlite3, sys, zipfile
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

def backup():
 from app.config import get_settings
 from app.db import engine, Base
 from app import models
 from sqlalchemy import inspect,text
 cfg=get_settings(); target=ROOT/'runtime/backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
 target.mkdir(parents=True)
 with engine.connect() as conn:
  data={table.name:[dict(r) for r in conn.execute(table.select()).mappings()] for table in Base.metadata.sorted_tables}
  revision=conn.scalar(text('SELECT version_num FROM alembic_version')) if inspect(conn).has_table('alembic_version') else None
 payload=json.dumps(data,ensure_ascii=False,default=lambda x:x.isoformat() if isinstance(x,(date,datetime)) else x).encode('utf-8')
 files={'schema.json':json.dumps({'alembic_revision':revision}).encode(),'database.json':payload,'environment.env':(ROOT/'.env').read_bytes()}
 for folder in [cfg.storage_dir/'uploads']:
  if folder.exists():
   for p in folder.rglob('*'):
    if p.is_file():files['uploads/'+p.relative_to(folder).as_posix()]=p.read_bytes()
 sessions=cfg.storage_dir/'agent_sessions.sqlite3'
 if sessions.exists():
  snapshot=target/'agent_sessions.sqlite3'
  with closing(sqlite3.connect(sessions)) as src, closing(sqlite3.connect(snapshot)) as dst:src.backup(dst)
  files['agent_sessions.sqlite3']=snapshot.read_bytes();snapshot.unlink()
 manifest={name:hashlib.sha256(blob).hexdigest() for name,blob in files.items()}
 archive=target/'project-backup.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for name,blob in files.items():z.writestr(name,blob)
  z.writestr('manifest.json',json.dumps(manifest,indent=2))
 summary=dict(archive=str(archive),counts={k:len(v) for k,v in data.items()},sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
 (target/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False))

def restore(archive,destination):
 from sqlalchemy import create_engine, DateTime, Date, text
 from app.db import Base
 from app import models
 dest=Path(destination).resolve()
 if dest.exists():raise RuntimeError('Restore destination must not exist; live data is never overwritten')
 with zipfile.ZipFile(archive) as z:
  manifest=json.loads(z.read('manifest.json'))
  for name,digest in manifest.items():
   path=(dest/name).resolve()
   if not path.is_relative_to(dest):raise RuntimeError('Unsafe archive path')
   if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise RuntimeError('Backup checksum mismatch')
  dest.mkdir(parents=True)
  for name in manifest:
   path=dest/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
 data=json.loads((dest/'database.json').read_text(encoding='utf-8'))
 engine=create_engine('sqlite:///'+(dest/'restored.db').as_posix());Base.metadata.create_all(engine)
 with engine.begin() as conn:
  for table in Base.metadata.sorted_tables:
   rows=data.get(table.name,[])
   for row in rows:
    for col in table.columns:
     if row.get(col.name) and isinstance(col.type,DateTime):row[col.name]=datetime.fromisoformat(row[col.name])
     elif row.get(col.name) and isinstance(col.type,Date):row[col.name]=date.fromisoformat(row[col.name])
   if rows:conn.execute(table.insert(),rows)
  schema_file=dest/'schema.json'
  revision=json.loads(schema_file.read_text()).get('alembic_revision') if schema_file.exists() else None
  if revision:
   conn.execute(text('CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
   conn.execute(text('INSERT INTO alembic_version VALUES (:version)'),{'version':revision})
 print(json.dumps(dict(restored=str(dest),counts={k:len(v) for k,v in data.items()})))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','restore']);p.add_argument('--archive');p.add_argument('--destination');a=p.parse_args()
 if a.action=='backup':backup()
 elif not a.archive or not a.destination:p.error('restore needs --archive and --destination')
 else:restore(a.archive,a.destination)
