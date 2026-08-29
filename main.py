# -*- coding: utf-8 -*-
"""
Zepp自动刷步数主程序
Token缓存、自动推送、错误重试
直接读取环境变量
"""
import json
import os
import random
import sys
import time
import traceback
import uuid
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, cast

import pytz

import util.push_util as push_util
import util.zepp_helper as zepphelper
from util.aes_help import encrypt_data, decrypt_data, get_aes_key


# ==================== 全局配置 ====================

class Config:
    """全局配置类"""
    TOKEN_FILE = "encrypted_tokens.data"
    TASK_STATE_FILE = "task_state.json"
    DEFAULT_MIN_STEP = 10000
    DEFAULT_MAX_STEP = 35000
    MAX_RETRY = 3
    RETRY_DELAY = 2

    # 自动执行时段允许的小时列表（北京时间）
    # 由 cron-job.org 准点触发：早上 10:00、晚上 19:30
    # 各保留 1 小时冗余以容忍 GitHub 排队延迟，task_state 保证每天各只真刷一次
    AUTO_EXEC_HOURS = {
        'morning': {10, 11},   # 10点为主（10:00 触发），延迟到 11 点也能补上
        'evening': {19, 20},   # 19点为主（19:30 触发），延迟到 20 点也能补上
    }

    # 时间段步数配置（按实际小时划分）
    MANUAL_STEP_RANGES = {
        'night': (10000, 20000),     # 北京 1-5点
        'morning': (10000, 20000),   # 北京 6-12点
        'afternoon': (21000, 30000), # 北京 13-18点（手动触发时使用）
        'evening': (31000, 35000),   # 北京 19-23/0点
    }


# ==================== 工具函数 ====================


def get_beijing_time() -> datetime:
    """获取北京时间"""
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


def format_now() -> str:
    """格式化当前时间（北京时间）"""
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


def get_timestamp() -> str:
    """获取时间戳（毫秒）"""
    current_time = get_beijing_time()
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
    """
    判断是否为真正的手动/网页触发。
    cron-job 外部定时触发（source=cron 的 workflow_dispatch）不算手动，
    仍照常走时段校验与 task_state 每日去重。
    """
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch':
        return False
    return os.environ.get('TRIGGER_SOURCE', '') != 'cron'


def get_current_period(hour: int = None) -> Optional[str]:
    """
    根据北京时间小时获取当前时段名称
    时段划分（北京时间）:
    - night:    01:00-05:59
    - morning:  06:00-12:59
    - evening:  17:00-00:59
    其他时段 (13:00-16:59) 不属于任何时段，自动触发时跳过
    """
    if hour is None:
        hour = get_beijing_time().hour

    if 1 <= hour <= 5:
        return 'night'
    elif 6 <= hour <= 12:
        return 'morning'
    elif 17 <= hour <= 23 or hour == 0:
        return 'evening'
    return None


def load_task_state() -> Dict[str, Any]:
    """
    加载任务状态文件，用于高频触发时同一天同一时段组只执行一次
    时段组: morning_group(10点一次), evening_group(19:30一次)
    文件结构: {"date": "2026-06-11", "periods": {"morning_group": bool, "evening_group": bool}}
    """
    default_state = {
        "date": get_beijing_time().strftime("%Y-%m-%d"),
        "periods": {"morning_group": False, "evening_group": False}
    }

    if not os.path.exists(Config.TASK_STATE_FILE):
        return default_state

    try:
        with open(Config.TASK_STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        today = get_beijing_time().strftime("%Y-%m-%d")
        if state.get("date") != today:
            print(f"[信息] 日期变更: {state.get('date')} -> {today}，重置任务状态")
            return default_state

        return state
    except Exception as e:
        print(f"[警告] 任务状态文件读取失败: {str(e)}")
        return default_state


def save_task_state(state: Dict[str, Any]):
    """保存任务状态到文件"""
    try:
        state["date"] = get_beijing_time().strftime("%Y-%m-%d")
        with open(Config.TASK_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[警告] 任务状态保存失败: {str(e)}")


def get_min_max_by_time(hour: int = None, minute: int = None) -> Tuple[int, int]:
    """
    根据当前北京时间智能计算步数范围
    时段划分（北京时间）:
    - 01:00-05:00 (night时段): 10000-20000
    - 06:00-12:00 (morning时段): 10000-20000
    - 13:00-18:00 (afternoon时段): 21000-30000
    - 19:00-24:00 (evening时段): 31000-35000
    """
    if hour is None:
        hour = get_beijing_time().hour
    if minute is None:
        minute = get_beijing_time().minute

    # 根据北京时间段选择步数范围
    if 1 <= hour <= 5:
        # 北京 1-5点 (night)
        return Config.MANUAL_STEP_RANGES['night']
    elif 6 <= hour <= 12:
        # 北京 6-12点 (morning)
        return Config.MANUAL_STEP_RANGES['morning']
    elif 13 <= hour <= 18:
        # 北京 13-18点 (afternoon)
        return Config.MANUAL_STEP_RANGES['afternoon']
    elif 19 <= hour <= 24 or hour == 0:
        # 北京 19-24点 (evening)
        return Config.MANUAL_STEP_RANGES['evening']
    else:
        # 默认范围
        return Config.DEFAULT_MIN_STEP, Config.DEFAULT_MAX_STEP


# ==================== Token管理 ====================

def prepare_user_tokens(aes_key: bytes = None) -> Dict[str, Any]:
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

        print(f"[成功] 已加载Token缓存")
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


def persist_user_tokens(user_tokens: Dict[str, Any], aes_key: bytes = None) -> bool:
    """
    保存Token到加密文件
    :param aes_key: AES密钥，如果为None则从环境变量获取
    :return: 是否保存成功
    """
    try:
        origin_str = json.dumps(user_tokens, ensure_ascii=False, indent=2)
        if aes_key is None:
            from util.aes_help import get_aes_key
            aes_key = get_aes_key()
        encrypted_data = encrypt_data(origin_str.encode("utf-8"), aes_key, None)

        with open(Config.TOKEN_FILE, 'wb') as f:
            f.write(encrypted_data)

        print(f"[成功] Token已加密保存")
        return True
    except Exception as e:
        print(f"[失败] Token保存失败: {str(e)}")
        traceback.print_exc()
        return False


# ==================== 核心业务类 ====================

class ZeppStepRunner:
    """Zepp刷步数执行器"""

    def __init__(self, user: str, password: str, user_tokens: Dict[str, Any]):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        self.invalid = False
        self.log_str = ""
        self.user_tokens = user_tokens
        self.error = None
        self.actual_step = 0

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
                    ok, msg = zepphelper.check_app_token(app_token, self.user_id)
                    if ok:
                        self.log_str += "[成功] 使用缓存的app_token\n"
                        return app_token
                    self.log_str += f"[详细] app_token验证失败: {msg}\n"
                except Exception as e:
                    self.log_str += f"[警告] app_token验证异常: {str(e)}\n"
            else:
                self.log_str += "[警告] 缓存中不存在 app_token\n"

            self.log_str += f"[警告] app_token已失效，尝试用login_token刷新...\n"

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

            self.log_str += f"[警告] login_token无效，尝试用access_token刷新...\n"

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
            app_token = self._full_login_process(0)
            if not app_token:
                self.invalid = True
                return None
            return app_token

        # 无缓存Token，执行完整登录
        self.log_str += f"[信息] 用户无缓存Token，执行完整登录流程\n"
        app_token = self._full_login_process(0)
        if not app_token:
            self.invalid = True
            return None
        return app_token

    def _full_login_process(self, retry_count=0) -> Optional[str]:
        """完整的登录流程，不使用缓存"""
        self.log_str += f"[登录] 开始第{retry_count}次重新登录流程，重新获取密钥并清空缓存\n"

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
                self.error = f"登录失败: {msg}"
                return None
            self.log_str += "[成功] 获取access_token\n"
        except Exception as e:
            self.log_str += f"[异常] 登录异常: {str(e)}\n"
            self.error = f"登录异常: {str(e)}"
            return None

        try:
            login_token, app_token, user_id, msg = zepphelper.grant_login_tokens(access_token, self.device_id,
                                                                                 self.is_phone)
            if not login_token:
                self.log_str += f"[失败] 获取login_token失败: {msg}\n"
                self.error = f"获取login_token失败: {msg}"
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
            return None

    def _clean_password(self):
        """安全清理密码"""
        if hasattr(self, '_password') and not self._password_cleaned:
            try:
                del self._password
                self._password_cleaned = True
            except AttributeError:
                pass

    def execute(self, min_step: int, max_step: int) -> Tuple[str, bool]:
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
                    if attempt < Config.MAX_RETRY - 1:
                        self.log_str += f"[重试] {Config.RETRY_DELAY}秒后进行第{attempt + 1}次登录重试...\n"
                        time.sleep(Config.RETRY_DELAY)
                    else:
                        return f"[失败] 连续{Config.MAX_RETRY}次登录尝试均失败", False
                else:
                    break

            if not app_token:
                return self.error or "[失败] 登录失败", False

            step = random.randint(min_step, max_step)
            self.actual_step = step

            update_success = False
            update_msg = ""
            last_error_msg = ""

            for attempt in range(Config.MAX_RETRY):
                try:
                    ok, msg = zepphelper.update_step(app_token, self.user_id, step, self.fake_ip_addr)
                    if ok:
                        update_success = True
                        update_msg = msg
                        break

                    last_error_msg = msg
                    self.log_str += f"[失败] 第{attempt + 1}次尝试: {msg}\n"

                    if msg and any(k in msg.lower() for k in ['token', 'auth', '未授权', '登录', '失效']):
                        self.log_str += f"[警告] 提交时发现Token可能失效，尝试重新获取密钥...\n"
                        app_token = self._full_login_process(retry_count=attempt + 1)
                        if not app_token:
                            self.log_str += f"[失败] 重新获取Token失败，放弃步数提交\n"
                            break
                        continue

                except Exception as e:
                    last_error_msg = str(e)
                    self.log_str += f"[异常] 第{attempt + 1}次尝试异常: {str(e)}\n"

                if attempt < Config.MAX_RETRY - 1:
                    delay = Config.RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    self.log_str += f"[重试] 网络波动，等待 {delay:.1f} 秒后重试...\n"
                    time.sleep(delay)

            if update_success:
                return f"[成功] {update_msg} | 步数: {step}", True
            else:
                fail_reason = last_error_msg if last_error_msg else "达到最大重试次数，步数更新未成功"
                return f"[失败] {fail_reason}", False
        finally:
            self._clean_password()


# ==================== 主执行函数 ====================

def run_single_account(user: str, password: str,
                       min_step: int, max_step: int, user_tokens: Dict[str, Any]) -> Dict[str, Any]:
    """执行单个账号的刷步数任务"""
    log_str = f"\n{'=' * 60}\n"
    log_str += f"[时间] {format_now()}\n"
    log_str += f"账号: {desensitize_user_name(user)}\n"
    log_str += f"{'=' * 60}\n"

    try:
        runner = ZeppStepRunner(user, password, user_tokens)
        exec_msg, success = runner.execute(min_step, max_step)

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


# ==================== 主入口 ====================

def main():
    """主函数 - 直接读取环境变量"""
    # 最早检查：自动触发时判断是否在允许的时间段
    bj_time = get_beijing_time()
    current_period = get_current_period(bj_time.hour)
    task_state = None

    if not is_manual_trigger():
        # 检查1: 是否在允许的时段（仅 morning/evening）
        if not current_period or current_period not in ('morning', 'evening'):
            print(f"北京时间: {bj_time.strftime('%H:%M:%S')}, 当前时段: {current_period or '非任务时段'}，跳过本次", flush=True)
            sys.exit(0)

        # 检查2: 当前小时是否在该时段的允许执行窗口内
        # morning: 9点或10点, evening: 19点或20点
        allowed_hours = Config.AUTO_EXEC_HOURS.get(current_period, set())
        if bj_time.hour not in allowed_hours:
            print(f"北京时间: {bj_time.strftime('%H:%M:%S')}, {current_period}时段允许执行时间: {sorted(allowed_hours)}点, 当前{bj_time.hour}点不在窗口内，跳过本次", flush=True)
            sys.exit(0)

        # 检查3: 今天该时段组是否已执行（时段组去重：9/10二选一, 19/20二选一）
        task_state = load_task_state()
        group_key = f"{current_period}_group"
        if task_state["periods"].get(group_key, False):
            print(f"北京时间: {bj_time.strftime('%H:%M:%S')}, {current_period}时段组({group_key})今日已执行，跳过本次", flush=True)
            sys.exit(0)

    print(f"\n{'=' * 60}", flush=True)
    print(f"Zepp自动刷步数程序", flush=True)
    print(f"执行时间: {format_now()} (北京时间)", flush=True)
    print(f"触发方式: {'手动触发' if is_manual_trigger() else '自动触发'}", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    # 读取环境变量
    users = os.environ.get('ZEPP_USER', '').strip()
    passwords = os.environ.get('ZEPP_PWD', '').strip()
    sckey = os.environ.get('SCKEY', '').strip()

    # 读取其他推送配置
    push_plus_token = os.environ.get('PUSH_PLUS_TOKEN', '').strip()
    push_wechat_webhook_key = os.environ.get('PUSH_WECHAT_WEBHOOK_KEY', '').strip()

    print("[检查] 环境变量配置...", flush=True)
    print(f"  - USER存在: {bool(users)}", flush=True)
    print(f"  - PWD存在: {bool(passwords)}", flush=True)
    print(f"  - SCKEY存在: {bool(sckey)}", flush=True)
    print(f"  - PUSH_PLUS_TOKEN存在: {bool(push_plus_token)}", flush=True)
    print(f"  - WECHAT_WEBHOOK_KEY存在: {bool(push_wechat_webhook_key)}", flush=True)
    print(f"  - AES_KEY存在: {bool(os.environ.get('AES_KEY'))}", flush=True)
    print(f"  - 当前时段: {current_period or '无'}\n", flush=True)

    if not users or not passwords:
        print("[错误] 缺少必需的环境变量: ZEPP_USER 或 ZEPP_PWD", flush=True)
        sys.exit(1)

    print(f"[成功] 配置验证通过\n", flush=True)

    # 初始化 Token 缓存
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
    min_step, max_step = get_min_max_by_time(bj_time.hour, bj_time.minute)

    push_channels = []
    if sckey and sckey != 'NO':
        push_channels.append("Server酱")
    if push_plus_token and push_plus_token != 'NO':
        push_channels.append("PushPlus")
    if push_wechat_webhook_key and push_wechat_webhook_key != 'NO':
        push_channels.append("企业微信")

    # 创建推送配置对象（用于最终结果统一推送）
    push_config = None
    if push_channels:
        push_config = push_util.PushConfig(
            sckey=sckey if sckey and sckey != 'NO' else None,
            push_plus_token=push_plus_token if push_plus_token and push_plus_token != 'NO' else None,
            push_wechat_webhook_key=push_wechat_webhook_key if push_wechat_webhook_key and push_wechat_webhook_key != 'NO' else None
        )

    # 执行刷步任务
    try:
        result = run_single_account(
            users, passwords, min_step, max_step,
            user_tokens
        )
        exec_results = [result]
    except Exception as e:
        print(f"\n[错误] 执行过程中发生异常: {str(e)}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    # 保存 Token 缓存
    if aes_key and user_tokens:
        try:
            persist_user_tokens(user_tokens, aes_key)
        except Exception as e:
            print(f"[警告] Token保存失败: {str(e)}", flush=True)

    # 保存任务状态（标记当前时段组已完成，同组内后续小时不再执行）
    if isinstance(current_period, str) and task_state is not None:
        group_key = f"{current_period}_group"
        state = cast(Dict[str, Any], task_state)
        state["periods"][group_key] = True
        save_task_state(state)

    # 统计结果
    fail_count = sum(1 for r in exec_results if not r.get('success'))

    # 晚间时段自动推送通知（手动触发和morning时段不推送）
    if not is_manual_trigger() and current_period == 'evening' and push_channels and push_config:
        push_util.push_results(exec_results, push_config, force_push=True)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
