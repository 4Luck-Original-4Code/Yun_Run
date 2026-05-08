# Zepp 自动刷步数项目

这是一个使用 GitHub Actions 自动运行的 Zepp (华米) 步数修改脚本，支持 Token 缓存、AES 加密持久化、随机步数生成和可选的 Server酱推送通知。该项目已优化为个人账号测试使用，仅支持单个账号。

## 功能特点
- **自动/手动触发**：每天北京时间 上午、下午 和 晚上各一次 自动运行，或手动触发。
- **随机步数**：根据时间段智能生成步数范围（例如晚上 31000-35000 步）。
- **Token缓存**：使用 Artifact 机制持久化加密 Token，避免频繁登录。
- **推送通知**：仅在自动运行的晚上 19:00 左右时间段发送 Server酱推送，其他时间仅在 GitHub Actions 控制台输出。
- **安全加密**：使用 AES 加密保护 Token 和传输数据。
- **简化单账号**：专为个人测试设计，无多账号并发逻辑。

## 使用流程
1. **Fork 项目**：Fork 本仓库到你的 GitHub 账号。
2. **设置 Secrets**：
   - 进入仓库 Settings > Secrets and variables > Actions > New repository secret。
   - 添加以下 Secrets：
     - `ZEPP_USER`：你的 Zepp 账号（手机号如 `138xxxxxxxx` 或邮箱）。
     - `ZEPP_PWD`：你的 Zepp 密码。
     - `AES_KEY`：16 字节的 AES 加密密钥（自定义，例如 `xeNtBVqzDc6tuNTh`）。
     - `SCKEY`：Server酱推送密钥（可选，如果需要推送请关注wx服务号`方糖`）。
3. **启用 Actions**：仓库 Settings > Actions > General > Workflow permissions > Read and write permissions > Save。
4. **运行 Workflow**：
   - 手动触发：Actions > 刷步数 > Run workflow。
   - 自动运行：等待预设时间点。
5. **查看结果**：
   - 在 Actions 运行日志中查看输出。
   - 如果配置了 SCKEY，每天晚上特定时间自动运行，会收到推送。
6. **首次运行**：如果 Artifact 不存在，会显示下载警告, 忽略即可。

## 注意事项
- 步数修改有风险，请自行承担。
- 仅支持单个账号，多账号输入会忽略额外账号。
- 如果 Token缓存失效，脚本会自动执行重新登录流程。
- 项目使用 GitHub Artifact 持久化 Token，保留 1 天。
- Artifact机制持久化加密不尽如人意，但不影响正常运行，替代方案待定。
- 长时间运行可能出现最大次数的登录失败，需登录华米APP绑定第三方，然后手动刷步。

## 依赖
- Python 3.10
- 库：pytz, requests, pycryptodome (详见 requirements.txt)

## 参考资料
- https://github.com/TonyJiangWJ/mimotion
- https://github.com/hanximeng/Zepp_API/blob/main/index.php 
