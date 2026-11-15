# Cardio Workspace 心电检查与分析管理平台

面向检查、分析和复核人员的本地课程项目。提供数字心电信号与标准报告图两个独立入口，连接受检者档案、检查、真实模型推理、人工复核和报告归档。

## 功能与技术

- Vue 3 + TypeScript + Vite + Element Plus；Axios请求；ECharts交互波形。
- FastAPI + SQLAlchemy + Alembic + MySQL 8.0；Argon2密码哈希；JWT登录；三个业务角色。
- 信号：A3 Wang ResNet1D，第21轮最佳权重，PyTorch CPU。
- 图像：B2 EfficientNet-B0，第25轮最佳权重对应ONNX FP32，ONNX Runtime CPU。
- 独立Python Worker：MySQL持久任务表、事务领取、租约心跳、超时恢复、部分成功与失败重试。
- 模型、类别顺序、阈值、预处理和SHA-256成套交付；不连接任何外部AI问答API。

## 本地运行

### 1. 准备工具并克隆项目

已验证的环境为 **Windows x64、Python 3.13、Node.js 24 和 MySQL 8.0**。安装 Git 后接受仓库邀请，使用有仓库权限的 GitHub 账号克隆项目。可以用自己习惯的 IDE 打开项目，也可以直接在 Windows PowerShell 中运行。已有可连接的 MySQL 8.0 实例时可以直接使用。

在 PowerShell 终端中运行 `git --version`、`py -3.13 --version` 和 `node --version`，确认工具可用。首次安装依赖需要联网。安装脚本使用 Python 的 `py` 启动器。

将下面示例中的 `OWNER/REPO` 换成实际仓库地址。克隆后进入 Git 创建的项目目录。

```powershell
git clone https://github.com/OWNER/REPO.git
Set-Location REPO
```

### 2. 安装项目依赖

在项目根目录的 PowerShell 终端运行以下命令。根目录内应能看到 `scripts`、`backend` 和 `frontend`。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -DevDependencies
```

脚本会在本机创建 `.venv`，按锁文件安装 Python 库和前端依赖，再生成本地 `.env` 和初始管理员密码。首次配置或依赖版本变化时执行此步骤，日常启动直接运行第 4 步。

#### 可以放在项目目录里的依赖

| 内容 | 项目内的位置 | 准备方式 |
| --- | --- | --- |
| Python 库，例如 FastAPI、PyTorch、ONNX Runtime | `.venv/` | 安装脚本使用本机 Python 3.13 自动创建和安装。 |
| 前端库，例如 Vue、Vite | `frontend/node_modules/` | 安装脚本使用本机 Node.js 和 npm 自动安装。 |
| MySQL 8.0 服务端程序（可选） | `runtime/tools/mysql/` | 将 Windows x64 ZIP 版解压到这里，或使用已有的 MySQL 安装。 |

Git、Python 解释器和 Node.js 建议在电脑上配置一次，供多个项目共用。表中三个目录均被 Git 忽略，组员克隆后各自在本机准备。

### 3. 配置 MySQL

启动自己的 MySQL 服务，创建空的 `ecg_platform` 数据库并选择 `utf8mb4` 字符集。使用对该库有建表、迁移和读写权限的账号。修改项目根目录 `.env` 中的 `DATABASE_URL`，用自己的数据库账号、密码和实际端口替换示例值。

```dotenv
DATABASE_URL=mysql+pymysql://数据库账号:URL编码后的密码@127.0.0.1:3306/ecg_platform?charset=utf8mb4
```

`3306` 是示例端口。启动脚本会运行数据库迁移并创建初始管理员，数据库中已有应用账号时可以继续使用。每位组员在本地配置自己的 `.env`。

密码中的特殊字符须URL编码。可在本地使用以下交互命令，不把明文密码放入终端历史：

```powershell
.venv\Scripts\python.exe -c "import getpass,urllib.parse; print(urllib.parse.quote(getpass.getpass('Database password: '),safe=''))"
```

复制编码结果填入本地 `.env`，不要发到聊天或提交Git。

#### 可选的项目专用数据库

如果想把 MySQL 程序也放在项目里，完成第 2 步后，下载 MySQL 8.0 的 Windows x64 免安装 ZIP 版，解压到 `runtime/tools/mysql/`。确认解压后的文件路径是 `runtime/tools/mysql/bin/mysqld.exe`。首次配置时保留 `.env` 中的 `DATABASE_URL` 占位值，由脚本创建专用库和账号并更新连接配置。可跳过上面的手动建库步骤。[MySQL ZIP 版安装说明](https://dev.mysql.com/doc/refman/8.0/en/windows-install-archive.html)

```powershell
.venv\Scripts\python.exe scripts/project_mysql.py start --mysqld ".\runtime\tools\mysql\bin\mysqld.exe"
```

如果本机已有 MySQL 8.0 程序，也可以将命令中的路径换成现有 `mysqld.exe` 的路径。专用实例使用 `127.0.0.1:3307`，数据库文件单独保存在 `runtime/mysql/`，后续可由应用启动脚本自动启动。

清理时先按下方说明停止应用和专用数据库。删除 `.venv/` 或 `frontend/node_modules/` 后可重新运行第 2 步恢复。`runtime/tools/mysql/` 保存的是程序文件，`runtime/mysql/` 保存的是数据库数据。需要保留检查记录时，请保留 `runtime/mysql/` 和 `runtime/uploads/`，并备份本地 `.env` 和 `runtime/mysql-local-admin.json`，后者用于专用数据库的启停。

### 4. 启动并登录

完整构建模式，直接由FastAPI提供静态前端：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -Build
```

- 页面： http://127.0.0.1:8000
- API文档： http://127.0.0.1:8000/docs
- 登录：本地 `.env` 中的 `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD`。

初始化不会重置已有账号密码。密码修改后，以新密码登录；`.env` 初始值不再代表当前密码。

### 5. 首次验证

1. 登录后进入「工作概览」，点击「导入演示样本」。
2. 在「检查记录」中分别打开一条数字信号记录和一条标准报告图记录，点击「运行分析」。
3. 确认两条记录都显示五类模型预测结果。也可访问 [健康检查](http://127.0.0.1:8000/api/v1/health)，其中 `ready`、`database` 和两项模型状态应为 `true`。

### 日常开发与停止

前后端独立开发模式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -Dev
```

开发页面： http://127.0.0.1:5173 。Vite代理 `/api` 到8000。启动脚本先迁移数据库，再启动API与Worker，保留本地日志。出现错误检查 `runtime/*.err.log`。

前端源码位于 `frontend/src/`，使用 `-Dev` 时保存修改即可热更新。后端源码位于 `backend/app/`，修改后先停止再重新启动，API 和 Worker 都会加载新代码。数据库结构变更要随代码提交 `backend/migrations/versions/` 下对应的迁移。更新代码后，如有依赖变化，重新执行第 2 步。

停止应用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop.ps1
```

关闭项目专属开发数据库时可增加 `-StopDatabase`；不会删除数据库。停止脚本只处理记录中、命令行属于本项目的进程。

启动报错时，先查看 `runtime/api.err.log` 和 `runtime/worker.err.log`。数据库连接失败时核对 MySQL 服务、端口和 `.env` 里的账号权限。若当前项目已占用 `8000` 或 `5173`，先停止旧的启动进程或 VS Code 调试会话，然后再启动。

### 可选的 VS Code 断点调试

选择 `.venv/Scripts/python.exe`。F5可选择“FastAPI 后端”“批量任务 Worker”或“后端 + Worker”。启动前任务会停止由项目脚本登记的对应后台服务及Python子进程，检查8000端口并初始化数据库；不停止MySQL，不终止无关应用。若之前已有VS Code调试会话，请先按Shift+F5停止，再按F5启动。“后端 + Worker”可同时调试API和批量任务。前端在另一个终端执行 `cd frontend; npm.cmd run dev`，或直接访问8000端口的构建版页面。运行任务菜单也包含依赖安装、启动、停止和测试。

## 第一条检查

1. 管理员登录，创建analyst（检查/分析人员）和reviewer（复核人员）账号，管理员也可兼任。
2. 新建受检者档案；进入相应分析入口，选择档案并填写检查名称。
3. 信号：上传一对 `.hea/.dat` 或规范CSV；图像：上传标准PNG/JPEG。
4. 选择正确的波形处理状态，保存并校验，检查预览后运行分析。
5. 复核人员查看原数据和结果，填写至少5字意见后归档。
6. 导出HTML分析报告，可在浏览器打印为PDF；检查列表可导出UTF-8 CSV。

也可在工作概览点击“导入演示样本”。这只导入五个演示档案及十条已校验检查，所有预测均需实际点击分析或提交批量任务生成。

## 输入协议

- 信号：12标准导联、100 Hz、10秒；WFDB format-16要求配对、mV增益及校验和正确。
- CSV：UTF-8、逗号分隔，列名 `I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6`，1000行。按列名重排。可附 `time_s` 秒列，间隔0.01秒。明确声明mV或uV。
- `filtered_mv`：已完成项目40Hz低通的物理波形，不重复滤波；`raw_mv`：应用四阶40Hz零相位低通并按处理版1微伏存储精度量化。全局训练集标准化在推理前统一应用。
- 报告图：与训练一致的3行4列、底部10秒II导联节律条。图片布局不自动判别。RGB、Pillow双线性224×224、ImageNet归一化。
- 单次文件总量≤16 MB，图片最大边8000、总像素≤2500万。未知采样率、未知单位、未支持的WFDB编码需先转换，系统不会猜测。

## 验证

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm.cmd run build
```

后端测试使用独立的 SQLite 文件。完整浏览器测试会在正在运行的 MySQL 开发库中创建验收记录，建议使用单独的测试库。启动完整构建模式后，用本机 Chrome 测试 Chrome，再通过 Playwright 安装 Firefox 和 WebKit。

```powershell
.venv\Scripts\python.exe -m playwright install firefox webkit
.venv\Scripts\python.exe scripts/verify_system.py
```

浏览器测试使用 `-DevDependencies` 安装的测试库，并把结果写入 `runtime/qa/verification.json`。WebKit 自动测试、真实 Safari 测试、模型推理耗时和系统端到端延迟应分别记录。

## GitHub交付

只推送本仓库目录，不推送上级实验归档。仓库包含两份发布模型（约17 MiB总量）、固定配置、少量演示数据及源代码。`.env`、虚拟环境、MySQL数据目录、上传文件、日志和临时测试记录均被忽略。

组员从最新的 `main` 新建功能分支。下面用 `feature/update-page` 举例。

```powershell
git switch main
git pull --ff-only
git switch -c feature/update-page
```

完成修改并在本地验证后，提交改动，再用 `git push -u origin feature/update-page` 推送分支，在 GitHub 提出 Pull Request。仓库配置的 GitHub Actions 会检查后端测试和前端构建。

许可、模型来源及数据引用见 `LICENSE` 和 `THIRD_PARTY_NOTICES.md`。
