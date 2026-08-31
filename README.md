# Zepp 自动刷步数项目

这是一个使用 GitHub Actions 自动运行的 Zepp (华米) 步数修改脚本，支持 Token 缓存、AES 加密持久化、随机步数生成和可选的 Server酱推送通知。该项目已优化为个人账号测试使用，仅支持单个账号。

## 功能特点
- **精准定时**：由 cron-job.org 在每天北京时间 10:00 与 19:30 精确触发，也可手动随时触发。
- **随机步数**：根据时间段智能生成步数范围（例如晚上 31000-35000 步）。
- **Token缓存**：使用加密文件持久化 Token，避免频繁登录。
- **多渠道推送通知**：支持 Server酱、PushPlus、企业微信 Webhook 三种推送方式。
- **定时推送**：自动触发（source=cron）的晚间任务跑完后统一推送通知。
- **安全加密**：使用 AES 加密保护 Token 和传输数据。
- **错误重试**：登录和步数提交失败时自动重试最多 3 次。
- **超时保护**：设置 30 分钟超时，防止任务长时间卡住。

## 工作原理

```text
[cron-job.org]  每天 10:00 / 19:30（北京时间）
        │  调用 GitHub API 触发 workflow_dispatch
        │  请求体: {"ref":"main","inputs":{"source":"cron"}}
        ▼
[GitHub Actions run.yml]  run-script
        │  把 source=cron 传给 main.py
        ▼
[main.py]
        │  is_manual_trigger()：source=cron → 视为自动触发
        │  于是走时段校验(10-11点/19-20点) + task_state 每日去重
        ▼
    真刷步数 + 可选推送
```

- 每个触发点由 cron-job 精确控制，运行历史干净。
- `source=cron` 让 main.py 区分“外部定时”与“真手动”：定时触发仍走时段校验与每日去重，网页手动触发则可随时测试。

## 使用流程
1. **Fork 项目**：Fork 本仓库到你的 GitHub 账号。
2. **设置 Secrets**：
   - 进入仓库 Settings > Secrets and variables > Actions > New repository secret。
   - 添加以下 Secrets（必需）：
     - `ZEPP_USER`：你的 Zepp 账号（手机号如 `138xxxxxxxx` 或邮箱）。
     - `ZEPP_PWD`：你的 Zepp 密码。
     - `AES_KEY`：16 字节的 AES 加密密钥（自定义，例如 `xeNtBVqzDc6tuNTh`）。
   - 添加以下 Secrets（可选，用于推送通知）：
     - `SCKEY`：Server酱推送密钥（关注wx服务号`方糖`获取）。
     - `PUSH_PLUS_TOKEN`：PushPlus 推送 token，注册地址[pushplus](https://www.pushplus.plus/push1.html)。
     - `PUSH_WECHAT_WEBHOOK_KEY`：企业微信推送通知的 key（企业微信建个内部群（只勾自己也能建）→ 右上角 … → 消息推送 → 添加 → 自定义消息推送（老版本叫"群机器人→新建机器人"）→ 填名称 → 复制 Webhook 地址 → 保存）。请复制 Webhook 地址里 `key=` 后面的内容填入，例如：`<你的企业微信Webhook的key>`。
3. **启用 Actions**：仓库 Settings > Actions > General > Workflow permissions > Read and write permissions > Save。
4. **运行 Workflow**：
   - 手动触发：Actions > 刷步数 > Run workflow（source 默认 manual，随时可测试）。
   - 自动运行：由 cron-job.org 在北京时间 10:00 / 19:30 触发（source=cron）。
5. **查看结果**：
   - 在 Actions 运行日志中查看详细输出。
   - 如果配置了推送渠道，非手动触发时会收到推送通知。
6. **首次运行**：Token 缓存文件会自动创建，无需额外操作。

## 配置外部定时触发（cron-job.org，推荐）

GitHub 自带的 `schedule` 派发时刻不可靠，推荐用免费的 **cron-job.org** 精确触发 `workflow_dispatch`。

**1. 生成最小权限 GitHub Token**

1. GitHub → 头像 → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token。
2. 配置：Token name:自定义，Resource owner:自己的账号(默认)，Repository access 选 **Only select repositories** -点击Select repositories选择本仓库；Permissions → Repository permissions → **Actions** → **Read and write**；Expiration 建议设 90 天。
3. 点 **Generate token**，立即复制那串 `github_pat_...`（只显示一次，遗忘只能新建）。

**2. 在 cron-job.org 新建任务**

| 配置项 | 填写内容 |
|---|---|
| 标题 | `Zepp 刷步触发` |
| 网站（URL） | `https://api.github.com/repos/<你的用户名>/<你的仓库名>/actions/workflows/run.yml/dispatches` |
| 运行计划 | 切到【自订】，Cron 填 `0 10 * * *`（每天 10:00）。**【一个任务只能一条 Cron】**：10:00 与 19:30 分钟不同无法合并，需新建两个独立任务 —— 本任务填 `0 10 * * *`；再**新建一个任务**填 `30 19 * * *`（19:30），其余配置完全相同 |
| 时区（【进阶】页） | `Asia/Shanghai` |
| 请求方法（【进阶】页） | `POST` |
| 标头（【进阶】页） | 两行键值：① 键 `Authorization` → 值 `token <你的github_pat_...>`；② 键 `Content-Type` → 值 `application/json` |
| 请求本体（【进阶】页） | `{"ref": "main", "inputs": {"source": "cron"}}` |

**3. 验证**

保存后点 **测试运行**，回 GitHub **Actions** 页应看到一条 `workflow_dispatch` 触发的新运行；打开日志，`执行刷步数脚本` 应显示“触发方式: 自动触发”（因 source=cron），且仅在 10-11 / 19-20 点真刷。

> 需新建**两个独立任务**：① Cron `0 10 * * *`（北京 10:00）；② Cron `30 19 * * *`（北京 19:30）。请求体都带上 `inputs.source=cron` 后，main.py 会把它当“自动触发”，照常走时段校验（真刷窗口 10-11 点 / 19-20 点）与 `task_state` 每日去重——即使延迟约 1 小时也能补上，且每天早晚各只真刷一次；你在网页手动运行（source 默认 manual）则跳过校验、随时可测。

## 注意事项
- 步数修改有风险，请自行承担。
- PushPlus 和企业微信支持 HTML/Markdown 格式，消息更美观。
- 长时间运行可能出现最大次数的登录失败，需登录华米 APP 绑定第三方，然后手动刷步。

## 依赖
- Python 3.10
- 库：pytz, requests, pycryptodome (详见 requirements.txt)

## 参考资料
- https://github.com/TonyJiangWJ/mimotion
- https://github.com/hanximeng/Zepp_API/blob/main/index.php 
