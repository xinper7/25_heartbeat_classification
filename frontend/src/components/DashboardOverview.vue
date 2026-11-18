<template>
  <section class="overview-workspace">
    <div class="page-heading overview-titlebar">
      <div>
        <div class="eyebrow">WORKSPACE OVERVIEW</div>
        <h1>工作概览</h1>
      </div>
      <div class="overview-heading-actions"><span class="overview-title-note">数据总览 · 检查与分析</span><el-button v-if="canAnalyze" text :loading="busy" @click="$emit('import-samples')">导入演示样本</el-button></div>
    </div>
    <header class="overview-hero">
      <div class="hero-copy">
        <span class="hero-kicker">CARDIO · 智能心电工作空间</span>
        <h1>让每一次检查，<br class="hero-mobile-break" />清晰有序</h1>
        <p>从数字波形到标准报告图，连接模型分析、专业复核与结果归档。</p>
        <div class="hero-actions">
          <el-button
            v-if="canAnalyze"
            type="primary"
            @click="$emit('new-study')"
            ><el-icon><Plus /></el-icon>新建检查</el-button
          ><el-button @click="$emit('navigate', 'agent')"
            >打开工作助手 <el-icon><ArrowRight /></el-icon
          ></el-button>
        </div>
      </div>
      <div class="hero-visual" aria-hidden="true">
        <div class="hero-orbit orbit-one"></div>
        <div class="hero-orbit orbit-two"></div>
        <div class="hero-ecg">
          <svg viewBox="0 0 340 140">
            <path
              class="ecg-shadow"
              d="M0 75h75l15-12 18 12h25l12 12 20-65 23 104 18-51h45l15-18 18 18h56"
            />
            <path
              d="M0 75h75l15-12 18 12h25l12 12 20-65 23 104 18-51h45l15-18 18 18h56"
            />
          </svg>
        </div>
        <span class="visual-chip chip-a">12 导联数字信号</span
        ><span class="visual-chip chip-b">标准报告图分析</span
        ><span class="visual-caption">双输入 · 同一工作空间</span>
      </div>
    </header>
    <div class="overview-metrics">
      <button
        v-for="item in metrics"
        :key="item.label"
        class="overview-metric"
        @click="$emit('navigate', item.route, item.filter ? {status:item.filter} : {})"
      >
        <span :class="['metric-symbol', item.tone]"
          ><el-icon><component :is="item.icon" /></el-icon></span
        ><span class="metric-main"
          ><span>{{ item.label }}</span
          ><strong>{{ item.value }}<small>份</small></strong
          ><small>{{ item.note }}</small></span
        ><el-icon class="metric-arrow"><ArrowRight /></el-icon>
      </button>
    </div>
    <div class="overview-columns">
      <div class="overview-primary">
        <section class="workspace-section">
          <div class="workspace-section-heading">
            <div>
              <span class="section-marker"></span>
              <h2>开始一项分析</h2>
            </div>
            <span>选择与你的文件对应的入口</span>
          </div>
          <div class="overview-entries">
            <button class="overview-entry" @click="$emit('navigate', 'signal')">
              <span class="analysis-symbol signal"
                ><el-icon><SignalIcon /></el-icon
              ></span>
              <div>
                <span class="entry-eyebrow">SIGNAL ANALYSIS</span>
                <h3>数字心电信号</h3>
                <p>12导联波形预览与五类模型分析</p>
                <span class="format-chip">WFDB / CSV</span>
              </div>
              <el-icon class="entry-arrow"><ArrowRight /></el-icon></button
            ><button class="overview-entry" @click="$emit('navigate', 'image')">
              <span class="analysis-symbol image"
                ><el-icon><ReportIcon /></el-icon
              ></span>
              <div>
                <span class="entry-eyebrow">REPORT ANALYSIS</span>
                <h3>标准心电报告图</h3>
                <p>图片预览、模型分析与结果留存</p>
                <span class="format-chip">PNG / JPEG</span>
              </div>
              <el-icon class="entry-arrow"><ArrowRight /></el-icon>
            </button>
          </div>
        </section>
        <section class="workspace-section recent-section">
          <div class="workspace-section-heading">
            <div>
              <span class="section-marker"></span>
              <h2>近期检查</h2>
              <span class="section-count"
                >最近 {{ dashboard.recent?.length || 0 }} 条</span
              >
            </div>
            <el-button text @click="$emit('navigate', 'studies')"
              >全部记录 <el-icon><ArrowRight /></el-icon
            ></el-button>
          </div>
          <el-table
            :data="dashboard.recent || []"
            class="record-table clickable"
            @row-click="(row: any) => $emit('open-study', row.id)"
            ><el-table-column label="检查记录" min-width="200"
              ><template #default="{ row }"
                ><strong class="table-title">{{ row.title }}</strong
                ><small class="table-sub"
                  >ECG-{{ String(row.id).padStart(5, "0") }}</small
                ></template
              ></el-table-column
            ><el-table-column
              prop="patient_name"
              label="受检者"
              min-width="120" /><el-table-column label="类型" width="100"
              ><template #default="{ row }"
                ><span class="input-type-label">{{
                  row.kind === "signal" ? "数字信号" : "报告图"
                }}</span></template
              ></el-table-column
            ><el-table-column label="状态" width="105"
              ><template #default="{ row }"
                ><span :class="['status', row.status]">{{
                  statusNames[row.status] || row.status
                }}</span></template
              ></el-table-column
            ><el-table-column label="创建时间" width="120"
              ><template #default="{ row }">{{
                date(row.created_at)
              }}</template></el-table-column
            ><template #empty
              ><el-empty
                description="还没有检查记录，先建立档案并新建检查。"
                :image-size="70" /></template
          ></el-table>
        </section>
      </div>
      <aside class="overview-secondary">
        <section class="workspace-section">
          <div class="workspace-section-heading">
            <div>
              <span class="section-marker"></span>
              <h2>检查状态分布</h2>
            </div>
            <span>当前可访问记录</span>
          </div>
          <div class="status-chart">
            <div
              class="status-donut"
              :style="{ background: donut }"
              role="img"
              :aria-label="
                '检查状态分布，共' + (dashboard.study_count || 0) + '份'
              "
            >
              <div>
                <strong>{{ dashboard.study_count || 0 }}</strong
                ><span>检查总数</span>
              </div>
            </div>
            <ul class="chart-legend">
              <li v-for="s in distribution" :key="s.label">
                <i :style="{ background: s.color }"></i
                ><span>{{ s.label }}</span
                ><strong>{{ s.value }}</strong>
              </li>
            </ul>
          </div>
          <p class="chart-note">按业务状态统计，不代表模型准确率。</p>
        </section>
        <section class="workspace-section">
          <div class="workspace-section-heading">
            <div>
              <span class="section-marker"></span>
              <h2>待办工作</h2>
            </div>
            <el-icon><Clock /></el-icon>
          </div>
          <button
            v-for="task in tasks"
            :key="task.label"
            class="work-task"
            @click="$emit('navigate', task.route, {status:task.filter})"
          >
            <span :class="['task-dot', task.tone]"></span
            ><span>{{ task.label }}</span
            ><strong>{{ task.value }}</strong
            ><el-icon><ArrowRight /></el-icon>
          </button>
        </section>
        <section class="workspace-section service-section">
          <div class="workspace-section-heading">
            <div>
              <span class="section-marker"></span>
              <h2>模型服务</h2>
            </div>
            <el-button text @click="$emit('navigate', 'models')"
              >详情</el-button
            >
          </div>
          <div v-for="m in modelStates" :key="m.label" class="service-item">
            <span :class="['service-light', { ready: m.ready }]"></span>
            <div>
              <strong>{{ m.label }}</strong
              ><small>{{ m.name }}</small>
            </div>
            <span :class="['service-label', { ready: m.ready }]">{{
              m.ready ? "已加载" : "未就绪"
            }}</span>
          </div>
          <div class="service-footer">
            <el-icon><Lock /></el-icon>本机运行 · 专业复核
          </div>
        </section>
      </aside>
    </div>
    <p class="overview-footnote">
      <el-icon><InfoFilled /></el-icon
      >模型预测为辅助分析信息，专业复核意见独立记录。
    </p>
  </section>
</template>
<script setup lang="ts">
import { computed } from "vue";
import {
  Plus,
  ArrowRight,
  User,
  Files,
  Checked,
  Document,
  Clock,
  Lock,
  InfoFilled,
} from "@element-plus/icons-vue";
import SignalIcon from "./SignalIcon.vue";
import ReportIcon from "./ReportIcon.vue";
const props = defineProps<{
  dashboard: any;
  canAnalyze: boolean;
  canReview: boolean;
  busy: boolean;
}>();
defineEmits<{
  (e: "navigate", route: string, query?: Record<string,string>): void;
  (e: "new-study"): void;
  (e: "import-samples"): void;
  (e: "open-study", id: number): void;
}>();
const count = (key: string) => Number(props.dashboard.counts?.[key] || 0);
const metrics = computed(() => [
  {
    label: "受检者档案",
    value: props.dashboard.patient_count || 0,
    note: "统一管理基础资料",
    route: "patients",
    icon: User,
    tone: "blue",
  },
  {
    label: "全部检查",
    value: props.dashboard.study_count || 0,
    note: "数字信号与报告图",
    route: "studies",
    icon: Files,
    tone: "cyan",
  },
  {
    label: "等待复核",
    filter: "awaiting_review",
    value: count("awaiting_review"),
    note: "模型分析已完成",
    route: props.canReview ? "review" : "studies",
    icon: Checked,
    tone: "amber",
  },
  {
    label: "已归档",
    filter: "archived",
    value: count("archived"),
    note: "已保存专业复核意见",
    route: "studies",
    icon: Document,
    tone: "green",
  },
]);
const distribution = computed(() => [
  {
    label: "待上传 / 待分析",
    value: count("awaiting_upload") + count("ready"),
    color: "#57a6f5",
  },
  {
    label: "排队 / 分析中",
    value: count("queued") + count("processing"),
    color: "#7b8ee6",
  },
  { label: "等待复核", value: count("awaiting_review"), color: "#f1bb65" },
  { label: "已归档", value: count("archived"), color: "#42c9b4" },
  { label: "分析失败", value: count("failed"), color: "#ee8f98" },
]);
const donut = computed(() => {
  const total = distribution.value.reduce((a, s) => a + s.value, 0);
  if (!total) return "#e5eef8";
  let start = 0;
  return (
    "conic-gradient(" +
    distribution.value
      .map((s) => {
        const end = start + (s.value / total) * 100;
        const segment = `${s.color} ${start}% ${end}%`;
        start = end;
        return segment;
      })
      .join(",") +
    ")"
  );
});
const tasks = computed(() => [
  {
    label: "待分析检查",
    filter: "ready",
    value: count("ready"),
    route: "studies",
    tone: "blue",
  },
  {
    label: "等待专业复核",
    filter: "awaiting_review",
    value: count("awaiting_review"),
    route: props.canReview ? "review" : "studies",
    tone: "amber",
  },
  {
    label: "需要处理的失败记录",
    filter: "failed",
    value: count("failed"),
    route: "studies",
    tone: "rose",
  },
]);
const modelStates = computed(() => [
  {
    label: "数字信号模型",
    name: "ResNet1D · A3",
    ready: !!props.dashboard.models_ready?.signal,
  },
  {
    label: "报告图模型",
    name: "EfficientNet-B0 · ONNX",
    ready: !!props.dashboard.models_ready?.image,
  },
]);
const statusNames: Record<string, string> = {
  awaiting_upload: "待上传",
  ready: "已校验",
  queued: "已排队",
  processing: "分析中",
  pending_correction: "待补充",
  awaiting_review: "待复核",
  archived: "已归档",
  failed: "失败",
};
function date(value: string) {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";
}
</script>
