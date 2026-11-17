<template>
  <section class="agent-workspace">
    <div class="page-heading"><div><h1>心电工作助手</h1><p>询问上传要求、模型信息，或选择检查后读取结果、运行分析。</p></div><el-tag>本地 Qwen · LoRA</el-tag></div>
    <el-alert title="助手仅编排已有工具并展示其返回结果，分析结论需要专业复核。" type="info" :closable="false" />
    <el-alert v-if="status" :title="`Agent：${status.ready ? (status.loaded ? '已加载' : '文件就绪，首次操作时加载') : '模型文件未就绪'}；适配器离线分类正确率 ${status.metrics?.accuracy == null ? '未测量' : (status.metrics.accuracy*100).toFixed(0)+'%'}（${status.metrics?.test_samples || 0} 条，非当前端到端成功率）；适配器 ${status.metrics?.adapter || '未标注'}。请核对工具后确认。`" type="warning" :closable="false" />
    <div class="agent-controls">
      <el-select v-model="studyId" placeholder="可选：选择检查记录" filterable clearable data-testid="agent-study">
        <el-option v-for="s in studies" :key="s.id" :value="s.id" :label="`#${s.id} · ${s.title} · ${s.kind === 'signal' ? '信号' : '图片'}`" />
      </el-select>
      <el-button @click="fresh" :disabled="busy">新建会话</el-button>
    </div>
    <div class="agent-suggestions"><el-button v-for="q in suggestions" :key="q" @click="query = q" :disabled="busy" size="small">{{ q }}</el-button></div>
    <div class="agent-thread" aria-live="polite" data-testid="agent-messages">
      <p v-if="!messages.length" class="muted">从“怎么上传文件”开始，或选择一条已有检查。会话保存在本机，刷新后可以继续。</p>
      <article v-for="(m, i) in messages" :key="i" :class="['agent-message',m.role]">
        <strong>{{ m.role === 'user' ? '你' : '工作助手' }}</strong><p>{{ m.content }}</p>
        <div v-if="m.tool_calls?.length" class="agent-trace"><el-tag v-for="(t,j) in m.tool_calls" :key="j" size="small">工具：{{ t.name }}</el-tag><span>{{ m.elapsed_ms }} ms</span></div>
      </article>
      <p v-if="busy" role="status">正在选择并执行工具，请稍候…</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
    </div>
    <section v-if="pending" class="agent-message">
      <h3>确认本轮操作</h3><p>工具：{{ pending.label }} · {{ pending.writes ? '可能保存分析结果' : '只读' }}</p>
      <p>检查：{{ pending.study_id ? `#${pending.study_id} · ${pending.study_title}` : '未关联检查' }}</p><p>{{ pending.note }}</p>
      <el-select v-model="correctTool" placeholder="工具选错了？手动修正" :disabled="busy"><el-option v-for="(v,k) in toolLabels" :key="k" :value="k" :label="v" /></el-select>
      <div class="agent-actions"><el-button @click="pending=null">取消</el-button><el-button @click="send" :disabled="busy || !correctTool">重新预览</el-button><el-button type="primary" @click="execute" :loading="busy" :disabled="pending.writes && !allowAnalysis">确认执行</el-button></div>
    </section>
    <el-form @submit.prevent="send" class="agent-composer">
      <el-input v-model="query" type="textarea" :rows="3" maxlength="1000" show-word-limit placeholder="例如：读取这条检查的结果；怎么准备CSV？" data-testid="agent-query" :disabled="busy" />
      <div class="agent-actions"><el-checkbox v-model="allowAnalysis" :disabled="busy">允许本轮运行模型分析</el-checkbox><el-button type="primary" native-type="submit" :loading="busy" :disabled="!query.trim()" data-testid="agent-send">预览操作</el-button></div>
      <small class="muted">每轮先预览工具和检查，再确认执行。会话只保存操作历史；工具只访问上方选中的检查，不会从聊天内容推断患者身份。</small>
    </el-form>
  </section>
</template>
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { api, get } from '../api';
type Message = {role:string;content:string;tool_calls?:{name:string}[];elapsed_ms?:number};
const key = `ecg-agent-${sessionStorage.getItem('ecg-token')?.slice(-16)}`;
const sessionId=ref(sessionStorage.getItem(key)||'');
const studyId=ref<number>(); const studies=ref<any[]>([]); const messages=ref<Message[]>([]);
const query=ref(''); const busy=ref(false); const error=ref(''); const allowAnalysis=ref(false);
const status=ref<any>(null); const pending=ref<any>(null);const correctTool=ref('');
const toolLabels:Record<string,string>={analyze_signal:'数字信号分析',analyze_image:'报告图分析',read_result:'读取已有结果',input_help:'上传格式说明',model_info:'模型版本信息'};
watch([query,studyId],()=>{pending.value=null;correctTool.value='';});
const suggestions=['怎么上传文件','当前用什么模型','读取检查结果','分析数字心电信号','分析报告图片'];
function fresh(){pending.value=null;correctTool.value='';sessionId.value='';messages.value=[];studyId.value=undefined;sessionStorage.removeItem(key);error.value='';}
onMounted(async()=>{try {status.value=await get('/agent/status'); const data=await get('/studies',{page_size:100}); studies.value=data.items||data;
 if(sessionId.value){ const s=await get(`/agent/sessions/${sessionId.value}`);messages.value=s.messages;studyId.value=s.study_id||undefined;}
}catch{error.value='加载会话或检查列表失败，可新建会话后重试。';}});
async function send(){
 if(busy.value||!query.value.trim())return;busy.value=true;error.value='';pending.value=null;
 try{const {data}=await api.post('/agent/plan',{query:query.value,session_id:sessionId.value||null,study_id:studyId.value||null,selected_tool:correctTool.value||null},{timeout:120000});
 const r=data.result;if(r.clarification){error.value=r.clarification;return;}
 sessionId.value=r.session_id;sessionStorage.setItem(key,r.session_id);pending.value=r;
 }catch(e:any){error.value=e.response?.data?.msg||'预览失败，请稍后重试。';}finally{busy.value=false;}
}
async function execute(){if(!pending.value||busy.value)return;busy.value=true;error.value='';const text=query.value;
 try{const {data}=await api.post('/agent/chat',{query:text,session_id:sessionId.value,study_id:studyId.value||null,allow_analysis:allowAnalysis.value,plan_token:pending.value.token},{timeout:120000});const r=data.result;
 messages.value.push({role:'user',content:text},{role:'agent',content:r.agent,tool_calls:r.tool_calls,elapsed_ms:r.elapsed_ms});query.value='';allowAnalysis.value=false;status.value=await get('/agent/status');}
 catch(e:any){error.value=e.response?.data?.msg||'执行失败，请重新预览后重试。';}finally{pending.value=null;busy.value=false;}
}
</script>
<style scoped>
.agent-workspace{max-width:1040px;margin:auto}.agent-controls{display:flex;gap:12px;margin:20px 0}.agent-controls .el-select{flex:1}.agent-suggestions{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.agent-suggestions .el-button{margin:0}.agent-thread{min-height:260px;max-height:60vh;overflow:auto;border:1px solid #dce3ef;background:#f8faff;border-radius:12px;padding:20px}.agent-message{padding:16px;margin:0 0 14px;background:white;border:1px solid #e1e6ee;border-radius:10px}.agent-message.user{background:#edf3ff;margin-left:12%}.agent-message p{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}.agent-trace{display:flex;gap:10px;flex-wrap:wrap;color:#64748b}.agent-composer{margin-top:18px}.agent-actions{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:12px 0}@media(max-width:600px){.agent-controls,.agent-actions{flex-direction:column;align-items:stretch}.agent-thread{padding:10px}.agent-message.user{margin-left:0}}
</style>
