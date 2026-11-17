"""Frozen new holdout: base versus deployed LoRA. Never trains or activates a model."""
import json,time,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.agent_lab import SYSTEM,adapter_paths
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from peft import PeftModel
GROUPS=[
['给这一段数字采样计算类别输出','将选定的十二路电压序列送入分类器','请启动当前dat记录的信号预测','对本条多导联时序数据做一次推断','我要给这段ECG数值运行分类'],
['把这幅纸质心电扫描件交给图像网络','请分类当前的报告截图','启动选定心电照片的识别任务','为这张标准排版心电图片计算标签','我要对这幅报告影像做模型推断'],
['不要重算，展示上次存下的预测分数','把已完成记录的分类输出调出来','我只想查当前检查已经保存的标签','此前那次推断的结果能列出来吗','打开这份记录现有的分析结论'],
['提交表格之前导联标题应如何命名','请解释上传时两个配对文件的作用','输入心电文件的长度和频率有什么限制','上传报告扫描件时需要哪种版式','怎样填写CSV幅值的计量单位'],
['目前服务器上的分类网络版本号是多少','请列出两种已部署分类器的输入规格','我想了解本项目预测模型的结构名称','发布的分类器使用了哪些判定阈值','显示现有推理模型的版本清单']]
rows=[dict(query=q,expected=chr(65+i)) for i,g in enumerate(GROUPS) for q in g]
folder=ROOT/'runtime/agent';out=ROOT/'runtime/qa/agent-holdout';out.mkdir(parents=True,exist_ok=True)
prior=set()
for p in folder.rglob('*.json'):
 if p.name not in ('agent_finetune_data.json','eval_data.json'):continue
 data=json.loads(p.read_text(encoding='utf-8'))
 for r in data:prior.add(r.get('input','') if isinstance(r,dict) else r[0])
assert not any(r['query'] in prior for r in rows)
blob=json.dumps(rows,ensure_ascii=False,indent=2);(out/'frozen_test.json').write_text(blob,encoding='utf-8')
torch.set_num_threads(4);tok=AutoTokenizer.from_pretrained(folder/'base',local_files_only=True)
model=AutoModelForCausalLM.from_pretrained(folder/'base',local_files_only=True,dtype=torch.float32).eval()
ids=[tok.encode(c,add_special_tokens=False)[0] for c in 'ABCDE'];result={}
def evaluate():
 output=[]
 with torch.no_grad():
  for r in rows:
   prompt=tok.apply_chat_template([{'role':'system','content':SYSTEM},{'role':'user','content':r['query']}],tokenize=False,add_generation_prompt=True)
   start=time.perf_counter();pred='ABCDE'[model(**tok(prompt,return_tensors='pt')).logits[0,-1,ids].argmax().item()]
   output.append(r|dict(predicted=pred,ms=round((time.perf_counter()-start)*1000,2)))
 return dict(accuracy=sum(r['expected']==r['predicted'] for r in output)/len(output),rows=output)
result['base']=evaluate();model=PeftModel.from_pretrained(model,adapter_paths()[0]).eval();result['lora']=evaluate()
result['test_sha256']=hashlib.sha256(blob.encode()).hexdigest();result['samples']=len(rows);result['exact_overlap']=0
result['limitations']='人工新增小样本留出集；仅检查完全重复，未证明语义独立；不得据此调参再声称盲测。'
(out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v if not isinstance(v,dict) else {'accuracy':v['accuracy']} for k,v in result.items()},ensure_ascii=False))
