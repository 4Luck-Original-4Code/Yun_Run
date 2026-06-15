# Zepp 自动刷步数项目

这是一个使用 GitHub Actions 自动运行的 Zepp (华米) 步数修改脚本，支持 Token 缓存、AES 加密持久化、随机步数生成和可选的 Server酱推送通知。该项目已优化为个人账号测试使用，仅支持单个账号。

## 功能特点
- **自动/手动触发**：每天北京时间上午和晚上各自动运行一次，也支持手动触发。
- **随机步数**：根据时间段智能生成步数范围（例如晚上 31000-35000 步）。
- **Token缓存**：使用加密文件持久化 Token，避免频繁登录。
- **多渠道推送通知**：支持 Server酱、PushPlus、企业微信 Webhook 三种推送方式。
- **智能推送时间**：直接根据触发执行的 cron 表达式判断，无需额外文件同步。
- **安全加密**：使用 AES 加密保护 Token 和传输数据。
- **错误重试**：登录和步数提交失败时自动重试最多 3 次。
- **超时保护**：设置 30 分钟超时，防止任务长时间卡住。

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
     - `PUSH_PLUS_TOKEN`：PushPlus 推送 token（访问 http://www.pushplus.plus 注册获取）。
     - `PUSH_WECHAT_WEBHOOK_KEY`：企业微信推送通知的key，假设webhook是：https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=693a91f6-7xxx-4bc4-97a0-0ec2sifa5aaa，请复制key=后面的内容 `693a91f6-7xxx-4bc4-97a0-0ec2sifa5aaa` 。
3. **启用 Actions**：仓库 Settings > Actions > General > Workflow permissions > Read and write permissions > Save。
4. **运行 Workflow**：
   - 手动触发：Actions > 刷步数 > Run workflow。
   - 自动运行：等待预设时间点（UTC 时间，对应北京时间早上和晚上）。
5. **查看结果**：
   - 在 Actions 运行日志中查看详细输出。
   - 如果配置了推送渠道，非手动触发时会收到推送通知。
6. **首次运行**：Token 缓存文件会自动创建，无需额外操作。

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
