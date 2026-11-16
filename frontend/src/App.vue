<template>
  <div v-if="booting" class="boot-screen">
    <p>正在连接心电工作空间…</p>
  </div>
  <div v-else-if="!user" class="login-screen">
    <section class="login-story">
      <div class="login-story-copy">
        <div class="eyebrow">为专业判断，整理每一份心电信息</div>
        <h1>从一份心电数据，<br />到一条完整检查记录。</h1>
        <p>数字信号与标准报告图独立分析，<br />连接检查、专业复核与归档。</p>
        <div class="login-wave">
          <svg viewBox="0 0 600 120">
            <path
              d="M0 65 H105 L125 50 L145 65 H200 L215 75 L232 10 L250 110 L270 65 H330 L350 45 L375 65 H600"
            />
          </svg>
        </div>
        <div class="story-features">
          <span>12导联信号分析</span><span>标准报告图识别</span
          ><span>检查全程可追溯</span>
        </div>
      </div>
    </section>
    <section class="login-form">
      <div class="login-box">
        <span class="eyebrow">欢迎回来</span>
        <h2>登录工作空间</h2>
        <p class="muted">使用分配给你的专业人员账号继续。</p>
        <el-alert v-if="capsLock" title="大写锁定已开启，请检查密码大小写" type="warning" :closable="false" />
          <el-form @submit.prevent="login" label-position="top"
          ><el-form-item label="账号"
            ><el-input
              v-model="loginForm.username"
              placeholder="请输入账号"
              size="large"
              autocomplete="username"
              data-testid="login-username" /></el-form-item
          ><el-form-item label="密码"
            ><el-input
              v-model="loginForm.password"
              type="password"
              placeholder="请输入密码"
              show-password
              size="large"
              autocomplete="current-password"
              @keydown="capsLock = $event.getModifierState('CapsLock')"
                data-testid="login-password" /></el-form-item
          ><el-button
            native-type="submit"
            type="primary"
            size="large"
            class="full"
            :loading="busy"
            data-testid="login-submit"
            >进入工作空间 <el-icon><ArrowRight /></el-icon></el-button
        ></el-form>
      </div>
    </section>
  </div>
  <div v-else class="app-shell">
    <div v-if="mobileNav" class="nav-mask" @click="mobileNav = false"></div>
    <aside class="sidebar" :class="{ 'mobile-open': mobileNav }">
      <a class="brand" href="/dashboard" @click.prevent="go('dashboard')"
        ><span class="brand-symbol" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M3 17h6l3-9 6 17 4-12 2 4h5" /></svg></span><span class="brand-copy"><span class="brand-title">心电分析系统</span><small>CARDIO WORKSPACE</small></span></a
      >
      <nav>
        <button
          v-for="item in navItems"
          :key="item.key"
          :class="{ active: page === item.key }"
          :aria-label="item.label"
          @click="go(item.key)"
        >
          <el-icon><component :is="item.icon" /></el-icon
          ><span>{{ item.label }}</span
          ><span
            v-if="item.key === 'review' && dashboard.counts?.awaiting_review"
            class="nav-count"
            >{{ dashboard.counts.awaiting_review }}</span
          >
        </button>
      </nav>
      <div class="sidebar-bottom">
        <button class="help-link" @click="openDocs">
          <el-icon><Document /></el-icon>API 文档
          <el-icon><TopRight /></el-icon>
        </button>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <div class="breadcrumb">
          <button
            class="mobile-toggle"
            @click="mobileNav = true"
            aria-label="打开导航"
          >
            <el-icon><Menu /></el-icon></button
          ><span>工作空间</span><span class="slash">/</span
          ><strong>{{ pageTitle }}</strong>
        </div>
        <div class="topbar-right">
          <span class="today">{{ today }}</span
          ><el-dropdown trigger="click"
            ><button
              class="user-button"
              type="button"
              :aria-label="'账号菜单：' + user.username"
            >
              <span class="account-id" :title="user.username">{{ user.username }}</span
              ><el-icon><ArrowDown /></el-icon></button
            ><template #dropdown
              ><el-dropdown-menu
                ><el-dropdown-item @click="passwordDialog = true"
                  >修改登录密码</el-dropdown-item
                ><el-dropdown-item divided @click="logout"
                  >退出登录</el-dropdown-item
                ></el-dropdown-menu
              ></template
            ></el-dropdown
          >
        </div>
      </header>
      <main class="content" :class="'page-' + page" v-loading="loading">
        <DashboardOverview
          v-if="page === 'dashboard'"
          :dashboard="dashboard"
          :can-analyze="canAnalyze"
          :can-review="canReview"
          :busy="busy"
          @new-study="studyDialog = true"
          @import-samples="importSamples"
          @navigate="go"
          @open-study="openStudy"
        />

        <template v-else-if="page === 'patients'">
          <div class="page-heading">
            <div>
              <div class="eyebrow">PATIENT RECORDS</div>
              <h1>受检者档案</h1>
              <p>管理基础资料，将多次检查连接到同一份档案。</p>
            </div>
            <el-button v-if="canAnalyze" type="primary" @click="editPatient()"
              ><el-icon><Plus /></el-icon> 新建档案</el-button
            >
          </div>
          <section class="panel">
            <div class="toolbar">
              <el-input
                v-model="search"
                placeholder="搜索姓名或档案编号"
                clearable
                @keyup.enter="loadPatients"
                @clear="loadPatients"
                ><template #prefix
                  ><el-icon><Search /></el-icon></template></el-input
              ><el-button @click="loadPatients">查询</el-button
              ><span class="toolbar-total">共 {{ patients.total }} 份档案</span>
            </div>
            <el-table :data="patients.items" class="record-table" stripe
              ><el-table-column label="受检者" min-width="180"
                ><template #default="{ row }"
                  ><div class="person-cell">
                    <strong>{{ row.name }}</strong
                    ><small class="table-sub">{{ row.code }}</small>
                  </div></template
                ></el-table-column
              ><el-table-column label="性别" width="100"
                ><template #default="{ row }">{{
                  sexNames[row.sex]
                }}</template></el-table-column
              ><el-table-column
                prop="age"
                label="年龄"
                width="90" /><el-table-column
                prop="note"
                label="备注"
                min-width="180"
                show-overflow-tooltip /><el-table-column
                label="操作"
                width="280"
                ><template #default="{ row }"
                  ><el-button
                    text
                    type="primary"
                    @click="viewPatient(row)"
                    >档案详情</el-button
                  ><el-button
                    class="action-edit"
                    v-if="canAnalyze"
                    text
                    @click="editPatient(row)"
                    >编辑</el-button
                  ><el-button
                    v-if="canAnalyze"
                    text
                    type="danger"
                    @click="removePatient(row)"
                    >删除</el-button
                  ></template
                ></el-table-column
              ><template #empty
                ><el-empty
                  description="暂无档案，创建一份受检者档案开始" /></template></el-table
            ><el-pagination
              class="pagination"
              layout="total, prev, pager, next"
              :total="patients.total"
              :page-size="20"
              v-model:current-page="listPage"
              @current-change="loadPatients"
            />
          </section>
        </template>

        <template v-else-if="page === 'signal' || page === 'image'">
          <div class="page-heading">
            <div>
              <div class="eyebrow">
                {{
                  page === "signal"
                    ? "SIGNAL ANALYSIS"
                    : "REPORT IMAGE ANALYSIS"
                }}
              </div>
              <h1>
                {{ page === "signal" ? "数字心电信号分析" : "标准报告图分析" }}
              </h1>
              <p>
                {{
                  page === "signal"
                    ? "完整12导联 · 100 Hz · 10秒记录"
                    : "既定3×4导联布局 · 底部完整10秒II导联节律条"
                }}
              </p>
            </div>
            <span class="model-pill"
              ><span class="dot"></span
              >{{
                page === "signal"
                  ? "ResNet1D · A3"
                  : "EfficientNet-B0 · ONNX FP32"
              }}</span
            >
          </div>
          <div class="workspace-grid">
            <section class="panel input-panel">
              <div class="panel-heading">
                <div>
                  <span class="step-number">01</span>
                  <h2>检查与数据输入</h2>
                </div>
                <el-button v-if="activeStudy" text @click="resetWorkspace"
                  >新建另一条</el-button
                >
              </div>
              <el-alert
                v-if="!canAnalyze"
                title="当前账号仅有复核权限，可在复核中心查看已有结果。"
                type="info"
                :closable="false"
              />
              <el-form
                label-position="top"
                :disabled="!canAnalyze || !!activeStudy"
                ><el-form-item label="受检者档案"
                  ><el-select
                    v-model="studyForm.patient_id"
                    filterable
                    placeholder="选择受检者"
                    class="full"
                    data-testid="workspace-patient"
                    ><el-option
                      v-for="p in patientOptions"
                      :key="p.id"
                      :value="p.id"
                      :label="`${p.name} · ${p.code}`" /></el-select
                  ><button
                    v-if="!patientOptions.length"
                    class="inline-link"
                    type="button"
                    @click="go('patients')"
                  >
                    先创建受检者档案 →
                  </button></el-form-item
                ><el-form-item label="检查名称"
                  ><el-input
                    v-model="studyForm.title"
                    placeholder="例如：常规静息心电检查"
                    maxlength="150"
                    data-testid="workspace-title"
                /></el-form-item>
                <el-form-item
                  v-if="page === 'signal'"
                  label="输入波形的处理状态"
                  ><el-select v-model="inputProfile" class="full"
                    ><el-option
                      label="实验处理版：已完成40 Hz低通，物理mV"
                      value="filtered_mv" /><el-option
                      label="原始波形：由系统进行40 Hz低通"
                      value="raw_mv" /></el-select
                ></el-form-item>
                <UploadGuide :kind="page" :files="selectedFiles" @sample="files => { selectedFiles=files;inputProfile='filtered_mv'; }" />
                <div v-if="page === 'signal' && (!selectedFiles.length || selectedFiles.some(f => f.name.toLowerCase().endsWith('.csv')))" class="two-fields">
                  <el-form-item label="CSV采样率"
                    ><el-input-number
                      v-model="samplingRate"
                      :min="100"
                      :max="100"
                      controls-position="right" /></el-form-item
                  ><el-form-item label="CSV数值单位"
                    ><el-select v-model="inputUnit"
                      ><el-option label="mV" value="mV" /><el-option
                        label="μV"
                        value="uV" /></el-select
                  ></el-form-item>
                </div> </el-form
              ><label
                class="upload-zone"
                :class="{ disabled: !canAnalyze || !!activeStudy }"
                ><input
                  ref="fileInput"
                  type="file"
                  :accept="
                    page === 'signal' ? '.csv,.hea,.dat' : '.png,.jpg,.jpeg'
                  "
                  :multiple="page === 'signal'"
                  :disabled="!canAnalyze || !!activeStudy"
                  @change="filesChanged"
                  data-testid="workspace-files"
                /><el-icon><UploadFilled /></el-icon
                ><strong>{{
                  selectedFiles.length
                    ? `${selectedFiles.length} 个文件已选择`
                    : "点击选择检查文件"
                }}</strong
                ><span>{{
                  page === "signal"
                    ? "一对 .hea/.dat，或一份规范CSV"
                    : "完整标准报告图，PNG / JPG / JPEG"
                }}</span
                ><small>单次总大小不超过16 MB</small></label
              >
              <div class="file-chips">
                <span v-for="f in selectedFiles" :key="f.name"
                  >{{ f.name }}
                  <small>{{ (f.size / 1024).toFixed(0) }} KB</small></span
                >
              </div>
              <el-alert
                v-if="page === 'image'"
                title="请上传与项目训练时相同布局的完整报告图。图片布局不由系统自动识别。"
                type="info"
                :closable="false"
              /><el-button
                class="full upload-submit"
                type="primary"
                :disabled="
                  !canAnalyze || !selectedFiles.length || !!activeStudy
                "
                :loading="busy"
                @click="submitInput"
                data-testid="upload-submit"
                >保存检查并校验数据</el-button
              >
              <div v-if="activeStudy" class="validation-success">
                <el-icon><CircleCheckFilled /></el-icon> 数据校验通过 · ECG-{{
                  pad(activeStudy.id)
                }}
              </div>
            </section>
            <div class="workspace-main">
              <section class="panel preview-panel">
                <div class="panel-heading">
                  <div>
                    <span class="step-number">02</span>
                    <h2>数据预览</h2>
                  </div>
                  <span class="muted">{{
                    activeStudy ? activeStudy.patient_name : "尚未加载检查数据"
                  }}</span>
                </div>
                <template v-if="activeStudy"
                  ><div v-if="page === 'signal'" class="lead-select">
                    <el-select
                      v-model="selectedLeads"
                      multiple
                      collapse-tags
                      :max-collapse-tags="4"
                      placeholder="选择导联"
                      ><el-option
                        v-for="lead in leads"
                        :key="lead"
                        :label="lead"
                        :value="lead" /></el-select
                    ><span>滚轮缩放 / 拖动查看时间区间</span>
                  </div>
                  <SignalChart
                    v-if="page === 'signal' && signalPreview"
                    :data="signalPreview"
                    :selected="selectedLeads" /><el-image
                    v-else-if="imagePreview"
                    :src="imagePreview"
                    :preview-src-list="[imagePreview]"
                    fit="contain"
                    class="report-preview" />
                  <div class="input-facts">
                    <span v-if="page === 'signal'"
                      >12 导联 · 100 Hz · 10秒 · mV</span
                    ><span v-else
                      >{{ activeStudy.metadata.width }} ×
                      {{ activeStudy.metadata.height }} px → 224 × 224</span
                    ><span>{{
                      activeStudy.metadata.preprocessing_version
                    }}</span>
                  </div>
                  <el-alert
                    v-for="warning in activeStudy.metadata.warnings || []"
                    :key="warning"
                    :title="warning"
                    type="warning"
                    :closable="false"
                    class="warning-line"
                /></template>
                <div v-else class="preview-empty">
                  <svg viewBox="0 0 260 80">
                    <path
                      d="M0 45 H65 L80 34 L94 45 H113 L125 53 L139 5 L151 75 L165 45 H260"
                    />
                  </svg>
                  <h3>
                    {{
                      page === "signal"
                        ? "波形将在这里呈现"
                        : "报告图将在这里呈现"
                    }}
                  </h3>
                  <p>选择档案并上传文件后，先检查输入内容。</p>
                </div>
              </section>
              <section class="panel result-panel">
                <div class="panel-heading">
                  <div>
                    <span class="step-number">03</span>
                    <h2>模型分析结果</h2>
                  </div>
                  <el-button
                    type="primary"
                    :disabled="
                      !canAnalyze ||
                      !activeStudy ||
                      !['ready', 'failed'].includes(activeStudy.status)
                    "
                    :loading="analyzing"
                    @click="runAnalysis"
                    data-testid="analyze-submit"
                    ><el-icon><Cpu /></el-icon>
                    {{ analyzing ? "正在分析" : "开始分析" }}</el-button
                  >
                </div>
                <template v-if="latestAnalysis"
                  ><div class="result-summary">
                    <span
                      :class="[
                        'status',
                        latestAnalysis.review ? 'archived' : 'awaiting_review',
                      ]"
                      >{{
                        latestAnalysis.review ? "已复核" : "待专业复核"
                      }}</span
                    ><span
                      >纯推理
                      {{ latestAnalysis.timings.inference_ms.toFixed(2) }}
                      ms</span
                    ><span v-if="displayMs"
                      >本次完整展示 {{ displayMs.toFixed(0) }} ms</span
                    >
                  </div>
                  <div class="prediction-list">
                    <div
                      v-for="p in sortedPredictions(latestAnalysis.predictions)"
                      :key="p.code"
                      class="prediction"
                    >
                      <div class="prediction-name">
                        <strong>{{ p.code }}</strong
                        ><span>{{ p.name }}</span>
                      </div>
                      <div class="probability-track">
                        <i
                          :style="{ width: `${p.probability * 100}%` }"
                          :class="{ positive: p.positive }"
                        ></i
                        ><b
                          :style="{ left: `${p.threshold * 100}%` }"
                          :title="`阈值 ${p.threshold}`"
                        ></b>
                      </div>
                      <span class="probability-number"
                        >{{ (p.probability * 100).toFixed(1)
                        }}<small>%</small></span
                      ><span
                        :class="['prediction-label', { positive: p.positive }]"
                        >{{ p.positive ? "阳性" : "阴性" }}</span
                      >
                    </div>
                  </div>
                  <div class="result-caption">
                    五类独立预测，可同时出现多个阳性标签。数值为模型分数，不代表患病概率；竖线为固定分类阈值。
                  </div>
                  <div class="result-actions">
                    <el-button
                      class="action-export"
                      @click="downloadReport(latestAnalysis.id)"
                      ><el-icon><Download /></el-icon> 导出报告</el-button
                    ><el-button
                      class="action-review"
                      v-if="canReview"
                      @click="showReview(latestAnalysis)"
                      >填写复核意见</el-button
                    ><el-button text @click="openStudy(activeStudy.id)"
                      >完整检查记录 →</el-button
                    >
                  </div>
                  <div v-if="latestAnalysis.review" class="review-note">
                    <strong
                      >复核意见 · {{ latestAnalysis.review.reviewer }}</strong
                    >
                    <p>{{ latestAnalysis.review.comment }}</p>
                  </div></template
                ><el-empty
                  v-else
                  description="完成数据校验后，点击开始分析"
                  :image-size="65"
                />
              </section>
            </div>
          </div>
        </template>

        <template v-else-if="page === 'studies' || page === 'review'">
          <div class="page-heading">
            <div>
              <div class="eyebrow">
                {{
                  page === "review"
                    ? "PROFESSIONAL REVIEW"
                    : "EXAMINATION RECORDS"
                }}
              </div>
              <h1>{{ page === "review" ? "复核中心" : "检查记录" }}</h1>
              <p>
                {{
                  page === "review"
                    ? "结合原始数据与模型结果，独立记录专业意见。"
                    : "从输入文件到归档报告，查看每条检查的完整过程。"
                }}
              </p>
            </div>
            <div class="heading-actions">
              <el-button
                class="action-export"
                @click="download('/exports/studies.csv', '心电检查记录.csv')"
                ><el-icon><Download /></el-icon> 导出清单</el-button
              ><el-button
                v-if="canAnalyze"
                type="primary"
                @click="studyDialog = true"
                ><el-icon><Plus /></el-icon> 新建检查</el-button
              >
            </div>
          </div>
          <section class="panel">
            <div class="toolbar wrap">
              <el-input
                v-model="search"
                placeholder="搜索检查、姓名、档案编号"
                clearable
                @keyup.enter="listPage=1;loadStudies()"
                @clear="listPage=1;loadStudies()"
                ><template #prefix
                  ><el-icon><Search /></el-icon></template></el-input
              ><el-select
                v-model="filterKind"
                placeholder="全部输入"
                clearable
                @change="listPage=1;loadStudies()"
                ><el-option label="数字信号" value="signal" /><el-option
                  label="标准报告图"
                  value="image" /></el-select
              ><el-select
                v-if="page !== 'review'"
                v-model="filterStatus"
                placeholder="全部状态"
                clearable
                @change="listPage=1;loadStudies()"
                ><el-option
                  v-for="(label, key) in statusNames"
                  :key="key"
                  :label="label"
                  :value="key" /></el-select
              ><el-select v-model="filterSource" placeholder="全部数据来源" clearable @change="listPage=1;loadStudies()"><el-option label="公开演示样本" value="sample"/><el-option label="其他上传记录" value="regular"/></el-select><el-date-picker
                v-model="dateRange"
                type="daterange"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                range-separator="至"
                style="max-width: 260px"
                @change="listPage=1;loadStudies()"
              /><el-button @click="listPage = 1; loadStudies()">查询</el-button
              ><el-button @click="resetFilters">重置筛选</el-button
              ><el-button
                v-if="canAnalyze && selectedStudies.length"
                type="primary"
                plain
                @click="queueSelected"
                >加入批量任务（{{ selectedStudies.length }}）</el-button
              >
            </div>
            <div v-if="patientFilter" class="filter-note">
              已按受检者筛选
              <el-button
                text
                @click="
                  patientFilter = null;
                  loadStudies();
                "
                >清除筛选</el-button
              >
            </div>
            <el-table
              :data="studies.items"
              class="record-table"
              stripe
              @selection-change="(rows: any[]) => (selectedStudies = rows)"
              ><el-table-column
                v-if="canAnalyze"
                type="selection"
                :selectable="
                  (row: any) => ['ready', 'failed'].includes(row.status)
                "
                width="45" /><el-table-column label="检查名称" min-width="220"
                ><template #default="{ row }"
                  ><button
                    class="table-title record-link"
                    @click="openStudy(row.id)"
                  >
                    {{ row.title }}</button
                  ><small class="table-sub"
                    >ECG-{{ pad(row.id) }} · {{ row.patient_code }}</small
                  ></template
                ></el-table-column
              ><el-table-column
                prop="patient_name"
                label="受检者"
                min-width="100" /><el-table-column label="输入方式" width="125"
                ><template #default="{ row }">{{
                  kindName(row.kind)
                }}</template></el-table-column
              ><el-table-column label="状态" width="135"
                ><template #default="{ row }"
                  ><span :class="'status ' + row.status">{{
                    statusNames[row.status]
                  }}</span></template
                ></el-table-column
              ><el-table-column label="创建时间" width="145"
                ><template #default="{ row }">{{
                  date(row.created_at)
                }}</template></el-table-column
              ><el-table-column label="操作" width="120"
                ><template #default="{ row }"
                  ><el-button text type="primary" @click="openStudy(row.id)">{{
                    page === "review" ? "查看复核" : "查看详情"
                  }}</el-button></template
                ></el-table-column
              ><template #empty
                ><el-empty
                  :description="
                    page === 'review'
                      ? '当前没有等待复核的检查'
                      : '暂无检查记录'
                  " /></template></el-table
            ><el-pagination
              class="pagination"
              layout="total, prev, pager, next"
              :total="studies.total"
              :page-size="20"
              v-model:current-page="listPage"
              @current-change="loadStudies"
            />
          </section>
        </template>

        <AgentChat v-else-if="page === 'agent'" />
        <template v-else-if="page === 'jobs'">
          <div class="page-heading">
            <div>
              <div class="eyebrow">TASK CENTER</div>
              <h1>批量任务</h1>
              <p>独立进程执行，进度保存在数据库；可关闭页面后回来查看。</p>
            </div>
            <el-button :loading="refreshingJobs" @click="refreshJobs"
              ><el-icon><Refresh /></el-icon> 刷新进度</el-button
            >
          </div>
          <el-alert
            title="在检查记录中勾选已校验的检查，创建批量任务。执行前需要单独启动Worker。"
            type="info"
            :closable="false"
            class="space-bottom"
          />
          <section
            v-for="job in jobList"
            :key="job.id"
            class="panel job-card"
            :class="'job-' + job.status"
          >
            <div class="panel-heading">
              <div>
                <h2>{{ job.name }}</h2>
                <p>
                  JOB-{{ pad(job.id) }} · {{ date(job.created_at) }} ·
                  {{ job.total }}项检查
                </p>
              </div>
              <span :class="'status ' + job.status">{{
                jobStatusNames[job.status]
              }}</span>
            </div>
            <el-progress
              :percentage="job.progress"
              :status="
                job.status === 'succeeded'
                  ? 'success'
                  : job.status === 'failed'
                    ? 'exception'
                    : undefined
              "
              :stroke-width="7"
            />
            <div class="job-counts">
              <span>等待 {{ job.counts.queued }}</span
              ><span>执行 {{ job.counts.running }}</span
              ><span>成功 {{ job.counts.succeeded }}</span
              ><span>失败 {{ job.counts.failed }}</span
              ><el-button
                class="action-retry"
                v-if="canAnalyze && job.counts.failed"
                text
                type="primary"
                @click="retryJob(job.id)"
                >重试失败项</el-button
              >
            </div>
            <p class="muted">进度包含成功与失败项，100% 表示处理完毕；请同时查看失败数量。</p><el-checkbox v-model="failedJobs[job.id]">只看失败项</el-checkbox>
            <el-collapse
              ><el-collapse-item title="查看任务明细" :name="job.id"
                ><el-table :data="failedJobs[job.id] ? job.items.filter((i:any)=>i.status==='failed') : job.items"
                  ><el-table-column label="检查" width="140"
                    ><template #default="{ row }"
                      ><el-button text @click="openStudy(row.study_id)"
                        >ECG-{{ pad(row.study_id) }}</el-button
                      ></template
                    ></el-table-column
                  ><el-table-column label="状态" width="120"
                    ><template #default="{ row }">{{
                      jobStatusNames[row.status]
                    }}</template></el-table-column
                  ><el-table-column
                    prop="attempts"
                    label="执行次数"
                    width="110" /><el-table-column
                    prop="error"
                    label="异常说明" /></el-table></el-collapse-item
            ></el-collapse>
          </section>
          <section v-if="!jobList.length" class="panel">
            <el-empty description="暂无批量任务"
              ><el-button @click="go('studies')"
                >前往检查记录创建</el-button
              ></el-empty
            >
          </section>
        </template>

        <template v-else-if="page === 'models'">
          <div class="page-heading">
            <div>
              <div class="eyebrow">MODEL REGISTRY</div>
              <h1>模型与运行状态</h1>
              <p>固定模型、预处理和验证阈值，让每次分析都可追溯。</p>
            </div>
            <div class="model-refresh-controls">
              <span
                v-if="modelsCheckedAt"
                class="last-check-note"
                data-testid="model-last-checked"
              >
                最近检查 {{ modelsCheckedAt }}
              </span>
              <el-button
                :loading="refreshingModels"
                @click="refreshModels"
                data-testid="model-refresh"
              >
                <el-icon v-if="!refreshingModels"><Refresh /></el-icon>
                {{ refreshingModels ? "正在检查…" : "刷新状态" }}
              </el-button>
            </div>
          </div>
          <AgentStatus />
          <div class="model-grid">
            <section
              v-for="model in modelList"
              :key="model.kind"
              class="panel model-card"
              :class="'model-' + model.kind"
            >
              <div class="panel-heading">
                <div class="entry-icon">
                  <el-icon
                    ><component
                      :is="model.kind === 'signal' ? SignalIcon : ReportIcon"
                  /></el-icon>
                </div>
                <span :class="['status', model.loaded ? 'loaded' : 'failed']">{{
                  model.loaded ? "已加载" : "未就绪"
                }}</span>
              </div>
              <h2>
                {{
                  model.kind === "signal"
                    ? "ResNet1D 信号模型"
                    : "EfficientNet-B0 报告图模型"
                }}
              </h2>
              <p class="muted">{{ model.version }}</p>
              <el-descriptions :column="1" border
                ><el-descriptions-item label="运行设备"
                  >CPU ·
                  {{ health.version ? "本地服务" : "" }}</el-descriptions-item
                ><el-descriptions-item label="输入形状">{{
                  model.input_shape.join(" × ")
                }}</el-descriptions-item
                ><el-descriptions-item label="处理协议">{{
                  model.preprocessing
                }}</el-descriptions-item></el-descriptions
              >
              <h3>固定分类阈值</h3>
              <div class="thresholds">
                <span v-for="(c, i) in model.classes" :key="c"
                  >{{ c }}
                  <strong>{{ model.thresholds[i].toFixed(2) }}</strong></span
                >
              </div>
              <details>
                <summary>模型文件SHA-256</summary>
                <code class="hash">{{ model.sha256 }}</code>
              </details>
              <el-alert
                v-if="model.error"
                :title="model.error"
                type="error"
                :closable="false"
              />
            </section>
          </div>
        </template>

        <template v-else-if="page === 'admin' && user.role === 'admin'">
          <div class="page-heading">
            <div>
              <div class="eyebrow">ADMINISTRATION</div>
              <h1>系统管理</h1>
              <p>维护专业人员账号与权限，查看业务操作记录。</p>
            </div>
            <el-button type="primary" @click="userDialog = true"
              ><el-icon><Plus /></el-icon> 新建账号</el-button
            >
          </div>
          <section class="panel">
            <el-tabs v-model="adminTab"
              ><el-tab-pane label="账号与角色" name="users"
                ><el-table :data="userList" class="record-table" stripe
                  ><el-table-column
                    prop="username"
                    label="账号"
                  /><el-table-column
                    prop="name"
                    label="显示姓名"
                  /><el-table-column label="角色" min-width="180"
                    ><template #default="{ row }"
                      ><el-select
                        class="account-role-select"
                        :model-value="row.role"
                        :disabled="row.id === user.id"
                        @change="(role: string) => updateRole(row, role)"
                        ><el-option
                          v-for="(v, k) in roleNames"
                          :key="k"
                          :value="k"
                          :label="v" /></el-select></template></el-table-column
                  ><el-table-column label="状态"
                    ><template #default="{ row }"
                      ><span
                        :class="['status', row.active ? 'enabled' : 'disabled']"
                        >{{ row.active ? "启用" : "停用" }}</span
                      ></template
                    ></el-table-column
                  ><el-table-column label="操作"
                    ><template #default="{ row }"
                      ><el-button
                        :class="row.active ? 'action-edit' : 'action-review'"
                        text
                        :disabled="row.id === user.id"
                        @click="toggleUser(row)"
                        >{{ row.active ? "停用" : "启用" }}</el-button
                      ></template
                    ></el-table-column
                  ></el-table
                ></el-tab-pane
              ><el-tab-pane label="操作日志" name="audit"
                ><div class="toolbar"><el-input v-model="auditSearch" clearable placeholder="搜索操作、对象或人员ID" @keyup.enter="auditPage=1;loadAdmin()" @clear="auditPage=1;loadAdmin()" /><el-button @click="auditPage=1;loadAdmin()">查询日志</el-button></div><el-table :data="auditData.items" class="record-table" stripe
                  ><el-table-column
                    prop="id"
                    label="编号"
                    width="80"
                  /><el-table-column
                    prop="actor_id"
                    label="操作人员ID"
                    width="120"
                  /><el-table-column
                    prop="action"
                    label="操作"
                  /><el-table-column
                    prop="target"
                    label="对象"
                  /><el-table-column label="时间"
                    ><template #default="{ row }">{{
                      date(row.created_at)
                    }}</template></el-table-column
                  ></el-table
                ><el-pagination
                  class="pagination"
                  layout="prev, pager, next"
                  :page-size="50"
                  :total="auditData.total"
                  v-model:current-page="auditPage"
                  @current-change="loadAdmin" /></el-tab-pane
            ></el-tabs>
          </section>
        </template>
      </main>
    </div>

    <el-dialog
      v-model="patientDialog"
      :title="patientForm.id ? '编辑受检者档案' : '新建受检者档案'"
      width="520px"
      :close-on-click-modal="false"
      ><el-form label-position="top" @submit.prevent="savePatient"
        ><div class="two-fields">
          <el-form-item label="档案编号"
            ><el-input
              v-model="patientForm.code"
              placeholder="例如：P-2026001"
              maxlength="64" /></el-form-item
          ><el-form-item label="姓名／演示名称"
            ><el-input v-model="patientForm.name" maxlength="80"
          /></el-form-item>
        </div>
        <div class="two-fields">
          <el-form-item label="性别"
            ><el-select v-model="patientForm.sex"
              ><el-option
                v-for="(v, k) in sexNames"
                :label="v"
                :value="k"
                :key="k" /></el-select></el-form-item
          ><el-form-item label="年龄"
            ><el-input-number v-model="patientForm.age" :min="0" :max="130"
          /></el-form-item>
        </div>
        <el-form-item label="备注"
          ><el-input
            type="textarea"
            v-model="patientForm.note"
            maxlength="2000"
            :rows="3"
        /></el-form-item>
        <p class="muted">基础资料用于业务管理，不进入当前模型计算。</p></el-form
      ><template #footer
        ><el-button @click="patientDialog = false">取消</el-button
        ><el-button type="primary" :loading="busy" @click="savePatient"
          >保存档案</el-button
        ></template
      ></el-dialog
    >
    <el-dialog v-model="studyDialog" title="新建检查" width="500px"
      ><el-form label-position="top"
        ><el-form-item label="受检者档案"
          ><el-select v-model="studyForm.patient_id" filterable class="full"
            ><el-option
              v-for="p in patientOptions"
              :key="p.id"
              :label="`${p.name} · ${p.code}`"
              :value="p.id" /></el-select></el-form-item
        ><el-form-item label="检查名称"
          ><el-input
            v-model="studyForm.title"
            placeholder="常规静息心电检查" /></el-form-item
        ><el-form-item label="输入方式"
          ><el-radio-group v-model="studyForm.kind"
            ><el-radio-button value="signal">数字信号</el-radio-button
            ><el-radio-button value="image"
              >标准报告图</el-radio-button
            ></el-radio-group
          ></el-form-item
        ></el-form
      ><template #footer
        ><el-button @click="studyDialog = false">取消</el-button
        ><el-button type="primary" @click="createEmptyStudy" :loading="busy"
          >创建并上传数据</el-button
        ></template
      ></el-dialog
    >
    <el-drawer v-model="patientDrawer" title="受检者档案与检查历史" size="min(650px,100vw)">
      <template v-if="patientProfile"><h2>{{patientProfile.name}}</h2><p>{{patientProfile.code}} · {{sexNames[patientProfile.sex]}} · {{patientProfile.age ?? '年龄未填写'}}</p><p>{{patientProfile.note || '暂无备注'}}</p><el-divider />
      <h3>最近十次检查</h3><el-table :data="patientHistory"><el-table-column prop="title" label="检查"/><el-table-column label="状态"><template #default="{row}">{{statusNames[row.status]}}</template></el-table-column><el-table-column label="日期"><template #default="{row}">{{date(row.created_at)}}</template></el-table-column><el-table-column label="详情"><template #default="{row}"><el-button text @click="openStudy(row.id)">查看</el-button></template></el-table-column></el-table><el-button @click="patientDrawer=false;viewPatientStudies(patientProfile)">查看全部检查</el-button></template>
    </el-drawer>
    <el-drawer
      v-model="detailDrawer"
      title="检查详情"
      size="min(850px, 100vw)"
      @closed="clearDetail"
    >
      <div
        v-if="detail"
        class="study-detail-content"
        :class="'detail-kind-' + detail.kind"
      >
        <div v-if="canReview" class="toolbar wrap">
          <el-button :disabled="!reviewNeighbors.previous" @click="openStudy(reviewNeighbors.previous)">上一条待复核</el-button>
          <span>剩余 {{ reviewNeighbors.remaining || 0 }} 条待复核</span>
          <el-button :disabled="!reviewNeighbors.next" @click="openStudy(reviewNeighbors.next)">下一条待复核</el-button>
        </div>
        <section class="detail-card detail-info-card">
          <div class="detail-hero">
            <span :class="'status ' + detail.status">{{
              statusNames[detail.status]
            }}</span>
            <h2>{{ detail.title }}</h2><el-tag v-if="detail.metadata.source?.purpose==='public_sample'" type="info">PTB-XL 公开演示样本</el-tag>
            <p>
              {{ detail.patient_name }} · {{ detail.patient_code }} · ECG-{{
                pad(detail.id)
              }}
            </p>
          </div>
          <el-descriptions :column="detailColumns" border>
            <el-descriptions-item label="输入方式">{{
              kindName(detail.kind)
            }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{
              date(detail.created_at)
            }}</el-descriptions-item>
            <el-descriptions-item label="文件" :span="detailColumns">{{
              detail.metadata.files?.join("、") || "尚未上传"
            }}</el-descriptions-item>
          </el-descriptions>
        </section>

        <section
          v-if="detail.metadata.storage_key"
          class="detail-card detail-preview"
        >
          <div class="detail-section-heading">
            <h3>
              {{ detail.kind === "signal" ? "数字波形预览" : "报告图预览" }}
            </h3>
          </div>
          <div
            v-if="detail.kind === 'signal' && detailSignal"
            class="detail-lead-select"
          >
            <span>显示导联</span>
            <el-select
              v-model="detailLead"
              aria-label="选择预览导联"
              data-testid="detail-lead-select"
            >
              <el-option
                v-for="lead in detailSignal.leads"
                :key="lead"
                :label="lead"
                :value="lead"
              />
            </el-select>
            <span class="detail-lead-note">共12导联，可切换预览</span>
          </div>
          <div class="detail-preview-content">
            <SignalChart
              v-if="detail.kind === 'signal' && detailSignal"
              :data="detailSignal"
              :selected="[detailLead]"
            />
            <el-image
              v-if="detailImage"
              :src="detailImage"
              :preview-src-list="[detailImage]"
              fit="contain"
              class="report-preview"
            />
          </div>
        </section>

        <el-alert
          v-if="detail.error"
          :title="detail.error"
          type="error"
          :closable="false"
        />
        <div class="result-actions detail-toolbar">
          <el-button
            v-if="canAnalyze && ['ready', 'failed'].includes(detail.status)"
            type="primary"
            :loading="analyzing"
            @click="analyzeDetail"
            >运行分析</el-button
          >
          <el-button
            v-if="canAnalyze && detail.status === 'awaiting_upload'"
            @click="continueUpload"
            >前往上传</el-button
          >
          <el-button @click="openStudy(detail.id)">刷新状态</el-button>
        </div>

        <section
          v-for="a in detail.analyses"
          :key="a.id"
          class="detail-card detail-analysis"
        >
          <div class="section-heading">
            <h3>分析记录 #{{ a.id }}</h3>
            <span>{{ date(a.created_at) }}</span>
          </div>
          <el-table :data="a.predictions" class="analysis-table" stripe>
            <el-table-column
              prop="code"
              label="类别"
              width="90"
              align="center"
              header-align="center"
            />
            <el-table-column
              prop="name"
              label="名称"
              min-width="160"
              align="center"
              header-align="center"
            />
            <el-table-column
              label="概率"
              width="110"
              align="center"
              header-align="center"
            >
              <template #default="{ row }"
                >{{ (row.probability * 100).toFixed(2) }}%</template
              >
            </el-table-column>
            <el-table-column
              label="阈值"
              width="90"
              align="center"
              header-align="center"
            >
              <template #default="{ row }">{{
                row.threshold.toFixed(2)
              }}</template>
            </el-table-column>
            <el-table-column
              label="判定"
              width="100"
              align="center"
              header-align="center"
            >
              <template #default="{ row }">
                <span
                  :class="['prediction-label', { positive: row.positive }]"
                  >{{ row.positive ? "阳性" : "阴性" }}</span
                >
              </template>
            </el-table-column>
          </el-table>
          <p class="muted analysis-meta">
            {{ a.model_version }} · 推理
            {{ a.timings.inference_ms.toFixed(2) }} ms · 服务
            {{ a.timings.service_ms.toFixed(2) }} ms
          </p>
          <div v-if="a.review" class="review-note">
            <strong
              >复核意见 · {{ a.review.reviewer }} ·
              {{ date(a.review.created_at) }}</strong
            >
            <p>{{ a.review.comment }}</p>
          </div>
          <div v-else class="detail-review-pending">
            <strong>专业复核</strong>
            <p>等待专业人员填写复核意见。</p>
          </div>
          <el-collapse
            v-if="a.review_history?.length > 1"
            class="detail-review-history"
          >
            <el-collapse-item title="查看全部复核记录">
              <div
                v-for="(r, i) in a.review_history"
                :key="i"
                class="review-note"
              >
                <strong>{{ r.reviewer }} · {{ date(r.created_at) }}</strong>
                <p>{{ r.comment }}</p>
              </div>
            </el-collapse-item>
          </el-collapse>
          <div class="result-actions">
            <el-button class="action-export" @click="downloadReport(a.id)"
              >导出分析报告</el-button
            >
            <el-button
              class="action-review"
              v-if="canReview && a.id === detail.analyses[0].id"
              type="primary"
              plain
              @click="showReview(a)"
              >{{ a.review ? "补充复核意见" : "填写复核意见" }}</el-button
            >
          </div>
        </section>
      </div>
    </el-drawer>
    <el-dialog v-model="reviewDialog" title="专业复核与归档" width="560px"
      ><el-alert
        title="请结合原始数据与模型预测独立复核。意见将作为新记录保存，不覆盖模型输出。"
        type="info"
        :closable="false"
      /><el-form label-position="top" class="space-top"
        ><el-form-item label="处理结论"
          ><el-radio-group v-model="reviewForm.conclusion"
            ><el-radio value="confirmed">已复核</el-radio
            ><el-radio value="needs_attention"
              >已复核，需进一步关注</el-radio
            ></el-radio-group
          ></el-form-item
        ><el-form-item label="复核意见"
          ><el-input
            type="textarea"
            v-model="reviewForm.comment"
            :rows="5"
            minlength="5"
            maxlength="5000"
            placeholder="填写复核意见，至少5个字符"
            data-testid="review-comment" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="reviewDialog = false">取消</el-button
        ><el-button
          class="action-review"
          type="primary"
          @click="saveReview(false)"
          :loading="busy"
          data-testid="review-submit"
          >保存并归档</el-button
        ><el-button v-if="detail && (reviewNeighbors.next || reviewNeighbors.previous)" @click="saveReview(true)" :loading="busy">归档并继续复核</el-button></template
      ></el-dialog
    >
    <el-dialog v-model="userDialog" title="新建专业人员账号" width="480px"
      ><el-form label-position="top"
        ><el-form-item label="账号"
          ><el-input
            v-model="newUser.username"
            placeholder="至少3位字母、数字或下划线" /></el-form-item
        ><el-form-item label="显示姓名"
          ><el-input v-model="newUser.name" /></el-form-item
        ><el-form-item label="初始密码"
          ><el-input
            v-model="newUser.password"
            type="password"
            show-password
            placeholder="至少12个字符" /></el-form-item
        ><el-form-item label="角色"
          ><el-select v-model="newUser.role"
            ><el-option
              v-for="(v, k) in roleNames"
              :key="k"
              :value="k"
              :label="v" /></el-select></el-form-item></el-form
      ><template #footer
        ><el-button @click="userDialog = false">取消</el-button
        ><el-button type="primary" @click="createUser" :loading="busy"
          >创建账号</el-button
        ></template
      ></el-dialog
    >
    <el-dialog v-model="passwordDialog" title="修改登录密码" width="460px"
      ><el-form label-position="top"
        ><el-form-item label="当前密码"
          ><el-input
            v-model="passwordForm.current_password"
            type="password"
            show-password /></el-form-item
        ><el-form-item label="新密码"
          ><el-input
            v-model="passwordForm.new_password"
            type="password"
            show-password
            placeholder="至少12个字符" /></el-form-item></el-form
      ><template #footer
        ><el-button type="primary" @click="changePassword" :loading="busy"
          >更新密码</el-button
        ></template
      ></el-dialog
    >
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowRight,
  ArrowDown,
  TopRight,
  Document,
  DocumentAdd,
  Files,
  User as UserIcon,
  Grid,
  Checked,
  List,
  Setting,
  Cpu,
  Plus,
  Search,
  Download,
  Refresh,
  UploadFilled,
  CircleCheckFilled,
  InfoFilled,
  Menu,
} from "@element-plus/icons-vue";
import { api, get, post, download } from "./api";
import SignalChart from "./components/SignalChart.vue";
import SignalIcon from "./components/SignalIcon.vue";
import ReportIcon from "./components/ReportIcon.vue";
import UploadGuide from "./components/UploadGuide.vue";
import AgentStatus from "./components/AgentStatus.vue";
import AgentChat from "./components/AgentChat.vue";
import DashboardOverview from "./components/DashboardOverview.vue";

const detailViewport = window.matchMedia("(max-width: 700px)");
const detailColumns = ref(detailViewport.matches ? 1 : 2);
const updateDetailColumns = () => {
  detailColumns.value = detailViewport.matches ? 1 : 2;
};
onMounted(() => detailViewport.addEventListener("change", updateDetailColumns));
onBeforeUnmount(() =>
  detailViewport.removeEventListener("change", updateDetailColumns),
);
const route = useRoute(),
  router = useRouter();
const page = computed(() => String(route.name || "dashboard"));
const user = ref<any>(null),
  booting = ref(true),
  loading = ref(false),
  busy = ref(false),
  analyzing = ref(false),
  mobileNav = ref(false);
const canAnalyze = computed(() =>
    ["analyst", "admin"].includes(user.value?.role),
  ),
  canReview = computed(() => ["reviewer", "admin"].includes(user.value?.role));
const roleNames: Record<string, string> = {
  admin: "系统管理员",
  analyst: "检查／分析人员",
  reviewer: "专业复核人员",
};
const sexNames: Record<string, string> = {
  male: "男",
  female: "女",
  unknown: "未记录",
};
const statusNames: Record<string, string> = {
  awaiting_upload: "待上传",
  ready: "已校验",
  queued: "排队中",
  processing: "分析中",
  awaiting_review: "待复核",
  archived: "已归档",
  failed: "分析失败",
};
const jobStatusNames: Record<string, string> = {
  queued: "排队中",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  partial: "部分完成",
};
const leads = [
  "I",
  "II",
  "III",
  "aVR",
  "aVL",
  "aVF",
  "V1",
  "V2",
  "V3",
  "V4",
  "V5",
  "V6",
];
const allNav = [
  { key: "dashboard", label: "工作概览", icon: Grid },
  { key: "patients", label: "受检者档案", icon: UserIcon },
  { key: "signal", label: "数字信号分析", icon: SignalIcon },
  { key: "image", label: "报告图分析", icon: ReportIcon },
  { key: "studies", label: "检查记录", icon: Files },
  { key: "review", label: "复核中心", icon: Checked },
  { key: "jobs", label: "批量任务", icon: List },
  { key: "agent", label: "心电工作助手", icon: Cpu },
  { key: "models", label: "模型与状态", icon: Cpu },
  { key: "admin", label: "系统管理", icon: Setting },
];
const navItems = computed(() =>
  allNav.filter(
    (n) =>
      (n.key !== "admin" || user.value?.role === "admin") &&
      (n.key !== "review" || canReview.value),
  ),
);
const pageTitle = computed(
  () => allNav.find((n) => n.key === page.value)?.label || "工作概览",
);
const today = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "short",
}).format(new Date());
const dashboard = ref<any>({ counts: {}, recent: [] }),
  health = ref<any>({}),
  patients = ref<any>({ items: [], total: 0 }),
  studies = ref<any>({ items: [], total: 0 });
const patientOptions = ref<any[]>([]),
  jobList = ref<any[]>([]),
  modelList = ref<any[]>([]),
  userList = ref<any[]>([]),
  auditData = ref<any>({ items: [], total: 0 });
const refreshingModels = ref(false),
  refreshingJobs = ref(false),
  modelsCheckedAt = ref("");
const dateRange = ref<[Date, Date] | null>(null);
const search = ref(""),
  filterKind = ref(""),
  filterStatus = ref(""),
  patientFilter = ref<number | null>(null),
  listPage = ref(1),
  auditPage = ref(1),
  adminTab = ref("users"),
  selectedStudies = ref<any[]>([]);
const patientProfile=ref<any>(null);const patientHistory=ref<any[]>([]);const patientDrawer=ref(false);
const reviewNeighbors = ref<any>({});
const sortedPredictions = (items:any[]) => [...items].sort((a,b)=>Number(b.positive)-Number(a.positive));
const capsLock = ref(false);
const auditSearch = ref("");
const filterSource = ref("");
const failedJobs=reactive<Record<number,boolean>>({});
const loginForm = reactive({ username: "", password: "" }),
  patientDialog = ref(false),
  studyDialog = ref(false),
  userDialog = ref(false),
  passwordDialog = ref(false);
const patientForm = reactive<any>({
  id: null,
  code: "",
  name: "",
  sex: "unknown",
  age: null,
  note: "",
});
const studyForm = reactive<any>({
  patient_id: null,
  title: "常规静息心电检查",
  kind: "signal",
  note: "",
});
const newUser = reactive({
    username: "",
    name: "",
    password: "",
    role: "analyst",
  }),
  passwordForm = reactive({ current_password: "", new_password: "" });
const selectedFiles = ref<File[]>([]),
  fileInput = ref<HTMLInputElement>(),
  inputProfile = ref("filtered_mv"),
  samplingRate = ref(100),
  inputUnit = ref("mV"),
  selectedLeads = ref(["II", "V1", "V5"]);
const activeStudy = ref<any>(null),
  signalPreview = ref<any>(null),
  imagePreview = ref(""),
  latestAnalysis = ref<any>(null),
  displayMs = ref(0),
  draftId = ref<number | null>(null);
const detailDrawer = ref(false),
  detail = ref<any>(null),
  detailSignal = ref<any>(null),
  detailLead = ref("II"),
  detailImage = ref(""),
  reviewDialog = ref(false),
  reviewId = ref(0),
  reviewForm = reactive({ conclusion: "confirmed", comment: "" });
let polling: ReturnType<typeof setInterval> | undefined;
function date(v: string) {
  return v
    ? new Date(v).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";
}
function pad(n: number) {
  return String(n).padStart(5, "0");
}
function kindName(k: string) {
  return k === "signal" ? "数字信号" : "标准报告图";
}
function go(key: string, query: Record<string, string> = {}) {
  mobileNav.value = false;
  router.push({ path: "/" + key, query });
}
function openDocs() {
  window.open("/docs", "_blank", "noopener");
}
async function guarded(fn: () => Promise<void>) {
  busy.value = true;
  try {
    await fn();
  } catch {
  } finally {
    busy.value = false;
  }
}
async function login() {
  await guarded(async () => {
    const r = await post("/auth/login", loginForm);
    sessionStorage.setItem("ecg-token", r.access_token);
    user.value = r.user;
    loginForm.password = "";
    await loadPage();
  });
}
function logout() {
  sessionStorage.removeItem("ecg-token");
  user.value = null;
  clearDetail();
  resetWorkspace();
}
async function loadPatients() {
  patients.value = await get("/patients", {
    q: search.value,
    page: listPage.value,
  });
}
async function loadPatientOptions() {
  let all: any[] = [];
  let p = 1;
  while (p <= 100) {
    const result = await get("/patients", { page: p, page_size: 100 });
    all.push(...result.items);
    if (all.length >= result.total) break;
    p++;
  }
  patientOptions.value = all;
}
function restoreFilters() {
  const q = route.query;
  search.value = String(q.q || ""); filterKind.value = String(q.kind || "");
  filterStatus.value = String(q.status || "");filterSource.value=String(q.source || ""); patientFilter.value = Number(q.patient_id) || null;
  listPage.value = Math.max(1, Number(q.page) || 1);
  dateRange.value = q.from && q.to ? [new Date(String(q.from)), new Date(String(q.to))] : null;
}
async function resetFilters() {
 search.value="";filterSource.value="";filterKind.value="";filterStatus.value="";patientFilter.value=null;dateRange.value=null;listPage.value=1;
 await loadStudies();
}
async function loadStudies() {
  const query: Record<string,string> = {};
  if(filterSource.value)query.source=filterSource.value;
  if(search.value) query.q=search.value; if(filterKind.value) query.kind=filterKind.value;
  if(filterStatus.value) query.status=filterStatus.value; if(patientFilter.value) query.patient_id=String(patientFilter.value);
  if(dateRange.value){query.from=dateRange.value[0].toISOString();query.to=dateRange.value[1].toISOString();}
  if(listPage.value>1)query.page=String(listPage.value);
  if(["studies","review"].includes(page.value)) await router.replace({query});
  studies.value = await get("/studies", {
    q: search.value,
    source: filterSource.value,
    kind: filterKind.value,
    status: page.value === "review" ? "awaiting_review" : filterStatus.value,
    patient_id: patientFilter.value || undefined,
    date_from: dateRange.value?.[0].toISOString(),
    date_to: dateRange.value
      ? new Date(dateRange.value[1].getTime() + 86400000 - 1).toISOString()
      : undefined,
    page: listPage.value,
  });
}
async function loadJobs() {
  jobList.value = await get("/jobs");
}
async function refreshJobs() {
  if (refreshingJobs.value) return;
  refreshingJobs.value = true;
  try {
    await loadJobs();
    ElMessage.success("任务进度已更新");
  } catch {
    // The shared API interceptor displays the concrete request error.
  } finally {
    refreshingJobs.value = false;
  }
}
async function loadModels() {
  modelList.value = await get("/models");
  modelsCheckedAt.value = new Date().toLocaleTimeString("zh-CN", {
    hour12: false,
  });
}
async function refreshModels() {
  if (refreshingModels.value) return;
  refreshingModels.value = true;
  try {
    const [models, response] = await Promise.all([
      get("/models"),
      api.get("/health", {
        validateStatus: (status) => status === 200 || status === 503,
      }),
    ]);
    modelList.value = models;
    health.value = response.data.result;
    modelsCheckedAt.value = new Date().toLocaleTimeString("zh-CN", {
      hour12: false,
    });
    const count = models.filter((model: any) => model.loaded).length;
    if (health.value.ready) {
      ElMessage.success(`状态检查完成：${count}/${models.length} 个模型已就绪`);
    } else {
      ElMessage.warning(
        `状态已更新：${count}/${models.length} 个模型已加载，服务未完全就绪，请检查模型或数据库。`,
      );
    }
  } catch {
    // Keep the last successful status/time; the API interceptor reports failure.
  } finally {
    refreshingModels.value = false;
  }
}
async function loadAdmin() {
  if (user.value?.role === "admin") {
    [userList.value, auditData.value] = await Promise.all([
      get("/users"),
      get("/audit", { page: auditPage.value, q: auditSearch.value }),
    ]);
  }
}
async function loadPage() {
  if (!user.value) return;
  loading.value = true;
  try {
    [dashboard.value, health.value] = await Promise.all([
      get("/dashboard"),
      get("/health").catch(() => ({ ready: false })),
    ]);
    if (page.value === "patients") await loadPatients();
    if (["signal", "image"].includes(page.value)) await loadPatientOptions();
    if (["studies", "review"].includes(page.value)) await loadStudies();
    if (page.value === "jobs") await loadJobs();
    if (page.value === "models") await loadModels();
    if (page.value === "admin") await loadAdmin();
  } catch {
  } finally {
    loading.value = false;
  }
}
function editPatient(row?: any) {
  Object.assign(
    patientForm,
    row
      ? { ...row }
      : { id: null, code: "", name: "", sex: "unknown", age: null, note: "" },
  );
  patientDialog.value = true;
}
async function savePatient() {
  if (!patientForm.name.trim() || !patientForm.code.trim()) {
    ElMessage.warning("请填写姓名和档案编号");
    return;
  }
  await guarded(async () => {
    const { id, ...body } = patientForm;
    if (id) await api.put(`/patients/${id}`, body);
    else await post("/patients", body);
    patientDialog.value = false;
    ElMessage.success("档案已保存");
    await loadPatients();
  });
}
async function removePatient(row: any) {
  try {
    await ElMessageBox.confirm(
      "仅能删除没有关联检查的档案，确认删除？",
      "删除档案",
      { type: "warning" },
    );
    await api.delete(`/patients/${row.id}`);
    await loadPatients();
  } catch {}
}
async function viewPatient(row:any){
 patientProfile.value=row;const r=await get('/studies',{patient_id:row.id,page_size:10});patientHistory.value=r.items;patientDrawer.value=true;
}
function viewPatientStudies(row: any) {
  go("studies", {patient_id:String(row.id)});
}
async function createEmptyStudy() {
  if (!studyForm.patient_id || !studyForm.title.trim()) {
    ElMessage.warning("请选择档案并填写检查名称");
    return;
  }
  await guarded(async () => {
    const r = await post("/studies", studyForm);
    studyDialog.value = false;
    resetWorkspace();
    draftId.value = r.id;
    go(studyForm.kind);
    ElMessage.success("检查已建立，请选择文件上传");
  });
}
function filesChanged(e: Event) {
  selectedFiles.value = Array.from((e.target as HTMLInputElement).files || []);
}
function resetWorkspace() {
  activeStudy.value = null;
  latestAnalysis.value = null;
  signalPreview.value = null;
  displayMs.value = 0;
  draftId.value = null;
  selectedFiles.value = [];
  if (fileInput.value) fileInput.value.value = "";
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value);
  imagePreview.value = "";
}
async function previewFor(study: any) {
  if (study.kind === "signal") return get(`/studies/${study.id}/preview`);
  const r = await api.get(`/studies/${study.id}/preview`, {
    responseType: "blob",
  });
  return URL.createObjectURL(r.data);
}
async function submitInput() {
  if (!studyForm.patient_id || !studyForm.title.trim()) {
    ElMessage.warning("请选择档案并填写检查名称");
    return;
  }
  if (selectedFiles.value.reduce((a, f) => a + f.size, 0) > 16 * 1024 * 1024) {
    ElMessage.warning("上传总大小不能超过16 MB");
    return;
  }
  await guarded(async () => {
    if (!draftId.value) {
      const r = await post("/studies", { ...studyForm, kind: page.value });
      draftId.value = r.id;
    }
    const form = new FormData();
    selectedFiles.value.forEach((f) => form.append("files", f));
    form.append("profile", inputProfile.value);
    form.append("sampling_rate", String(samplingRate.value));
    form.append("unit", inputUnit.value);
    const r = await post(`/studies/${draftId.value}/assets`, form);
    activeStudy.value = r;
    const p = await previewFor(r);
    if (r.kind === "signal") signalPreview.value = p;
    else imagePreview.value = p;
    ElMessage.success("数据校验通过");
  });
}
async function runAnalysis() {
  if (!activeStudy.value) return;
  analyzing.value = true;
  const start = performance.now();
  try {
    latestAnalysis.value = await post(
      `/studies/${activeStudy.value.id}/analyses`,
    );
    activeStudy.value.status = "awaiting_review";
    await nextTick();
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    displayMs.value = performance.now() - start;
    window.dispatchEvent(
      new CustomEvent("ecg-analysis-rendered", {
        detail: { studyId: activeStudy.value.id, displayMs: displayMs.value },
      }),
    );
  } catch {
    try {
      activeStudy.value = await get(`/studies/${activeStudy.value.id}`);
    } catch {}
  } finally {
    analyzing.value = false;
  }
}
async function openStudy(id: number) {
  try {
    const study = await get(`/studies/${id}`);
    if (detail.value?.id !== id) detailLead.value = "II";
    detail.value = study;
    reviewNeighbors.value = canReview.value ? await get(`/studies/${id}/review-neighbors`) : {};
    clearDetailPreview();
    if (detail.value.metadata.storage_key) {
      const p = await previewFor(detail.value);
      if (detail.value.kind === "signal") {
        detailSignal.value = p;
        if (!p.leads.includes(detailLead.value)) detailLead.value = p.leads[0];
      }
      else detailImage.value = p;
    }
    detailDrawer.value = true;
  } catch {}
}
function clearDetailPreview() {
  detailSignal.value = null;
  if (detailImage.value) URL.revokeObjectURL(detailImage.value);
  detailImage.value = "";
}
function clearDetail() {
  clearDetailPreview();
  detailLead.value = "II";
  detail.value = null;
}
function continueUpload() {
  const s = detail.value;
  detailDrawer.value = false;
  resetWorkspace();
  Object.assign(studyForm, {
    patient_id: s.patient_id,
    title: s.title,
    kind: s.kind,
    note: s.note,
  });
  draftId.value = s.id;
  go(s.kind);
}
async function analyzeDetail() {
  analyzing.value = true;
  try {
    await post(`/studies/${detail.value.id}/analyses`);
    await openStudy(detail.value.id);
    await loadPage();
  } catch {
  } finally {
    analyzing.value = false;
  }
}
function showReview(a: any) {
  reviewId.value = a.id;
  reviewForm.comment = "";
  reviewForm.conclusion = "confirmed";
  reviewDialog.value = true;
}
async function saveReview(continueNext = false) {
  if (reviewForm.comment.trim().length < 5) {
    ElMessage.warning("复核意见至少5个字符");
    return;
  }
  await guarded(async () => {
    const nextId = reviewNeighbors.value.next || reviewNeighbors.value.previous;
    const a = await post(`/analyses/${reviewId.value}/reviews`, reviewForm);
    reviewDialog.value = false;
    if (latestAnalysis.value?.id === a.id) latestAnalysis.value = a;
    if (detail.value) await openStudy(detail.value.id);
    await loadPage();
    ElMessage.success("复核意见已保存并归档");
    if(continueNext && nextId) await openStudy(nextId);
  });
}
async function downloadReport(id: number) {
  await download(`/analyses/${id}/report`, `心电分析报告-${id}.html`);
}
async function queueSelected() {
  try {
    const { value } = await ElMessageBox.prompt(
      "为本次批量分析填写名称",
      "创建批量任务",
      {
        inputValue: `批量分析 ${date(new Date().toISOString())}`,
        inputValidator: (v: string) => !!v.trim() || "请输入名称",
      },
    );
    await post("/jobs", {
      name: value,
      study_ids: selectedStudies.value.map((s) => s.id),
    });
    selectedStudies.value = [];
    go("jobs");
  } catch {}
}
async function retryJob(id: number) {
  await guarded(async () => {
    await post(`/jobs/${id}/retries`);
    await loadJobs();
  });
}
async function importSamples() {
  await guarded(async () => {
    await post("/samples/import");
    await loadPage();
    ElMessage.success("演示档案和两种输入检查已导入，可在检查记录中分析");
  });
}
async function createUser() {
  await guarded(async () => {
    await post("/users", newUser);
    userDialog.value = false;
    newUser.password = "";
    await loadAdmin();
    ElMessage.success("账号已创建");
  });
}
async function updateRole(row: any, role: string) {
  try { await ElMessageBox.confirm(`将 ${row.name}（${row.username}）的角色改为 ${roleNames[role]}？`, "确认权限变更", {type:"warning"}); }
  catch {await loadAdmin();return;}
  await guarded(async () => {
    await api.patch(`/users/${row.id}`, { role });
    await loadAdmin();
    ElMessage.success("角色已更新");
  });
}
async function toggleUser(row: any) {
  try {await ElMessageBox.confirm(`${row.active ? "停用后该账号将无法继续操作。确认停用" : "确认启用"} ${row.name}（${row.username}）？`, "确认账号状态", {type:"warning"});}catch{return;}
  await guarded(async () => {
    await api.patch(`/users/${row.id}`, { active: !row.active });
    ElMessage.success(row.active ? "账号已停用" : "账号已启用");
    await loadAdmin();
  });
}
async function changePassword() {
  await guarded(async () => {
    await post("/auth/password", passwordForm);
    passwordDialog.value = false;
    passwordForm.current_password = "";
    passwordForm.new_password = "";
    ElMessage.success("密码已修改");
  });
}
watch(page, async (n, o) => {
  restoreFilters();
  selectedStudies.value = [];
  if (["signal", "image"].includes(o) && n !== o && activeStudy.value)
    resetWorkspace();
  await loadPage();
});
watch(() => route.query, async () => {
 if(["studies","review"].includes(page.value) && user.value){
   const current = JSON.stringify([search.value,filterKind.value,filterStatus.value,filterSource.value,patientFilter.value,listPage.value,dateRange.value]);
   restoreFilters();
   if(current !== JSON.stringify([search.value,filterKind.value,filterStatus.value,filterSource.value,patientFilter.value,listPage.value,dateRange.value])) await loadStudies();
 }
});
watch(studyDialog, async (v) => {
  if (v)
    try {
      await loadPatientOptions();
    } catch {}
});
onMounted(async () => {
  window.addEventListener("ecg-logout", logout);
  if (sessionStorage.getItem("ecg-token"))
    try {
      user.value = await get("/auth/me");
      restoreFilters();
      await loadPage();
    } catch {
      logout();
    }
  booting.value = false;
  polling = setInterval(async () => {
    if (user.value && page.value === "jobs")
      try {
        await loadJobs();
      } catch {}
  }, 3000);
});
onBeforeUnmount(() => {
  clearInterval(polling);
  window.removeEventListener("ecg-logout", logout);
  clearDetailPreview();
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value);
});
</script>
