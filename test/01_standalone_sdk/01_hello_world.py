import os

from sdk import LLM, Agent, Conversation
from sdk.context.condenser.llm_summarizing_condenser import (
    LLMSummarizingCondenser,
)


api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "dashscope/deepseek-v3.2")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    model=model,
    api_key=api_key,
    base_url=base_url,
)

agent = Agent(
    llm=llm,
    tools=[
        # Tool(name=TerminalTool.name),
        # Tool(name=FileEditorTool.name),
        # Tool(name=TaskTrackerTool.name),
    ],
    condenser=LLMSummarizingCondenser(llm=llm, max_size=8, keep_first=2),
)  # type: ignore

cwd = os.getcwd()
conversation = Conversation(
    agent=agent, workspace=cwd, persistence_dir="D:\\spacex\\agent_data2"
)

conversation.send_message(
    "分10次输出不同的 人生哲理，一次输出一条 ,严格分10次，不要一次输出10个 ,严格分10次，不要一次输出10个，请先思考，请务必调用工具"
)
conversation.run()
print("All done!")
