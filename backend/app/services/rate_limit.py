"""接口限流服务"""

from app.redis_client import check_rate_limit
from app.config import config


def check_chat_rate() -> tuple[bool, int]:
    return check_rate_limit("chat", config.CHAT_RATE_LIMIT_PER_MINUTE)


def check_upload_rate() -> tuple[bool, int]:
    return check_rate_limit("upload", config.UPLOAD_RATE_LIMIT_PER_MINUTE)
