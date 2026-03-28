
from datetime import datetime
import os
from sdk import LLM, Agent, Conversation
from sdk.context.agent_context import AgentContext
from sdk.context.condenser.llm_summarizing_condenser import (
    LLMSummarizingCondenser,
)
from sdk.context.memory.base import ExecutionTrace, ExperienceMemory
from sdk.context.memory.elasticsearch_config import ElasticsearchConfig
from sdk.context.memory.embedding.embedding_config import EmbeddingConfig
from sdk.context.memory.embedding.openai_embedding import OpenAIEmbedding
from sdk.context.memory.memory_manager import MemoryManager
from sdk.llm.message import Message, TextContent


api_key = os.getenv("LLM_API_KEY")
user_id = "111111"
assert api_key is not None, "LLM_API_KEY environment variable is not set."

# embedding-model 很多需要通过chatgpt来完成，并不能通过litellm，因为不支持
model = os.getenv("LLM_MODEL", "dashscope/deepseek-v3.2")
embedding_model = "text-embedding-v1"
base_url = os.getenv("LLM_BASE_URL")

persistence_dir = "D:\\spacex\\agent_data2"
llm = LLM(
    model=model,
    embedding_model=embedding_model,  
    api_key=api_key,
    base_url=base_url,
)
# 待会调整到配置项中
elasticsearch_config: ElasticsearchConfig = ElasticsearchConfig(
    host="http://127.0.0.1:9200",
    collection_name="agent_memory_new",
    embedding_model_dims=1536,
)
embedding_config = EmbeddingConfig(
    model=embedding_model, api_key=api_key, base_url=base_url, embedding_dims=1536
)
opai_embeddding = OpenAIEmbedding(embedding_config)
memory_manager: MemoryManager = MemoryManager(
    embedding_base=opai_embeddding,
    base_memory_dir=persistence_dir + "\\memory",
    elastic_config=elasticsearch_config,
)
current_time = datetime.now()
experience = ExperienceMemory(
    id="exp_001",
    user_id=user_id,    
    question="输出3条具有实践意义，且有助于学习进步的哲理，请务必先思考，在回答",
    solution="先思考，后回答",
    execute_trace=[
        ExecutionTrace(
            tool_name="think_tool",
            choice_reason="根据用户问题，先进行思考分析，明确用户需求和目标，再选择合适的工具进行回答",
        )
    ],
    domain_type="general",
    feedback_type="positive",
    created_at=current_time,
)
memory_manager.build_experience(
    experience=experience 
)
memory_manager._search_experience_memory(user_id=user_id, content="输出3条具有实践意义，且有助于学习进步的哲理")
# memory_manager._search_experience_memory(
#     user_id=user_id,
#     content="请记住，我的邮箱 7755233@qq.com",
# )
agent_context: AgentContext = AgentContext(memory_manager=memory_manager)

agent = Agent(
    llm=llm,
    tools=[
        # Tool(name=TerminalTool.name),
        # Tool(name=FileEditorTool.name),
        # Tool(name=TaskTrackerTool.name),
    ],
    condenser=LLMSummarizingCondenser(llm=llm, max_size=8, keep_first=2),
    agent_context=agent_context,
)  # type: ignore

cwd = os.getcwd()  # 通过会话id 检索到未完成的会话。
conversation = Conversation(agent=agent, workspace=cwd, persistence_dir=persistence_dir)

# conversation.send_message(
#     "分2次输出不同的 人生哲理，一次输出一条 ,严格分2次，不要一次输出2个 "
# )
# conversation.run()
message = Message(
    user_id=user_id,
    role="user",
    content=[TextContent(text="请记住，我的邮箱 7755233@qq.com")],
)
conversation.send_message(message)
conversation.run()
message = Message(
    user_id=user_id,
    role="user",
    content=[TextContent(text="输出3条具有实践意义，且有助于学习进步的哲理，请务必先思考，在回答")],
)
message = Message(
    user_id=user_id,
    role="user",
    content=[TextContent(text="回复不错")],
)
conversation.send_message(message)
conversation.run()
message = Message(
    user_id=user_id,
    role="user",
    content=[TextContent(text="输出3条具有实践意义，且有助于学习进步的哲理")],
)
conversation.send_message(message)
conversation.run()
print("All done!")
