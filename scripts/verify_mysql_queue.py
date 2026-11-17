"""Real MySQL8 concurrent worker check in a disposable isolated schema."""
import concurrent.futures,json,os,sys,threading,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
import pymysql
info=json.loads(Path(os.environ.get('QA_MYSQL_ADMIN_FILE',str(ROOT/'runtime/mysql-local-admin.json'))).read_text())
port=int(os.environ.get('QA_MYSQL_PORT','3307'))
schema='ecg_qa_'+uuid.uuid4().hex
admin=pymysql.connect(host='127.0.0.1',port=port,user='root',password=info['root_password'],autocommit=True)
with admin.cursor() as c:c.execute('CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
os.environ['DATABASE_URL']=f"mysql+pymysql://root:{info['root_password']}@127.0.0.1:{port}/{schema}?charset=utf8mb4"
from app.db import Base,SessionLocal,engine
from app import models,worker
from app.models import User,Patient,Study,Job,JobItem,Analysis
from app.inputs import prepare_signal
from app.config import get_settings
import numpy as np
from sqlalchemy import select,text
from app.services import perform_analysis as original
(ROOT/'runtime/qa').mkdir(parents=True,exist_ok=True)
(ROOT/'runtime/qa/mysql-queue-schema.json').write_text(json.dumps({'schema':schema}))
try:
 Base.metadata.create_all(engine)
 sample=ROOT/'sample-data/9'
 arr,meta=prepare_signal({p.name:p.read_bytes() for p in sample.iterdir() if p.suffix in ('.dat','.hea')},'filtered_mv',100,'mV')
 # Dedicated input folder is retained with QA evidence; no production uploads are changed.
 key='qa-'+uuid.uuid4().hex;folder=get_settings().storage_dir/'uploads'/key;folder.mkdir(parents=True)
 np.save(folder/'input.npy',arr)
 with SessionLocal() as db:
  u=User(username='queue-verifier',name='验证',password_hash='unused',role='admin');db.add(u);db.flush()
  p=Patient(code=key,name='队列测试',owner_id=u.id);db.add(p);db.flush()
  job=Job(owner_id=u.id,name='isolated concurrency verification');db.add(job);db.flush();job_id=job.id
  for i in range(2):
   s=Study(patient_id=p.id,owner_id=u.id,title='QA',kind='signal',status='queued',metadata_json=meta|{'storage_key':key});db.add(s);db.flush();db.add(JobItem(job_id=job.id,study_id=s.id,status='queued'))
  db.commit()
 # Verify the actual SKIP LOCKED behavior while another transaction still holds a row lock.
 with SessionLocal() as first,SessionLocal() as second:
  a=first.scalar(select(JobItem).order_by(JobItem.id).with_for_update(skip_locked=True).limit(1))
  b=second.scalar(select(JobItem).order_by(JobItem.id).with_for_update(skip_locked=True).limit(1))
  assert a.id!=b.id
  first.rollback();second.rollback()
 barrier=threading.Barrier(2);claims=[];lock=threading.Lock()
 def synchronized(db,study_id,owner_id,token):
  with lock:claims.append((study_id,token))
  barrier.wait(timeout=30)
  # The application lock limits inference within this process; serialize only inference.
  with inference_lock:return original(db,study_id,owner_id,token)
 inference_lock=threading.Lock();worker.perform_analysis=synchronized
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda _:worker.run_once(),range(2)))
 with SessionLocal() as db:
  items=db.scalars(select(JobItem).order_by(JobItem.id)).all();analyses=db.scalars(select(Analysis)).all()
  assert all(results) and len({x[0] for x in claims})==2
  assert all(i.status=='succeeded' and i.attempts==1 for i in items)
  assert len(analyses)==2
  evidence=dict(mysql= db.scalar(text('SELECT VERSION()')),concurrent_workers=2,skip_locked_distinct=True,distinct_claims=len({x[0] for x in claims}),items=[dict(id=i.id,status=i.status,attempts=i.attempts) for i in items],analyses=len(analyses))
 out=ROOT/'runtime/qa/mysql-queue.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))
finally:
 engine.dispose()
 with admin.cursor() as c:c.execute('DROP DATABASE '+schema)
 admin.close()
