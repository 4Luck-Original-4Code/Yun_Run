# -*- coding: utf-8 -*-
"""
Zepp自动刷步数主程序
Token缓存、自动推送、错误重试
直接读取环境变量
"""
import traceback
from datetime import datetime
import pytz
import uuid
import json
import random
import time
import os
import sys
from typing import Optional, Tuple, Dict, List

import requests
from util.aes_help import encrypt_data, decrypt_data, get_aes_key
import util.zepp_helper as zepphelper


# ==================== 全局配置 ====================

class Config:
    """全局配置类"""
    TOKEN_FILE = "encrypted_tokens.data"
    DEFAULT_MIN_STEP = 10000
    DEFAULT_MAX_STEP = 35000
    DEFAULT_SLEEP_GAP = 5.0
    REQUEST_TIMEOUT = 30
    MAX_RETRY = 3
    RETRY_DELAY = 2

    # 时间段步数配置（北京时间）
    MANUAL_STEP_RANGES = {
        'night': (10000, 20000),  # 北京 1-5点(UTC 17-21点)
        'morning': (10000, 20000),  # 北京 6-12点(UTC 22-4点，跨天)
        'afternoon': (21000, 30000),  # 北京 13-18点(UTC 5-10点)
        'evening': (31000, 35000),  # 北京 19-23/0点(UTC 11-15/16点)
    }


# ==================== 工具函数 ====================

def get_int_value_default(value: str, default: int) -> int:
    """获取环境变量的整数值，提供默认值"""
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        print(f"[警告] 值 {value} 无效，使用默认值: {default}")
        return default


def get_float_value_default(value: str, default: float) -> float:
    """获取环境变量的浮点值，提供默认值"""
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        print(f"[警告] 值 {value} 无效，使用默认值: {default}")
        return default


def get_bool_value_default(value: str, default: bool) -> bool:
    """获取环境变量的布尔值，提供默认值"""
    if not value:
        return default
    return value.upper() in ('TRUE', '1', 'YES', 'ON')


def get_utc_time() -> datetime:
    """获取UTC时间"""
    return datetime.now(pytz.utc)


def format_now() -> str:
    """格式化当前时间（UTC）"""
    return get_utc_time().strftime("%Y-%m-%d %H:%M:%S UTC")


def get_timestamp() -> str:
    """获取时间戳（毫秒）"""
    current_time = get_utc_time()
    return "%.0f" % (current_time.timestamp() * 1000)


def fake_ip() -> str:
    """
    生成虚拟IP地址（国内IP段）
    IP段：223.64.0.0 - 223.117.255.255 或 39.0.0.0 - 39.255.255.255
    """
    if random.choice([True, False]):
        return f"39.149.{random.randint(0, 255)}.{random.randint(0, 255)}"
    else:
        return f"223.{random.randint(64, 117)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


def desensitize_user_name(user: str) -> str:
    """账号脱敏显示"""
    if not user:
        return "None"
    length = len(user)
    if length < 3:
        return "请配置正确的手机号或者邮箱"
    return "*" * (length - 2) + user[-2:]


def is_manual_trigger() -> bool:
    """判断是否为手动触发"""
    return os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'


def get_min_max_by_time(hour: int = None, minute: int = None) -> Tuple[int, int]:
    """
    根据当前UTC时间智能计算步数范围
    UTC时间对应关系（北京时间 = UTC + 8）:
    - UTC 17-21点  → 北京 次日1-5点   (night时段: 10000-20000)
    - UTC 22-23点/0-4点  → 北京 6-12点  (morning时段: 10000-20000，跨天)
    - UTC 5-10点  → 北京 13-18点  (afternoon时段: 21000-30000)
    - UTC 11-16点 → 北京 19-24点  (evening时段: 31000-35000)
    """
    if hour is None:
        hour = get_utc_time().hour
    if minute is None:
        minute = get_utc_time().minute

    # 根据UTC时间段选择步数范围
    if 17 <= hour <= 21:
        # UTC 17-21 → 北京 1-5点 (night)
        return Config.MANUAL_STEP_RANGES['night']
    elif (22 <= hour <= 23) or (0 <= hour <= 4):
        # UTC 22-23,0-4 = 北京 6-12点 (morning，跨天)
        return Config.MANUAL_STEP_RANGES['morning']
    elif 5 <= hour <= 10:
        # UTC 5-10 → 北京 13-18点 (afternoon)
        return Config.MANUAL_STEP_RANGES['afternoon']
    elif 11 <= hour <= 16:
        # UTC 11-16 → 北京 19-24点 (evening)
        return Config.MANUAL_STEP_RANGES['evening']
    else:
        # 默认范围
        return Config.DEFAULT_MIN_STEP, Config.DEFAULT_MAX_STEP


def server_send(title: str, body: str, sckey: str = None):
    """
    Server酱推送（支持Server酱Turbo）
    :param title: 推送标题
    :param body: 推送正文
    :param sckey: Server酱密钥
    """
    if not sckey or sckey.upper() == 'NO':
        return

    server_url = f"https://sctapi.ftqq.com/{sckey}.send"

    data = {
        'text': title,
        'desp': body
    }

    try:
        response = requests.post(server_url, data=data, timeout=Config.REQUEST_TIMEOUT)
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


# ==================== Token管理 ====================

def prepare_user_tokens(aes_key: bytes = None) -> Dict:
    """从加密文件加载Token缓存"""
    if not os.path.exists(Config.TOKEN_FILE):
        print(f"[信息] Token缓存文件不存在，将创建新文件")
        return {}

    try:
        with open(Config.TOKEN_FILE, 'rb') as f:
            encrypted_data = f.read()

        if not encrypted_data:
            print(f"[警告] Token缓存文件为空")
            return {}

        # 使用传入的 aes_key，避免重复调用 get_aes_key()
        if aes_key is None:
            from util.aes_help import get_aes_key
            aes_key = get_aes_key()

        decrypted_data = decrypt_data(encrypted_data, aes_key, None)
        tokens = json.loads(decrypted_data.decode('utf-8', errors='strict'))

        print(f"[成功] 已加载 {len(tokens)} 个账号的Token缓存")
        return tokens
    except json.JSONDecodeError as e:
        print(f"[错误] Token文件JSON解析失败: {str(e)}")
        # 删除损坏的文件，避免持续报错
        try:
            os.remove(Config.TOKEN_FILE)
            print(f"[信息] 已删除损坏的Token文件，将重新创建")
        except Exception as remove_err:
            print(f"[警告] 无法删除损坏的Token文件: {str(remove_err)}")
        return {}
    except Exception as e:
        print(f"[警告] Token解密失败（可能是密钥错误）: {str(e)}")
        return {}


def persist_user_tokens(user_tokens: Dict) -> bool:
    """
    保存Token到加密文件
    :return: 是否保存成功
    """
    try:
        origin_str = json.dumps(user_tokens, ensure_ascii=False, indent=2)
        encrypted_data = encrypt_data(origin_str.encode("utf-8"), get_aes_key(), None)

        with open(Config.TOKEN_FILE, 'wb') as f:
            f.write(encrypted_data)

        print(f"[成功] Token已加密保存（{len(user_tokens)} 个账号）")
        return True
    except Exception as e:
        print(f"[失败] Token保存失败: {str(e)}")
        traceback.print_exc()
        return False


# ==================== 核心业务类 ====================

class ZeppStepRunner:
    """Zepp刷步数执行器"""

    def __init__(self, user: str, password: str, user_tokens: Dict):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        self.invalid = False
        self.log_str = ""
        self.user_tokens = user_tokens
        self.error = None
        self.actual_step = 0
        self.login_failure_count = 0

        # 参数校验
        user = str(user).strip()
        password = str(password).strip()

        if not user or not password:
            self.error = "[失败] 用户名或密码为空"
            self.invalid = True
            return

        # 存储密码用于登录，但不长期保存明文
        self._password = password

        # 处理用户名格式
        if not (user.startswith("+86") or "@" in user):
            user = "+86" + user

        self.is_phone = user.startswith("+86")
        self.user = user

        # 生成虚拟IP
        self.fake_ip_addr = fake_ip()
        self.log_str += f"[虚拟IP] {self.fake_ip_addr}\n"

        # 标记密码是否已清理
        self._password_cleaned = False

    def login(self, retry_count=0) -> Optional[str]:
        """
        登录并获取app_token
        支持三级Token缓存：access_token -> login_token -> app_token
        :return: app_token 或 None
        """
        if retry_count > 0:
            self.log_str += f"[重试] 第{retry_count}次登录尝试，跳过缓存，重新获取密钥\n"
            return self._full_login_process(retry_count)

        user_token_info = self.user_tokens.get(self.user)

        if user_token_info:
            access_token = user_token_info.get("access_token")
            login_token = user_token_info.get("login_token")
            app_token = user_token_info.get("app_token")
            self.device_id = user_token_info.get("device_id", self.device_id)
            self.user_id = user_token_info.get("user_id")

            if app_token:
                try:
                    ok, msg = zepphelper.check_app_token(app_token)
                    if ok:
                        self.log_str += "[成功] 使用缓存的app_token\n"
                        return app_token
                    self.log_str += f"[详细] app_token验证失败: {msg}\n"
                except Exception as e:
                    self.log_str += f"[警告] app_token验证异常: {str(e)}\n"
            else:
                self.log_str += "[警告] 缓存中不存在 app_token\n"

            self.log_str += f"[警告] app_token已失效，尝试刷新...\n"

            try:
                app_token, msg = zepphelper.grant_app_token(login_token)
                if app_token:
                    user_token_info["app_token"] = app_token
                    user_token_info["app_token_time"] = get_timestamp()
                    self.log_str += "[成功] 使用login_token刷新app_token\n"
                    return app_token
                self.log_str += f"[详细] login_token刷新失败: {msg}\n"
            except Exception as e:
                self.log_str += f"[警告] login_token刷新异常: {str(e)}\n"

            self.log_str += f"[警告] login_token无效，尝试刷新...\n"

            try:
                login_token, app_token, user_id, msg = zepphelper.grant_login_tokens(access_token, self.device_id,
                                                                                     self.is_phone)
                if login_token:
                    user_token_info["login_token"] = login_token
                    user_token_info["login_token_time"] = get_timestamp()
                    user_token_info["app_token"] = app_token
                    user_token_info["app_token_time"] = get_timestamp()
                    user_token_info["user_id"] = user_id
                    self.user_id = user_id
                    self.log_str += "[成功] 使用access_token刷新login_token和app_token\n"
                    return app_token
                self.log_str += f"[详细] access_token刷新失败: {msg}\n"
            except Exception as e:
                self.log_str += f"[警告] access_token刷新异常: {str(e)}\n"

            self.log_str += f"[警告] access_token无效，重新登录...\n"

        try:
            access_token, msg = zepphelper.login_access_token(self.user, self._password)
            if not access_token:
                self.log_str += f"[失败] 获取access_token失败: {msg}\n"
                self.error = f"登录失败: {msg}"
                self.invalid = True
                return None
            self.log_str += "[成功] 重新登录获取access_token\n"
        except Exception as e:
            self.log_str += f"[异常] 登录异常: {str(e)}\n"
            self.error = f"登录异常: {str(e)}"
            self.invalid = True
            return None

        try:
            login_token, app_token, user_id, msg = zepphelper.grant_login_tokens(access_token, self.device_id,
                                                                                 self.is_phone)
            if not login_token:
                self.log_str += f"[失败] 获取login_token失败: {msg}\n"
                self.error = f"获取login_token失败: {msg}"
                self.invalid = True
                return None

            self.user_id = user_id
            self.user_tokens[self.user] = {
                "access_token": access_token,
                "access_token_time": get_timestamp(),
                "login_token": login_token,
                "login_token_time": get_timestamp(),
                "app_token": app_token,
                "app_token_time": get_timestamp(),
                "user_id": user_id,
                "device_id": self.device_id
            }
            self.log_str += "[成功] 登录成功，获取所有Token\n"
            return app_token
        except Exception as e:
            self.log_str += f"[异常] 获取Token异常: {str(e)}\n"
            self.error = f"获取Token异常: {str(e)}"
            self.invalid = True
            return None

    def _full_login_process(self, retry_count=0) -> Optional[str]:
        """完整的登录流程，不使用缓存"""
        self.log_str += f"[登录] 开始第{retry_count}次重新登录流程，重新获取密钥并清空缓存\n"

        from util.aes_help import get_aes_key
        new_aes_key = get_aes_key()
        self.log_str += f"[密钥] 重新获取AES密钥完成\n"

        if self.user in self.user_tokens:
            del self.user_tokens[self.user]
            self.log_str += f"[缓存] 已清除用户 {self.user} 的旧缓存\n"
        else:
            self.log_str += f"[缓存] 用户 {self.user} 无旧缓存\n"

        try:
            access_token, msg = zepphelper.login_access_token(self.user, self._password)
            if not access_token:
                self.log_str += f"[失败] 获取access_token失败: {msg}\n"
                return None
            self.log_str += "[成功] 获取access_token\n"
        except Exception as e:
            self.log_str += f"[异常] 登录异常: {str(e)}\n"
            return None

        try:
            login_token, app_token, user_id, msg = zepphelper.grant_login_tokens(access_token, self.device_id,
                                                                                 self.is_phone)
            if not login_token:
                self.log_str += f"[失败] 获取login_token失败: {msg}\n"
                return None

            self.user_id = user_id
            self.user_tokens[self.user] = {
                "access_token": access_token,
                "access_token_time": get_timestamp(),
                "login_token": login_token,
                "login_token_time": get_timestamp(),
                "app_token": app_token,
                "app_token_time": get_timestamp(),
                "user_id": user_id,
                "device_id": self.device_id
            }
            self.log_str += "[成功] 登录成功，获取所有Token\n"
            return app_token
        except Exception as e:
            self.log_str += f"[异常] 获取Token异常: {str(e)}\n"
            return None

    def _clean_password(self):
        """安全清理密码"""
        if hasattr(self, '_password') and not self._password_cleaned:
            try:
                del self._password
                self._password_cleaned = True
            except AttributeError:
                pass

    def execute(self, min_step: int, max_step: int, sckey: str = None) -> Tuple[str, bool]:
        """
        执行刷步数主逻辑
        :return: (消息, 是否成功)
        """
        if self.invalid:
            return self.error, False

        try:
            app_token = None

            for attempt in range(Config.MAX_RETRY):
                if attempt == 0:
                    app_token = self.login(retry_count=0)
                else:
                    app_token = self._full_login_process(retry_count=attempt)

                if not app_token:
                    self.login_failure_count += 1
                    if attempt < Config.MAX_RETRY - 1:
                        self.log_str += f"[重试] {Config.RETRY_DELAY}秒后进行第{attempt + 1}次登录重试...\n"
                        time.sleep(Config.RETRY_DELAY)
                    else:
                        if sckey and sckey.upper() != 'NO':
                            self._send_login_failure_notification(sckey)
                        return f"[失败] 连续{Config.MAX_RETRY}次登录尝试均失败", False
                else:
                    self.login_failure_count = 0
                    break

            if not app_token:
                if sckey and sckey.upper() != 'NO':
                    self._send_login_failure_notification(sckey)
                return self.error or "[失败] 登录失败", False

            step = random.randint(min_step, max_step)
            self.actual_step = step

            update_success = False
            update_msg = ""

            for attempt in range(Config.MAX_RETRY):
                try:
                    ok, msg = zepphelper.update_step(app_token, self.user_id, step, self.fake_ip_addr)
                    if ok:
                        update_success = True
                        update_msg = msg
                        break

                    self.log_str += f"[失败] 第{attempt + 1}次尝试: {msg}\n"

                    if msg and any(k in msg.lower() for k in ['token', 'auth', '未授权', '登录', '失效']):
                        self.log_str += f"[警告] 提交时发现Token可能失效，尝试重新获取密钥...\n"
                        app_token = self._full_login_process(retry_count=attempt + 1)
                        if not app_token:
                            self.log_str += f"[失败] 重新获取Token失败，放弃步数提交\n"
                            break
                        continue

                except Exception as e:
                    self.log_str += f"[异常] 第{attempt + 1}次尝试异常: {str(e)}\n"

                if attempt < Config.MAX_RETRY - 1:
                    delay = Config.RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    self.log_str += f"[重试] 网络波动，等待 {delay:.1f} 秒后重试...\n"
                    time.sleep(delay)

            if update_success:
                return f"[成功] {update_msg} | 步数: {step}", True
            else:
                return "[失败] 达到最大重试次数，步数更新未成功", False
        finally:
            self._clean_password()

    def _send_login_failure_notification(self, sckey: str):
        """发送登录失败通知"""
        current_time = format_now()
        title = "刷步失败通知"
        body = f"{current_time}\n\n登录失败 | 账号: {desensitize_user_name(self.user)}\n原因: 连续3次登录尝试均失败"

        print(f"[信息] 推送登录失败通知...", flush=True)
        server_send(title, body, sckey)


# ==================== 主执行函数 ====================

def run_single_account(user: str, password: str,
                       min_step: int, max_step: int, user_tokens: Dict, sckey: str = None) -> Dict:
    """执行单个账号的刷步数任务"""
    log_str = f"\n{'=' * 60}\n"
    log_str += f"[时间] {format_now()}\n"
    log_str += f"账号: {desensitize_user_name(user)}\n"
    log_str += f"{'=' * 60}\n"

    try:
        runner = ZeppStepRunner(user, password, user_tokens)
        exec_msg, success = runner.execute(min_step, max_step, sckey)

        log_str += runner.log_str
        log_str += f"{exec_msg}\n"

        exec_result = {
            "user": desensitize_user_name(user),
            "success": success,
            "msg": exec_msg,
            "step": runner.actual_step if success else None
        }
    except Exception as e:
        error_msg = f"[异常] {str(e)}"
        log_str += error_msg + "\n"
        log_str += traceback.format_exc()

        exec_result = {
            "user": desensitize_user_name(user),
            "success": False,
            "msg": f"执行异常: {str(e)}"
        }

    print(log_str, flush=True)
    return exec_result


def execute_single_account(user: str, password: str, min_step: int, max_step: int,
                           user_tokens: Dict, sckey: str = None) -> List[Dict]:
    """执行单个账号的刷步数任务"""
    result = run_single_account(user, password, min_step, max_step, user_tokens, sckey)
    return [result]


def push_notification(exec_results: List[Dict], sckey: str = None):
    """推送执行结果通知"""
    if not sckey or sckey.upper() == 'NO':
        print("[信息] 未配置推送或已禁用推送", flush=True)
        return

    if not exec_results:
        return

    result = exec_results[0]
    user = result.get('user', '未知')
    success = result.get('success', False)
    res_msg = result.get('msg', '无信息')
    step = result.get('step', 0) if success else None

    status = "成功 success" if success else "失败 failure"
    current_time = format_now()

    title = "刷步通知"
    body = f"{current_time}\n\n"
    if step:
        body += f"{status} | 步数: {step}\n"
    else:
        body += f"{status} | {res_msg}\n"

    print(f"[信息] 正在推送通知...", flush=True)
    server_send(title, body, sckey)


# ==================== 主入口 ====================

def main():
    """主函数 - 直接读取环境变量"""
    print(f"\n{'=' * 60}", flush=True)
    print(f"Zepp自动刷步数程序", flush=True)
    print(f"执行时间: {format_now()}", flush=True)
    print(f"触发方式: {'手动触发' if is_manual_trigger() else '自动触发'}", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    users = os.environ.get('ZEPP_USER', '').strip()
    passwords = os.environ.get('ZEPP_PWD', '').strip()
    sckey = os.environ.get('SCKEY', '').strip()

    print("[检查] 环境变量配置...", flush=True)
    print(f"  - USER存在: {bool(users)}", flush=True)
    print(f"  - PWD存在: {bool(passwords)}", flush=True)
    print(f"  - SCKEY存在: {bool(sckey)}", flush=True)
    print(f"  - AES_KEY存在: {bool(os.environ.get('AES_KEY'))}\n", flush=True)

    if not users or not passwords:
        print("[错误] 缺少必需的环境变量: ZEPP_USER 或 ZEPP_PWD", flush=True)
        sys.exit(1)

    print(f"[成功] 配置验证通过\n", flush=True)

    user_tokens = {}
    aes_key = get_aes_key()

    if aes_key:
        try:
            user_tokens = prepare_user_tokens(aes_key)
        except Exception as e:
            print(f"[警告] Token加载失败: {str(e)}", flush=True)
            user_tokens = {}
    else:
        print("[警告] 未设置AES_KEY，无法使用Token缓存功能", flush=True)

    # 计算步数范围
    min_step, max_step = get_min_max_by_time()
    print(f"[信息] 步数范围: {min_step} ~ {max_step}", flush=True)
    print(f"[信息] 推送通知: {'已启用' if sckey and sckey != 'NO' else '未启用'}\n", flush=True)

    try:
        exec_results = execute_single_account(
            users, passwords, min_step, max_step,
            user_tokens, sckey
        )
    except Exception as e:
        print(f"\n[错误] 执行过程中发生异常: {str(e)}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    if aes_key and user_tokens:
        try:
            persist_user_tokens(user_tokens)
        except Exception as e:
            print(f"[警告] Token保存失败: {str(e)}", flush=True)

    # 统计结果
    total = len(exec_results)
    success_count = sum(1 for r in exec_results if r.get('success'))
    fail_count = total - success_count
    total_steps = sum(r.get('step', 0) for r in exec_results if r.get('success'))

    if sckey and sckey.upper() != 'NO' and not is_manual_trigger():
        current_hour = get_utc_time().hour
        if 11 <= current_hour <= 16:
            try:
                push_notification(exec_results, sckey)
            except Exception as e:
                print(f"[警告] 推送通知失败: {str(e)}", flush=True)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
