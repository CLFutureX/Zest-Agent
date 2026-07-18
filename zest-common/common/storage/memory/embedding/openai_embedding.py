import os

from litellm import EmbeddingInput
from ollama import embed
from openai import OpenAI
from pydantic import PrivateAttr

from common.storage.memory.embedding.embedding_base import EmbeddingBase
from common.storage.memory.embedding.embedding_config import EmbeddingConfig


class OpenAIEmbedding(EmbeddingBase):
    _client: OpenAI = PrivateAttr()

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config=config)

        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    def get_embedding(self, text) -> list[float]:
        # 这里可以根据memory_action调整embedding的参数或行为
        if self.config.model is None or self.config.embedding_dims is None:
            raise ValueError(
                "EmbeddingConfig must specify model and embedding_dims for OpenAIEmbedding."
            )

        return (
            self._client.embeddings.create(
                input=[text],
                model=self.config.model,
                dimensions=self.config.embedding_dims,
            )
            .data[0]
            .embedding
        )

def get_default_embedding(embedding_config: EmbeddingConfig | None = None)-> EmbeddingBase:
    if embedding_config is None:
        embedding_config = load_embedding_setting_from_env()
    
    return OpenAIEmbedding(embedding_config)
        
    
def load_embedding_setting_from_env() -> EmbeddingConfig:
    return EmbeddingConfig(
        model= os.getenv("EMBEDDING_LLM_MODEL", "text-embedding-v1"),
        api_key = os.getenv("LLM_API_KEY" ),
        base_url = os.getenv("LLM_BASE_URL"),
    )
      