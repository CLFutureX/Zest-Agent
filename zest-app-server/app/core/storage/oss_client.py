"""OSS 客户端封装 —— 机制层。

仅封装 oss2 的字节存取（put/get/delete/exists），不做业务命名策略；
对象键（key）的生成规则由策略层（service）决定。
凭证在构造时传入；缺凭证时构造抛错，由策略层决定何时实例化。
"""
from __future__ import annotations

import oss2


class OssClientError(RuntimeError):
    """OSS 操作失败。"""


class OssClient:
    """阿里云 OSS bucket 的薄封装。"""

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str,
    ):
        if not all([access_key_id, access_key_secret, endpoint, bucket_name]):
            raise OssClientError("OSS 配置不完整（access_key_id/secret/endpoint/bucket）")
        auth = oss2.Auth(access_key_id, access_key_secret)
        self._bucket = oss2.Bucket(auth, endpoint, bucket_name)
        self.bucket_name = bucket_name

    def put_bytes(self, key: str, data: bytes) -> str:
        try:
            result = self._bucket.put_object(key, data)
        except oss2.exceptions.OssError as e:
            raise OssClientError(f"OSS 上传失败 key={key}: {e}") from e
        if result.status != 200:
            raise OssClientError(f"OSS 上传失败 key={key} status={result.status}")
        return key

    def get_bytes(self, key: str) -> bytes:
        try:
            result = self._bucket.get_object(key)
            return result.read()
        except oss2.exceptions.OssError as e:
            raise OssClientError(f"OSS 下载失败 key={key}: {e}") from e

    def delete(self, key: str) -> bool:
        try:
            self._bucket.delete_object(key)
            return True
        except oss2.exceptions.OssError as e:
            raise OssClientError(f"OSS 删除失败 key={key}: {e}") from e

    def exists(self, key: str) -> bool:
        try:
            return bool(self._bucket.object_exists(key))
        except oss2.exceptions.OssError as e:
            raise OssClientError(f"OSS 查询失败 key={key}: {e}") from e
