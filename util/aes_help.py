from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import os

# 华米传输加密使用的密钥 固定iv
# 参考自 https://github.com/hanximeng/Zepp_API/blob/main/index.php
HM_AES_KEY = b'xeNtBVqzDc6tuNTh'  # 16 bytes
HM_AES_IV = b'MAAAYAAAAAAAAABg'  # 16 bytes

AES_BLOCK_SIZE = AES.block_size  # 16


def get_aes_key():
    """获取AES密钥：从环境变量获取，未设置时返回None"""
    aes_key = os.environ.get('AES_KEY')
    if aes_key and len(aes_key) == 16:
        return aes_key.encode('utf-8')
    print("[警告] AES_KEY环境变量未设置或无效，将返回None")
    return None


def _pkcs7_pad(data: bytes) -> bytes:
    """PKCS7填充"""
    pad_len = AES_BLOCK_SIZE - (len(data) % AES_BLOCK_SIZE)
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes) -> bytes:
    """PKCS7去填充"""
    if not data or len(data) % AES_BLOCK_SIZE != 0:
        raise ValueError(f"invalid padded data length {len(data)}")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > AES_BLOCK_SIZE:
        raise ValueError(f"invalid padding length: {pad_len}")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-pad_len]


def _validate_key(key: bytes):
    """验证密钥格式"""
    if not isinstance(key, (bytes, bytearray)):
        raise TypeError("key must be bytes")
    if len(key) != 16:
        raise ValueError("key must be 16 bytes for AES-128")


def encrypt_data(plain: bytes, key: bytes, iv: bytes | None = None) -> bytes:
    """
    AES-CBC加密
    
    参数：
      - plain: 明文字节
      - key: 16 字节 AES-128 密钥
      - iv: IV向量，如果为None则生成随机IV并附加在密文前
    
    返回：
      - iv为None时: IV（16B） + ciphertext
      - iv不为None时: ciphertext（使用固定IV）
    """
    _validate_key(key)
    if not isinstance(plain, (bytes, bytearray)):
        raise TypeError("plain must be bytes")

    if iv is None:
        # 使用随机IV
        iv = get_random_bytes(AES_BLOCK_SIZE)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = _pkcs7_pad(plain)
        ciphertext = cipher.encrypt(padded)
        return iv + ciphertext  # IV + 密文
    else:
        # 使用固定IV
        if len(iv) != AES_BLOCK_SIZE:
            raise ValueError(f"IV must be {AES_BLOCK_SIZE} bytes")
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = _pkcs7_pad(plain)
        ciphertext = cipher.encrypt(padded)
        return ciphertext  # 仅密文


def decrypt_data(data: bytes, key: bytes, iv: bytes | None = None) -> bytes:
    """
    AES-CBC解密
    
    参数：
      - data: 加密数据（IV + 密文 或 仅密文）
      - key: 16 字节 AES-128 密钥
      - iv: 固定IV，如果为None则从data前16字节提取
    
    返回：明文字节
    """
    _validate_key(key)
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")

    if iv is None:
        # 从数据中提取IV（前16字节）
        if len(data) < AES_BLOCK_SIZE:
            raise ValueError("data too short")
        
        iv = data[:AES_BLOCK_SIZE]
        ciphertext = data[AES_BLOCK_SIZE:]
        
        if len(ciphertext) == 0 or len(ciphertext) % AES_BLOCK_SIZE != 0:
            raise ValueError("invalid ciphertext length")
    else:
        # 使用提供的固定IV
        if len(iv) != AES_BLOCK_SIZE:
            raise ValueError(f"IV must be {AES_BLOCK_SIZE} bytes")
        ciphertext = data
        if len(ciphertext) == 0 or len(ciphertext) % AES_BLOCK_SIZE != 0:
            raise ValueError("invalid ciphertext length")

    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted_padded = cipher.decrypt(ciphertext)
    return _pkcs7_unpad(decrypted_padded)


