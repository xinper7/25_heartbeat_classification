# 推送此代码副本

本目录是独立整理的代码副本，具有新的 Git 仓库，无旧提交和旧 Git LFS 对象依赖。
原工作目录保留作备份。数据、环境、凭据、旧笔记本和临时输出未复制；历史小型权重只用于测试及复现，不是当前应用模型。

1. 在 VS Code 中选择“文件 → 打开文件夹”，打开此新目录。
2. 检查待提交列表只包含项目文件；`.gitignore` 排除本地数据和生成产物。
3. 在此目录终端执行：

```powershell
git add -A
git commit -m "Initial PTB-XL project"
git push -u origin main
```

origin 已配置为 `https://github.com/xinper7/25_heartbeat_classification.git`。
如 Git 提示登录，使用具有该仓库写权限的 GitHub 账号完成认证。
新副本尚未提交或推送；以上操作由你执行。无需复制旧 `.git`、旧 `.gitattributes` 或旧 LFS 配置。
