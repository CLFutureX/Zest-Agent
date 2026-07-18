
from pydantic import BaseModel, Field


class EmbeddingConfig(BaseModel):
    model: str = Field(..., description="embedding model")
    api_key: str = Field()
    embedding_dims: int = Field(default=1536)
    base_url: str | None = Field(default=None)
    model_kwargs: dict | None = Field(default=None)
