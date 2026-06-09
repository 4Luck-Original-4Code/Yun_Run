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
    """获取北京时间"""
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


def format_now_bj():
    """格式化当前北京时间"""
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
    """Server酱推送（支持Turbo版）"""
    if not sckey or sckey.upper() == 'NO':
        print("[推送] Server酱未配置，跳过")
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
                print(f"[推送] Server酱返回非JSON: {response.text[:200]}")
                return
            if result.get('code') == 0:
                print(f"[推送] Server酱推送成功")
            else:
                print(f"[推送] Server酱推送失败: {result.get('message', '未知错误')}")
        else:
            print(f"[推送] Server酱请求失败: HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"[推送] Server酱请求超时({timeout}秒)")
    except Exception as e:
        print(f"[推送] Server酱推送异常: {str(e)}")


def push_plus(token, title, content, timeout: int = 30):
    """PushPlus推送（HTML格式）"""
    if not token or token.upper() == 'NO':
        print("[推送] PushPlus未配置，跳过")
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
            code = json_res.get('code', -1)
            msg = json_res.get('msg', '未知')
            if code == 200:
                print(f"[推送] PushPlus推送成功")
            else:
                print(f"[推送] PushPlus推送失败: {code}-{msg}")
        else:
            print(f"[推送] PushPlus请求失败: HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[推送] PushPlus网络异常: {e}")
    except Exception as e:
        print(f"[推送] PushPlus推送异常: {e}")


def push_wechat_webhook(key, title, content, timeout: int = 30):
    """企业微信机器人推送（Markdown V2格式）"""
    if not key or key.upper() == 'NO':
        print("[推送] 企业微信未配置，跳过")
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
            errcode = json_res.get('errcode', -1)
            errmsg = json_res.get('errmsg', '未知')
            if errcode == 0:
                print(f"[推送] 企业微信推送成功")
            else:
                print(f"[推送] 企业微信推送失败: {errmsg}")
        else:
            print(f"[推送] 企业微信请求失败: HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[推送] 企业微信网络异常: {e}")
    except Exception as e:
        print(f"[推送] 企业微信推送异常: {e}")


def build_wechat_content(title, content) -> str:
    """构建企业微信 Markdown 内容"""
    return f"# {title}\n{content}"


def push_results(exec_results, summary, config: PushConfig):
    """统一推送入口：逐个推送到所有已配置的渠道"""
    if not_in_push_time_range(config):
        print("[推送] 不在推送时间段，跳过")
        return

    push_to_server_chan(exec_results, summary, config)
    push_to_push_plus(exec_results, summary, config)
    push_to_wechat_webhook(exec_results, summary, config)


def not_in_push_time_range(config: PushConfig) -> bool:
    """
    检查当前是否在推送时间段内

    优先级：
    1. 未配置推送时间 → 始终允许
    2. 当前北京时间整点匹配 → 允许
    3. cron_change_time计划时间匹配 → 允许（延迟补偿）

    :return: True=跳过, False=推送
    """
    if not config.push_plus_hour:
        return False

    time_bj = get_beijing_time()

    # 策略1：当前时间匹配
    if config.push_plus_hour.isdigit():
        current_hour = time_bj.hour
        target_hour = int(config.push_plus_hour)
        if current_hour == target_hour:
            print(f"[推送时间] 当前{current_hour}:xx，匹配推送时间")
            return False

    # 策略2：cron_change_time计划时间匹配（延迟补偿）
    try:
        with open('cron_change_time', 'r') as f:
            lines = f.readlines()
            if lines:
                first_line = lines[0].strip()
                match = re.search(r'北京时间\((\d+):(\d+)\)', first_line)
                if match:
                    planned_hour = int(match.group(1))
                    planned_minute = match.group(2)
                    target_hour = int(config.push_plus_hour)
                    if target_hour == planned_hour:
                        print(f"[推送时间] 计划{planned_hour}:{planned_minute}，匹配推送，延迟补偿")
                        return False
    except FileNotFoundError:
        pass  # 首次运行或文件不存在
    except Exception as e:
        print(f"[警告] 读取cron_change_time失败: {e}")

    print(f"[推送时间] 当前{time_bj.hour}:xx ≠ {config.push_plus_hour}:00，跳过")
    return True


def push_to_server_chan(exec_results, summary, config: PushConfig):
    """Server酱推送"""
    if not config.sckey or config.sckey.upper() == 'NO':
        print("[推送] Server酱未配置，跳过")
        return

    body = f"{summary}\n\n"
    if len(exec_results) >= config.push_plus_max:
        body += "⚠️ 账号过多，详情请查看 GitHub Actions\n"
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
    print(f"[推送] 发送Server酱...")
    server_send(title, body, config.sckey)


def push_to_push_plus(exec_results, summary, config: PushConfig):
    """PushPlus推送（HTML）"""
    if not config.push_plus_token or config.push_plus_token.upper() == 'NO':
        print("[推送] PushPlus未配置，跳过")
        return

    html = f'<div>{summary}</div>'
    if len(exec_results) >= config.push_plus_max:
        html += '<div>⚠️ 账号过多，详情请查看 GitHub Actions</div>'
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
    print(f"[推送] 发送PushPlus...")
    push_plus(config.push_plus_token, title, html)


def push_to_wechat_webhook(exec_results, summary, config: PushConfig):
    """企业微信推送（Markdown V2）"""
    if not config.push_wechat_webhook_key or config.push_wechat_webhook_key.upper() == 'NO':
        print("[推送] 企业微信未配置，跳过")
        return

    content = f'## {summary}'
    if len(exec_results) >= config.push_plus_max:
        content += '\n- ⚠️ 账号过多，详情请查看 GitHub Actions'
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
    print(f"[推送] 发送企业微信...")
    push_wechat_webhook(config.push_wechat_webhook_key, title, content)


