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
 out=ROOT/'runtime/agent/v2'; out.mkdir(parents=True,exist_ok=True)
 extra=[
 ['给当前数字检查做一次分类','对上传的CSV进行推理','开始处理这份十二导联数据','用信号模型识别当前波形','计算所选记录的数字信号标签','请给dat波形计算分类分数','对这份心电采样数据执行分析','执行当前信号模型推理','分析已上传的数字采样','用ResNet计算波形输出'],
 ['用报告图模型识别当前PNG','请给已上传的图像做分类','启动选中图片的推理任务','对这张心电截图计算分数','用EfficientNet识别心电图','分类这份JPEG心电报告','给当前报告照片生成标签','对选中的标准报告图做分析','运行已上传图片的推理','给这张扫描心电图计算输出'],
 ['展示当前已经保存的分析输出','把这份已分析检查的预测读出来','我想查看之前生成的分类结果','打开当前记录的五类分数','这次分析得到什么标签','显示已经计算好的预测结果','读取所选检查的已有模型输出','查询这份检查保存的结果','请把之前分析的分数列出来','查看当前分析的阳性阴性结果'],
 ['上传前需要怎样整理CSV','WFDB配对文件有哪些要求','图片支持什么排版','导联列名要怎么写','怎么选择波形的处理状态','心电数据需要多少采样点','上传的时间列需要什么间隔','文件大小有什么限制','上传图片需要保留节律条吗','表格必须使用哪些单位'],
 ['查询两个分类模型的版本','显示当前部署模型的名称与配置','查看服务使用的模型输入形状','报告图分类网络叫什么','当前信号推理采用哪个网络','发布清单中的阈值是多少','当前使用什么分类架构','检查两份模型的发布版本','我要查询推理引擎模型信息','看看当前模型的类别列表']]
 for group,more in zip(PHRASES,extra):group.extend(more)
 data=[{'instruction':SYSTEM,'input':x+suffix,'output':chr(65+i),'source':'课程心电工具路由人工模板扩展，非实验1原始文本'} for i,xs in enumerate(PHRASES) for x in xs for suffix in ['','，谢谢']]
 random.shuffle(data)
 (out/'agent_finetune_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'eval_data.json').write_text(json.dumps(TEST,ensure_ascii=False,indent=2),encoding='utf-8')
 TEST.extend([
 ('给这条数字波形执行五类标签计算','A'),('请用数字信号网络处理这个记录','A'),('对CSV心电采样执行分类计算','A'),('对当前十二导联运行信号模型','A'),
 ('请运行图片网络对报告进行分类','B'),('给这张心电截图做图像推理','B'),('识别报告扫描图里的分类标签','B'),('对所选PNG报告执行模型分析','B'),
 ('打开已经生成的心电分析分数','C'),('把这条检查已保存的预测列出来','C'),('查看刚才保存的分类标签','C'),('读取之前计算好的模型输出','C'),
 ('我上传的数据表列名怎么填写','D'),('输入文件应该采用怎样的采样间隔','D'),('成对的波形文件应该怎么传','D'),('报告图片需要遵守什么布局','D'),
 ('本机发布了哪两个分类模型','E'),('想看部署网络的输入尺寸和版本','E'),('告诉我分类模型使用哪些阈值','E'),('查看数字信号和图片模型的配置','E')])
 (out/'eval_data.json').write_text(json.dumps(TEST,ensure_ascii=False,indent=2),encoding='utf-8')
 tok=AutoTokenizer.from_pretrained(ROOT/'runtime/agent/base',local_files_only=True)
 model=AutoModelForCausalLM.from_pretrained(ROOT/'runtime/agent/base',local_files_only=True,torch_dtype=torch.float32)
 ids=[tok.encode(x,add_special_tokens=False)[0] for x in 'ABCDE']
 def evaluate():
  model.eval(); rows=[]
  with torch.no_grad():
   for text,expected in TEST:
    t=time.perf_counter(); batch=tok(prompt(tok,text),return_tensors='pt'); logits=model(**batch).logits[0,-1,ids]; predicted='ABCDE'[logits.argmax().item()]
    rows.append(dict(query=text,expected=expected,predicted=predicted,ms=round((time.perf_counter()-t)*1000,2)))
  return dict(accuracy=sum(r['expected']==r['predicted'] for r in rows)/len(rows),rows=rows)
 baseline=evaluate(); print('baseline',baseline['accuracy'],flush=True)
 model=get_peft_model(model,LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,target_modules=['q_proj','v_proj'],layers_to_transform=[20,21,22,23],task_type='CAUSAL_LM'))
 trainable=sum(p.numel() for p in model.parameters() if p.requires_grad); total=sum(p.numel() for p in model.parameters())
 optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=5e-4)
 started=time.perf_counter(); losses=[]; model.train(); optimizer.zero_grad()
 for epoch in range(4):
  for index,row in enumerate(data):
   prefix=prompt(tok,row['input']); x=tok(prefix+row['output'],return_tensors='pt'); labels=x['input_ids'].clone(); labels[:,:-1]=-100
   loss=model(**x,labels=labels).loss; (loss/8).backward(); losses.append(float(loss.detach()))
   if (index+1)%8==0 or index+1==len(data): optimizer.step(); optimizer.zero_grad()
   if (index+1)%20==0: print('epoch',epoch+1,'sample',index+1,'loss',round(losses[-1],4),flush=True)
 model.save_pretrained(out/'adapter'); tok.save_pretrained(out/'adapter')
 result=dict(base='Qwen/Qwen2.5-0.5B-Instruct',seed=42,train_samples=len(data),test_samples=len(TEST),epochs=4,rank=8,alpha=16,gradient_accumulation=8,learning_rate=5e-4,layers=[20,21,22,23],dtype='float32',device='cpu',trainable=trainable,total=total,training_seconds=round(time.perf_counter()-started,2),losses=losses,baseline=baseline,finetuned=evaluate())
 (out/'training_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print('finetuned',result['finetuned']['accuracy'],flush=True)
