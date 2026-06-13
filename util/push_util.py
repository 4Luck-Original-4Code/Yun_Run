# -*- coding: utf-8 -*-
"""
推送工具模块
支持多种推送方式：Server酱、PushPlus、企业微信 Webhook
"""
from datetime import datetime

import pytz
import requests


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
                 push_wechat_webhook_key=None):
        self.sckey = sckey
        self.push_plus_token = push_plus_token
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

    request_url = "https://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
        "channel": "wechat"
    }
    try:
        response = requests.post(request_url, data=data, timeout=timeout)
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

    request_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    payload = {
        "msgtype": "markdown_v2",
        "markdown_v2": {
            "content": build_wechat_content(title, content)
        }
    }

    try:
        response = requests.post(request_url, json=payload, timeout=timeout)
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


def push_results(exec_results, config: PushConfig, force_push: bool = False):
    """统一推送入口：逐个推送到所有已配置的渠道

    :param force_push: 为 True 时跳过时段检查，强制推送（用于晚间 cron 触发的统一推送）
    """
    if not force_push and not_in_push_time_range():
        return

    # 统计已配置的推送渠道数
    active_channels = sum(1 for key in [config.sckey, config.push_plus_token, config.push_wechat_webhook_key]
                         if key and key.upper() != 'NO')
    if active_channels > 0:
        print(f"\n[信息] 开始推送通知到 {active_channels} 个渠道...", flush=True)

    push_to_server_chan(exec_results, config)
    push_to_push_plus(exec_results, config)
    push_to_wechat_webhook(exec_results, config)


def not_in_push_time_range() -> bool:
    """
    检查当前是否在推送时间段内（北京时间 19:00-24:00）
    注意：force_push=True 时此函数不会被调用，见 push_results()

    :return: True=跳过, False=推送
    """
    time_bj = get_beijing_time()
    current_hour = time_bj.hour

    # 判断是否在晚上推送时段（北京时间 19-24点）
    is_evening = (19 <= current_hour <= 23) or (current_hour == 0)

    if not is_evening:
        print(f"[推送时间] 当前{current_hour}:xx，非晚上时段，跳过推送")
        return True

    print(f"[推送时间] 当前{current_hour}:xx，晚上时段，允许推送")
    return False


def push_to_server_chan(exec_results, config: PushConfig):
    """Server酱推送"""
    if not config.sckey or config.sckey.upper() == 'NO':
        print("[推送] Server酱未配置，跳过")
        return

    # 使用 exec_result 中的 msg 作为推送内容
    detail_msgs = [r.get('msg', '') for r in exec_results if r.get('msg')]
    body = f"{format_now_bj()}，{detail_msgs[0]}" if detail_msgs else f"{format_now_bj()}，无执行结果"

    title = "刷步通知"
    print(f"[推送] 发送Server酱...")
    server_send(title, body, config.sckey)


def push_to_push_plus(exec_results, config: PushConfig):
    """PushPlus推送（HTML）"""
    if not config.push_plus_token or config.push_plus_token.upper() == 'NO':
        print("[推送] PushPlus未配置，跳过")
        return

    # 使用 exec_result 中的 msg 作为推送内容
    detail_msgs = [r.get('msg', '') for r in exec_results if r.get('msg')]
    content = f"{format_now_bj()}，{detail_msgs[0]}" if detail_msgs else f"{format_now_bj()}，无执行结果"
    html = f'<div>{content}</div>'

    title = f"{format_now_bj()} 刷步通知"
    print(f"[推送] 发送PushPlus...")
    push_plus(config.push_plus_token, title, html)


def push_to_wechat_webhook(exec_results, config: PushConfig):
    """企业微信推送（Markdown V2）"""
    if not config.push_wechat_webhook_key or config.push_wechat_webhook_key.upper() == 'NO':
        print("[推送] 企业微信未配置，跳过")
        return

    # 使用 exec_result 中的 msg 作为推送内容
    detail_msgs = [r.get('msg', '') for r in exec_results if r.get('msg')]
    if detail_msgs:
        content = '## ' + '\n'.join(detail_msgs)
    else:
        content = f"## {format_now_bj()}，无执行结果"

    title = f"{format_now_bj()} 刷步通知"
    print(f"[推送] 发送企业微信...")
    push_wechat_webhook(config.push_wechat_webhook_key, title, content)
