from typing import Any

from git import Optional
from pydantic import BaseModel, Field, model_validator


class ElasticsearchConfig(BaseModel):
    collection_name: str = Field(
        default="agent_experiences",
        description="Elasticsearch索引名称，默认为agent_experiences",
    )
    host: Optional[str] = Field(
        default=None, description="Elasticsearch服务器地址，默认为None"
    )
    port: Optional[int] = Field(
        default=None, description="Elasticsearch服务器端口，默认为None"
    )
    user: Optional[str] = None
    password: Optional[str] = None
    cloud_id: Optional[str] = None
    api_key: Optional[str] = None
    embedding_model_dims: int = Field(
        default=768, description="Embedding向量的维度，默认为768"
    )
    verify_certs: bool = Field(default=True, description="是否验证SSL证书，默认为True")
    use_ssl: bool = Field(default=False, description="是否使用SSL连接，默认为False")
    auto_create_index: bool = Field(
        default=True, description="是否自动创建索引，默认为True"
    )
    custom_search_query: Optional[dict] = Field(
        default=None, description="自定义搜索查询模板，默认为None"
    )
    headers: Optional[dict[str, str]] = Field(
        default=None, description="连接Elasticsearch的HTTP头，默认为None"
    )

    @model_validator(mode="before")
    @classmethod
    def validate_auth(cls, values: dict[str, Any]) -> dict[str, Any]:
        # Check if either cloud_id or host/port is provided
        if not values.get("cloud_id") and not values.get("host"):
            raise ValueError("Either cloud_id or host must be provided")

        # Check if authentication is provided
        # if not any(
        #     [values.get("api_key"), (values.get("user") and values.get("password"))]
        # ):
        #     raise ValueError("Either api_key or user/password must be provided")

        return values

    @model_validator(mode="before")
    @classmethod
    def validate_headers(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Validate headers format and content"""
        headers = values.get("headers")
        if headers is not None:
            # Check if headers is a dictionary
            if not isinstance(headers, dict):
                raise ValueError("headers must be a dictionary")

            # Check if all keys and values are strings
            for key, value in headers.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError("All header keys and values must be strings")

        return values

    @model_validator(mode="before")
    @classmethod
    def validate_extra_fields(cls, values: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = set(cls.model_fields.keys())
        input_fields = set(values.keys())
        extra_fields = input_fields - allowed_fields
        if extra_fields:
            raise ValueError(
                f"Extra fields not allowed: {', '.join(extra_fields)}. "
                f"Please input only the following fields: {', '.join(allowed_fields)}"
            )
        return values
