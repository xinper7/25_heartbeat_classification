"""Same-set comparison, retaining both old and new experimental evidence."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];folder=ROOT/'runtime/agent'
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from peft import PeftModel
sys.path.insert(0,str(ROOT/'scripts'))
from lab5_train import SYSTEM
torch.set_num_threads(4)
tok=AutoTokenizer.from_pretrained(folder/'base',local_files_only=True)
base=AutoModelForCausalLM.from_pretrained(folder/'base',local_files_only=True,torch_dtype=torch.float32)
model=PeftModel.from_pretrained(base,folder/'adapter',adapter_name='v1').eval()
model.load_adapter(folder/'v2/adapter',adapter_name='v2')
rows=json.loads((folder/'v2/eval_data.json').read_text(encoding='utf-8'))
ids=[tok.encode(x,add_special_tokens=False)[0] for x in 'ABCDE']
result={}
for adapter in ['v1','v2']:
 model.set_adapter(adapter);model.eval();output=[]
 with torch.no_grad():
  for query,expected in rows:
   prompt=tok.apply_chat_template([{'role':'system','content':SYSTEM},{'role':'user','content':query}],tokenize=False,add_generation_prompt=True)
   t=time.perf_counter();batch=tok(prompt,return_tensors='pt');predicted='ABCDE'[model(**batch).logits[0,-1,ids].argmax().item()]
   output.append(dict(query=query,expected=expected,predicted=predicted,ms=round((time.perf_counter()-t)*1000,2)))
 result[adapter]=dict(samples=len(output),accuracy=sum(x['expected']==x['predicted'] for x in output)/len(output),original10_accuracy=sum(x['expected']==x['predicted'] for x in output[:10])/10,rows=output)
(folder/'router_comparison_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
if result['v2']['accuracy']>result['v1']['accuracy'] and result['v2']['original10_accuracy']>=result['v1']['original10_accuracy']:
 (folder/'active_adapter.json').write_text(json.dumps(dict(directory='v2/adapter',metrics='v2/training_metrics.json')),encoding='utf-8');result['activated']='v2'
else:result['activated']='v1'
print(json.dumps({k:({a:b for a,b in v.items() if a!='rows'} if isinstance(v,dict) else v) for k,v in result.items()}))
