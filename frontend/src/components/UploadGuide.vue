<template>
  <div class="upload-guide">
    <el-button text type="primary" @click="expanded=!expanded">格式要求与演示样例</el-button>
    <div v-if="expanded">
      <p v-if="kind==='signal'">同时选择同名 .hea 和 .dat，或一份 CSV。要求 12 标准导联、100 Hz、10 秒。CSV 含 1000 行数值，列名为 I、II、III、aVR、aVL、aVF、V1—V6，可附 time_s 列。</p>
      <p v-else>PNG / JPEG，3 行 × 4 列标准报告图，并含底部 II 导联节律条。截图应保留完整波形，避免遮挡、旋转和透视变形。</p>
      <el-button v-if="kind==='signal'" size="small" @click="download('/input-template.csv','ecg-template.csv')">下载 CSV 空模板</el-button>
      <p class="muted">模板需要填写真实数值；以下演示文件来自 PTB-XL 公开测试集，已完成实验预处理。演示分析会保存为所选档案的新检查，请使用演示档案。</p>
      <el-select v-model="sampleId" placeholder="选择公开演示样本"><el-option v-for="s in catalog" :key="s.id" :value="s.id" :label="s.label" /></el-select>
      <el-button size="small" :loading="busy" @click="useSample" :disabled="!sampleId">载入演示文件</el-button>
      <el-button v-if="kind==='image' && sampleId" size="small" @click="showExample">查看标准布局</el-button>
      <el-image v-if="example" :src="example" :preview-src-list="[example]" style="width:100%;margin-top:12px" />
    </div>
    <p v-if="header" class="muted">头文件声明：{{ header }}。实际内容仍需保存后由服务器校验。</p>
  </div>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount,watch} from 'vue';
import {api,get,download} from '../api';
const props=defineProps<{kind:string;files:File[]}>();
const emit=defineEmits<{(e:'sample',files:File[]):void}>();
const expanded=ref(false),catalog=ref<any[]>([]),sampleId=ref<number>(),busy=ref(false),header=ref(''),example=ref('');
onMounted(async()=>{catalog.value=await get('/samples/catalog');sampleId.value=catalog.value[0]?.id;});
watch(()=>props.files,async files=>{header.value='';const f=files.find(x=>x.name.toLowerCase().endsWith('.hea'));if(!f)return;const lines=(await f.text()).trim().split(/\r?\n/);const a=lines[0].trim().split(/\s+/);header.value=`${a[1]} 导联 · ${a[2]} Hz · ${a[3]} 采样点`;});
async function fetchFile(name:string){const {data}=await api.get(`/samples/${sampleId.value}/files/${encodeURIComponent(name)}`,{responseType:'blob'});return new File([data],name,{type:data.type});}
async function useSample(){busy.value=true;try{const row=catalog.value.find(s=>s.id===sampleId.value);const names=row.files.filter((x:string)=>props.kind==='signal'?/\.(hea|dat)$/.test(x):x.endsWith('.png'));emit('sample',await Promise.all(names.map(fetchFile)));}finally{busy.value=false;}}
async function showExample(){if(example.value)URL.revokeObjectURL(example.value);const f=await fetchFile('report.png');example.value=URL.createObjectURL(f);}
onBeforeUnmount(()=>{if(example.value)URL.revokeObjectURL(example.value);});
</script>
<style scoped>.upload-guide{padding:12px;background:#f0f7ff;border:1px solid #d8e8f8;border-radius:10px;margin:12px 0;font-size:13px;line-height:1.7}.upload-guide p{font-size:13px;line-height:1.7}.upload-guide .el-select{margin:8px 0;width:100%}.upload-guide .el-button{margin-left:0;margin-right:8px;white-space:normal;height:auto;min-height:28px}</style>
