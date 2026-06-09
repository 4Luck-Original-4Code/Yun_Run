# -*- coding: utf-8 -*-
"""
推送工具模块
支持多种推送方式：Server酱、PushPlus、企业微信 Webhook
"""
import json
import re
import requests
from datetime import datetime
import pytz


def get_beijing_time():
    """获取北京时间（与 main.py 保持一致）"""
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


def format_now_bj():
    """格式化当前时间（北京时间，与 main.py 保持一致）"""
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


class PushConfig:
    """推送配置类"""

    def __init__(self,
                 sckey=None,
                 push_plus_token=None,
                 push_plus_hour=None,
                 push_plus_max=30,
                 push_wechat_webhook_key=None):
        self.sckey = sckey
        self.push_plus_token = push_plus_token
        self.push_plus_hour = push_plus_hour
        self.push_plus_max = int(push_plus_max) if push_plus_max else 30
        self.push_wechat_webhook_key = push_wechat_webhook_key


def server_send(title: str, body: str, sckey: str = None, timeout: int = 30):
    """
    Server酱推送（支持Server酱Turbo）
    :param title: 推送标题
    :param body: 推送正文
    :param sckey: Server酱密钥
    :param timeout: 请求超时时间（秒）
    """
    if not sckey or sckey.upper() == 'NO':
        print("[信息] 未配置或已禁用 Server酱推送")
        return

    server_url = f"https://sctapi.ftqq.com/{sckey}.send"

    data = {
        'text': title,
        'desp': body
    }

    try:
        response = requests.post(server_url, data=data, timeout=timeout)
        if response.status_code == 200:
            try:
                result = response.json()
            except ValueError:
                print(f"[失败] Server酱返回非JSON: {response.text[:200]}")
                return
            if result.get('code') == 0:
                print(f"[成功] Server酱推送成功")
            else:
                print(f"[失败] Server酱推送失败: {result.get('message', '未知错误')}")
        else:
            print(f"[失败] Server酱推送失败: HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"[超时] Server酱推送超时")
    except Exception as e:
        print(f"[异常] Server酱推送异常: {str(e)}")


def push_plus(token, title, content, timeout: int = 30):
    """
    PushPlus 推送
    :param token: PUSHPLUS 的token
    :param title: 推送标题
    :param content: 推送内容（HTML格式）
    :param timeout: 请求超时时间（秒）
    """
    if not token or token.upper() == 'NO':
        print("[信息] 未配置或已禁用 PushPlus 推送")
        return

    requestUrl = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
        "channel": "wechat"
    }
    try:
        response = requests.post(requestUrl, data=data, timeout=timeout)
        if response.status_code == 200:
            json_res = response.json()
            print(f"[成功] PushPlus推送完毕：{json_res['code']}-{json_res['msg']}")
        else:
            print(f"[失败] PushPlus推送失败: HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[异常] PushPlus推送网络异常: {e}")
    except Exception as e:
        print(f"[异常] PushPlus推送未知异常: {e}")


def push_wechat_webhook(key, title, content, timeout: int = 30):
    """
    企业微信 Webhook 推送
    :param key: WebHook机器人的key
    :param title: 推送标题
    :param content: 推送内容（Markdown格式）
    :param timeout: 请求超时时间（秒）
    """
    if not key or key.upper() == 'NO':
        print("[信息] 未配置或已禁用 企业微信推送")
        return

    requestUrl = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    payload = {
        "msgtype": "markdown_v2",
        "markdown_v2": {
            "content": build_wechat_content(title, content)
        }
    }

    try:
        response = requests.post(requestUrl, json=payload, timeout=timeout)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('errcode') == 0:
                print(f"[成功] 企业微信推送完毕：{json_res['errmsg']}")
            else:
                print(f"[失败] 企业微信推送失败：{json_res.get('errmsg', '未知错误')}")
        else:
            print(f"[失败] 企业微信推送失败: HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[异常] 企业微信推送网络异常: {e}")
    except Exception as e:
        print(f"[异常] 企业微信推送未知异常: {e}")


def build_wechat_content(title, content) -> str:
    """构建企业微信 Markdown 内容"""
    return f"# {title}\n{content}"


def push_results(exec_results, summary, config: PushConfig):
    """
    推送所有结果到配置的渠道
    :param exec_results: 执行结果列表
    :param summary: 汇总信息
    :param config: 推送配置对象
    """
    if not_in_push_time_range(config):
        print("[信息] 当前不在推送时间范围内，跳过推送")
        return

    # 推送到各个渠道
    push_to_server_chan(exec_results, summary, config)
    push_to_push_plus(exec_results, summary, config)
    push_to_wechat_webhook(exec_results, summary, config)


def not_in_push_time_range(config: PushConfig) -> bool:
    """
    检查是否在推送时间范围内
    :return: True 表示不在推送时间范围内，False 表示在推送时间范围内
    """
    if not config.push_plus_hour:
        return False  # 如果没有设置推送时间，则总是推送

    time_bj = get_beijing_time()

    # 首先根据当前时间判断，如果匹配直接返回
    if config.push_plus_hour.isdigit():
        if time_bj.hour == int(config.push_plus_hour):
            print(f"[推送时间] 当前设置推送整点为：{config.push_plus_hour}, 当前整点为：{time_bj.hour}，执行推送")
            return False

    # 如果当前时间不匹配，检查cron_change_time文件中的计划执行时间
    # 用于处理GitHub Actions延迟执行的情况
    try:
        with open('cron_change_time', 'r') as f:
            lines = f.readlines()
            if lines:
                # 读取第一行：planned exec time: 北京时间(19:30)
                first_line = lines[0].strip()
                # 提取计划执行的北京时间小时数
                match = re.search(r'北京时间\((\d+):(\d+)\)', first_line)
                if match:
                    planned_hour = int(match.group(1))
                    if int(config.push_plus_hour) == planned_hour:
                        print(
                            f"[推送时间] 当前设置推送整点为：{config.push_plus_hour}, 计划执行时间为：{planned_hour}:{match.group(2)}，执行推送（补偿延迟）")
                        return False
    except FileNotFoundError:
        pass  # 首次运行或文件不存在，属于正常情况
    except Exception as e:
        print(f"[警告] 读取cron_change_time文件出错: {e}")

    print(f"[推送时间] 当前北京时间整点为：{time_bj.hour}，不在配置的推送时间 {config.push_plus_hour}，不执行推送")
    return True


def push_to_server_chan(exec_results, summary, config: PushConfig):
    """推送到 Server酱"""
    if not config.sckey or config.sckey.upper() == 'NO':
        print("[信息] 未配置 SCKEY，跳过 Server酱推送")
        return

    # 构建推送内容
    body = f"{summary}\n\n"
    if len(exec_results) >= config.push_plus_max:
        body += "账号数量过多，详细情况请前往 GitHub Actions 中查看\n"
    else:
        for exec_result in exec_results:
            user = exec_result.get('user', '未知')
            success = exec_result.get('success', False)
            msg = exec_result.get('msg', '无信息')
            step = exec_result.get('step')

            if success:
                if step:
                    body += f"✅ 账号：{user} | 步数：{step} | {msg}\n"
                else:
                    body += f"✅ 账号：{user} | {msg}\n"
            else:
                body += f"❌ 账号：{user} | 失败原因：{msg}\n"

    title = "刷步通知"
    print(f"[信息] 正在推送 Server酱通知...")
    server_send(title, body, config.sckey)


def push_to_push_plus(exec_results, summary, config: PushConfig):
    """推送到 PushPlus"""
    if not config.push_plus_token or config.push_plus_token.upper() == 'NO':
        print("[信息] 未配置 PUSH_PLUS_TOKEN，跳过 PushPlus 推送")
        return

    html = f'<div>{summary}</div>'
    if len(exec_results) >= config.push_plus_max:
        html += '<div>账号数量过多，详细情况请前往 GitHub Actions 中查看</div>'
    else:
        html += '<ul>'
        for exec_result in exec_results:
            user = exec_result.get('user', '未知')
            success = exec_result.get('success', False)
            msg = exec_result.get('msg', '无信息')
            step = exec_result.get('step')

            if success:
                if step:
                    html += f'<li><span>账号：{user}</span> | 步数：{step} | {msg}</li>'
                else:
                    html += f'<li><span>账号：{user}</span> | {msg}</li>'
            else:
                html += f'<li><span>账号：{user}</span> | 失败原因：{msg}</li>'
        html += '</ul>'

    title = f"{format_now_bj()} 刷步通知"
    print(f"[信息] 正在推送 PushPlus 通知...")
    push_plus(config.push_plus_token, title, html)


def push_to_wechat_webhook(exec_results, summary, config: PushConfig):
    """推送到企业微信"""
    if not config.push_wechat_webhook_key or config.push_wechat_webhook_key.upper() == 'NO':
        print("[信息] 未配置 WECHAT_WEBHOOK_KEY，跳过企业微信推送")
        return

    content = f'## {summary}'
    if len(exec_results) >= config.push_plus_max:
        content += '\n- 账号数量过多，详细情况请前往 GitHub Actions 中查看'
    else:
        for exec_result in exec_results:
            user = exec_result.get('user', '未知')
            success = exec_result.get('success', False)
            msg = exec_result.get('msg', '无信息')
            step = exec_result.get('step')

            if success:
                if step:
                    content += f'\n- ✅ 账号：{user} | 步数：{step} | {msg}'
                else:
                    content += f'\n- ✅ 账号：{user} | {msg}'
            else:
                content += f'\n- ❌ 账号：{user} | 失败原因：{msg}'

    title = f"{format_now_bj()} 刷步通知"
    print(f"[信息] 正在推送企业微信通知...")
    push_wechat_webhook(config.push_wechat_webhook_key, title, content)


