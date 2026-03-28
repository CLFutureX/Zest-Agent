
from sdk.event.base import Event
from sdk.event.llm_convertible.system import SystemPromptEvent
from sdk.llm.message import TextContent


event = SystemPromptEvent(
    source="agent", system_prompt=TextContent(text="test demos"), tools=[]
)

types = type[event]
print(types)
print(isinstance(event, Event))
