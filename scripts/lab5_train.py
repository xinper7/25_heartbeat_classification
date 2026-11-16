"""Reproducible local LoRA routing experiment; synthetic task instructions, no patient data."""
import json, random, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model

SYSTEM = '选择心电工作空间工具，只输出字母。A=分析数字信号波形；B=分析报告图片；C=读取已有检查结果；D=上传格式使用帮助；E=查询模型版本状态。'
PHRASES = [
 ['分析数字心电信号','运行波形分类','帮我分析12导联','开始信号推理','对这条波形运行模型','处理数字信号','执行心电信号分析','识别这份ECG信号','计算波形五类预测','启动数字检查分析'],
 ['分析报告图片','识别心电图照片','运行图片分类','对这张报告图推理','分析PNG心电报告','处理JPEG报告图','开始图像模型分析','判断报告图五类标签','执行图片检查分析','识别标准心电报告图'],
 ['读取检查结果','查看已有预测','解释这次分析结果','查询检查结论','显示五类预测分数','看看已完成的分析','总结模型输出','查看复核信息','这条记录结果是什么','读一下最新分析'],
 ['怎么上传文件','支持哪些文件格式','采样率要求是什么','CSV应该怎么准备','需要几个导联','图片布局有什么要求','给我上传说明','hea和dat怎么选择','波形处理状态怎么选','单位应该怎么设置'],
 ['当前用什么模型','模型版本是什么','显示模型状态','信号模型叫什么','图像模型架构是什么','查询推理模型信息','看看模型配置','分类阈值在哪里','模型输入维度是什么','已加载哪些模型']]
TEST = [('请对已选择记录做数字信号分类','A'),('运行这份12导联波形的推理','A'),('请识别选中的心电报告照片','B'),('用图像模型处理这张报告','B'),('这份检查已经分析好了，帮我看预测','C'),('请读取这条检查的五类结果','C'),('我要准备上传，数据格式有何限制','D'),('心电文件要如何提交','D'),('请告诉我部署模型的版本信息','E'),('两个推理模型的配置分别是什么','E')]

def prompt(tok, text):
 return tok.apply_chat_template([{'role':'system','content':SYSTEM},{'role':'user','content':text}],tokenize=False,add_generation_prompt=True)

if __name__ == '__main__':
 torch.set_num_threads(4); torch.manual_seed(42); random.seed(42)
 out=ROOT/'runtime/agent'; out.mkdir(parents=True,exist_ok=True)
 data=[{'instruction':SYSTEM,'input':x+suffix,'output':chr(65+i),'source':'课程心电工具路由人工模板扩展，非实验1原始文本'} for i,xs in enumerate(PHRASES) for x in xs for suffix in ['','，谢谢']]
 random.shuffle(data)
 (out/'agent_finetune_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'eval_data.json').write_text(json.dumps(TEST,ensure_ascii=False,indent=2),encoding='utf-8')
 tok=AutoTokenizer.from_pretrained(out/'base',local_files_only=True)
 model=AutoModelForCausalLM.from_pretrained(out/'base',local_files_only=True,torch_dtype=torch.float32)
 ids=[tok.encode(x,add_special_tokens=False)[0] for x in 'ABCDE']
 def evaluate():
  model.eval(); rows=[]
  with torch.no_grad():
   for text,expected in TEST:
    t=time.perf_counter(); batch=tok(prompt(tok,text),return_tensors='pt'); logits=model(**batch).logits[0,-1,ids]; predicted='ABCDE'[logits.argmax().item()]
    rows.append(dict(query=text,expected=expected,predicted=predicted,ms=round((time.perf_counter()-t)*1000,2)))
  return dict(accuracy=sum(r['expected']==r['predicted'] for r in rows)/len(rows),rows=rows)
 baseline=evaluate(); print('baseline',baseline['accuracy'],flush=True)
 model=get_peft_model(model,LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,target_modules=['q_proj','v_proj'],layers_to_transform=[22,23],task_type='CAUSAL_LM'))
 trainable=sum(p.numel() for p in model.parameters() if p.requires_grad); total=sum(p.numel() for p in model.parameters())
 optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=5e-4)
 started=time.perf_counter(); losses=[]; model.train(); optimizer.zero_grad()
 for epoch in range(8):
  for index,row in enumerate(data):
   prefix=prompt(tok,row['input']); x=tok(prefix+row['output'],return_tensors='pt'); labels=x['input_ids'].clone(); labels[:,:-1]=-100
   loss=model(**x,labels=labels).loss; (loss/8).backward(); losses.append(float(loss.detach()))
   if (index+1)%8==0 or index+1==len(data): optimizer.step(); optimizer.zero_grad()
   if (index+1)%20==0: print('epoch',epoch+1,'sample',index+1,'loss',round(losses[-1],4),flush=True)
 model.save_pretrained(out/'adapter'); tok.save_pretrained(out/'adapter')
 result=dict(base='Qwen/Qwen2.5-0.5B-Instruct',seed=42,train_samples=len(data),test_samples=len(TEST),epochs=8,rank=8,alpha=16,gradient_accumulation=8,learning_rate=5e-4,layers=[22,23],dtype='float32',device='cpu',trainable=trainable,total=total,training_seconds=round(time.perf_counter()-started,2),losses=losses,baseline=baseline,finetuned=evaluate())
 (out/'training_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print('finetuned',result['finetuned']['accuracy'],flush=True)
