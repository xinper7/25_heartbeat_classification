"""Backfill public-sample provenance only when recorded file hashes match packaged samples."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.db import SessionLocal
from app.models import Asset,Study
from app.samples import source_info
from sqlalchemy import select
from app.samples import packaged_hashes
groups=packaged_hashes()
changed=0
with SessionLocal() as db:
 for study in db.scalars(select(Study)):
  hashes=tuple(sorted(db.scalars(select(Asset.sha256).where(Asset.study_id==study.id))))
  if hashes in groups and study.metadata_json.get('source',{}).get('purpose')!='public_sample':
   study.metadata_json=study.metadata_json|{'source':source_info(groups[hashes])};changed+=1
 db.commit()
print(json.dumps({'hash_verified_sample_records':changed}))
