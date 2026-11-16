"""Copy current SQLite project into its empty isolated MySQL8 database after backup."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from sqlalchemy import create_engine,func,select,text
from app.db import Base,engine as source
from app import models
from app.config import get_settings

if __name__=='__main__':
 if not get_settings().database_url.startswith('sqlite'):raise RuntimeError('Source must be SQLite')
 backups=sorted((ROOT/'runtime/backups').glob('*/project-backup.zip'))
 if not backups:raise RuntimeError('Create a backup first')
 info=json.loads((ROOT/'runtime/mysql-local-admin.json').read_text())
 url=f"mysql+pymysql://ecg_app:{info['app_password']}@127.0.0.1:3307/ecg_platform?charset=utf8mb4"
 target=create_engine(url)
 with target.connect() as c:
  version=c.scalar(text('SELECT VERSION()'))
  if not version.startswith('8.'):raise RuntimeError('MySQL8 required')
 Base.metadata.create_all(target)
 with source.connect() as old,target.begin() as new:
  if any(new.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables):raise RuntimeError('Destination contains data; refusing overwrite')
  counts={}
  for table in Base.metadata.sorted_tables:
   rows=[dict(r) for r in old.execute(table.select()).mappings()]
   if rows:new.execute(table.insert(),rows)
   n=new.scalar(select(func.count()).select_from(table))
   if n!=len(rows):raise RuntimeError('Count mismatch')
   counts[table.name]=n
  # Existing schema revision is preserved for future Alembic upgrades.
  revision=old.scalar(text('SELECT version_num FROM alembic_version'))
  new.execute(text('CREATE TABLE IF NOT EXISTS alembic_version(version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
  new.execute(text('INSERT INTO alembic_version VALUES (:version)'),{'version':revision})
 content=(ROOT/'.env').read_text(encoding='utf-8')
 lines=[('DATABASE_URL='+url) if x.startswith('DATABASE_URL=') else x for x in content.splitlines()]
 (ROOT/'.env').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 result=dict(version=version,counts=counts,backup=str(backups[-1]),original_sqlite_preserved=True)
 (ROOT/'runtime/mysql-migration.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result))
