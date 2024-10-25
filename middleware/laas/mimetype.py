import mimetypes
from urllib.parse import urlparse


# 지원 가능한 MIME 타입 목록 정의
SUPPORTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",  # 일부 서비스는 jpg로 MIME 타입을 표시함
    "image/webp",
    "image/gif",
}


def is_supported_mime_type(mime_type):
    """MIME 타입이 지원되는지 검사"""
    return mime_type in SUPPORTED_MIME_TYPES


def get_mime_type_from_url(url):
    # URL에서 파일 확장자로 MIME 타입 추론
    path = urlparse(url).path
    mime_type, _ = mimetypes.guess_type(path)
    return mime_type or "application/octet-stream"  # 기본 MIME 타입
