from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from sdk.context.memory.embedding.embedding_config import EmbeddingConfig


class EmbeddingBase(ABC, BaseModel):
    config: EmbeddingConfig = Field()

    @abstractmethod
    def get_embedding(self, text: str) -> list[float]:
        pass
