# Zepp 自动刷步数项目

这是一个使用 GitHub Actions 自动运行的 Zepp (华米) 步数修改脚本，支持 Token 缓存、AES 加密持久化、随机步数生成、失败自动补跑和可选的多渠道推送通知（Server酱 / PushPlus / 企业微信）。该项目已优化为个人账号测试使用，仅支持单个账号。

## 功能特点
- **定时刷步 + 失败自动补跑**：cron-job.org 早、晚两窗定时触发（也可手动）；登录重试 3 次、步数提交重试 5 次，整窗失败则由后续触发点自动补跑，**早晚各只成功刷一次**（触发时刻见下文）。
- **随机步数**：按时间段智能生成步数范围（如晚上 31000-35000 步）。
- **Token 缓存 + AES 加密**：Token 经 AES 加密持久化到文件，避免频繁登录，同时保护凭证与传输数据。
- **多渠道智能推送**：支持 Server酱 / PushPlus / 企业微信；晚间成功即推一条，失败只在当晚最后一次（20:00 保底）推一条醒目的失败通知（标题 `【刷步失败】今晚已用尽所有重试`），避免重复告警；早上与手动触发不推送。
- **日志脱敏**：账号（手机号/邮箱）在所有日志与推送中统一脱敏，仅保留前 2 位、其余以 `*` 替换。
- **超时保护**：30 分钟超时，防止任务卡死。

## 工作原理

```text
[cron-job.org]  早窗 10:00~10:20 / 11:00，晚窗 19:00~19:20 / 20:00（北京时间）
        │  调用 GitHub API 触发 workflow_dispatch
        │  请求体: {"ref":"main","inputs":{"source":"cron"}}
        ▼
[GitHub Actions run.yml]  run-script
        │  把 source=cron 传给 main.py
        ▼
[main.py]
        │  is_manual_trigger()：source=cron → 视为自动触发
        │  于是走时段校验(早 10-11 点 / 晚 19-20 点) + task_state 每日去重
        ▼
    真刷步数 + 可选推送
```

- 每个触发点由 cron-job 精确控制，运行历史干净。
- `source=cron` 让 main.py 区分“外部定时”与“真手动”：定时触发仍走时段校验与每日去重，网页手动触发则可随时测试。

## 使用流程

1. **Fork 项目**：Fork 本仓库到你的 GitHub 账号。
2. **设置 Secrets**：进入仓库 `Settings > Secrets and variables > Actions`，点 `New repository secret` 逐个添加。
   - 必需：
     - `ZEPP_USER`：Zepp 账号（手机号如 `138xxxxxxxx` 或邮箱）。
     - `ZEPP_PWD`：Zepp 密码。
     - `AES_KEY`：16 字节 AES 密钥（自定义，如 `xeNtBVqzDc6tuNTh`）。
   - 可选（推送通知，至少配一个才会推送）：
     - `SCKEY`：Server酱推送密钥（关注 wx 服务号「方糖」获取）。
     - `PUSH_PLUS_TOKEN`：PushPlus 推送 token（[注册地址](https://www.pushplus.plus/push1.html)）。
     - `PUSH_WECHAT_WEBHOOK_KEY`：企业微信 Webhook 的 key（获取方式见下）。
   - 企业微信 key 获取：建一个内部群（只勾自己也能建）→ 右上角「…」→ 消息推送 → 添加 → 自定义消息推送（旧版叫「群机器人 → 新建机器人」）→ 填名称 → 复制 Webhook 地址 → 取地址里 `key=` 后面那串填入。
3. **启用 Actions 写权限**：仓库 `Settings > Actions > General > Workflow permissions`，选 `Read and write permissions` 后 Save。
4. **运行 Workflow**：
   - 手动触发：`Actions > 刷步数 > Run workflow`（source 默认 manual，随时可测试）。
   - 自动运行：由 cron-job.org 定时触发，配置见下一节。
5. **查看结果**：在 Actions 运行日志查看输出；配置了推送渠道时，晚间自动触发会收到推送。
6. **首次运行**：Token 缓存文件会自动创建，无需额外操作。

## 配置外部定时触发（cron-job.org，推荐）

GitHub 自带的 `schedule` 派发时刻不可靠，推荐用 **cron-job.org** 精确触发 `workflow_dispatch`。

### 1. 生成最小权限 GitHub Token

1. GitHub → 头像 → `Settings` → `Developer settings` → `Personal access tokens` → **Fine-grained tokens** → `Generate new token`。
2. 配置：
   - Token name：自定义；Resource owner：自己的账号（默认）。
   - Repository access：选 **Only select repositories**，勾选本仓库。
   - Permissions → Repository permissions → **Actions** → **Read and write**。
   - Expiration：建议 90 天。
3. 点 **Generate token**，立即复制那串 `github_pat_...`（只显示一次，遗失只能重建）。

### 2. 在 cron-job.org 新建任务

**一个任务只能填一条 Cron**，因此需建 **4 个独立任务**，除「运行计划」外其余配置完全相同：

| 任务 | Cron 表达式 | 触发时间 |
|---|---|---|
| 早上主刷 | `0,5,10,15,20 10 * * *` | 10:00 / 05 / 10 / 15 / 20 |
| 早上保底 | `0 11 * * *` | 11:00 |
| 晚上主刷 | `0,5,10,15,20 19 * * *` | 19:00 / 05 / 10 / 15 / 20 |
| 晚上保底 | `0 20 * * *` | 20:00 |

4 个任务的公共配置：

| 配置项 | 填写内容 |
|---|---|
| 网站（URL） | `https://api.github.com/repos/<你的用户名>/<你的仓库名>/actions/workflows/run.yml/dispatches` |
| 时区（进阶页） | `Asia/Shanghai` |
| 请求方法（进阶页） | `POST` |
| 标头（进阶页） | ① `Authorization`：`token <你的 github_pat_...>`　② `Content-Type`：`application/json` |
| 请求本体（进阶页） | `{"ref": "main", "inputs": {"source": "cron"}}` |

> 带上 `inputs.source=cron` 后，main.py 会当它是自动触发，照常走时段校验与 `task_state` 每日去重：**每天早晚各只真刷一次**，某窗口首个触发点成功后同窗后续自动跳过；整窗失败则不写状态，由下一个触发点自动补跑。

### 3. 验证

保存后点 **测试运行**，回 GitHub **Actions** 页应看到一条 `workflow_dispatch` 触发的新运行；打开日志，`执行刷步数脚本` 应显示「触发方式: 自动触发」，且仅在早 10-11 点 / 晚 19-20 点窗口内真刷。

## 注意事项

- 步数修改有风险，请自行承担。
- PushPlus 和企业微信支持 HTML/Markdown 格式，消息更美观。
- 若反复登录失败（达到最大重试次数），可能是账号需要验证：登录华米/Zepp APP 绑定第三方后，再手动触发一次刷步。

## 依赖

- Python 3.10
- 库：`pytz`、`requests`、`pycryptodome`（详见 `requirements.txt`）

## 参考资料

- https://github.com/TonyJiangWJ/mimotion
- https://github.com/hanximeng/Zepp_API/blob/main/index.php
