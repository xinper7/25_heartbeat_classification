import csv,io
from test_workflow import create_patient,create_study

def test_export_uses_same_filters_and_permissions(client,headers):
 a=headers('analyst');other=headers('other')
 p=create_patient(client,a,'filter-export');sid=create_study(client,a,p,'signal')
 create_study(client,a,p,'image')
 p2=create_patient(client,other,'private-export');create_study(client,other,p2)
 params={'patient_id':p,'kind':'signal','status':'awaiting_upload'}
 listed=client.get('/api/v1/studies',headers=a,params=params).json()['result']
 result=client.get('/api/v1/exports/studies.csv',headers=a,params=params)
 assert result.status_code==200
 rows=list(csv.reader(io.StringIO(result.content.decode('utf-8-sig'))))
 assert listed['total']==1 and len(rows)==2
 assert client.get('/api/v1/exports/studies.csv',headers=other,params=params).status_code==404
 assert client.get('/api/v1/studies',headers=a,params={'q':f'ECG-{sid:05d}'}).json()['result']['total']==1
 assert len(list(csv.reader(io.StringIO(client.get('/api/v1/exports/studies.csv',headers=a,params={'q':'no-such-record'}).content.decode('utf-8-sig')))))==1
