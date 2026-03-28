from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import Field
from rich.text import Text
from sdk.tool.schema import Action, Observation
from sdk.tool.tool import ToolDefinition, ToolExecutor
if TYPE_CHECKING:
    from sdk.agent.runner_context import RunnerContext
    from sdk.conversation.state import ConversationState

DESCRIPTION = ""
class QueryOneAction(Action):
    item_code: str = Field(..., description="商品编码")

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation with thinking styling."""
        content = Text()

        # Add thinking icon and header
        content.append("🤔 ", style="yellow")
        content.append("QueryOne: ", style="bold yellow")
        content.append(f"itemCode:{self.item_code}")

        # Add the thought content with proper formatting
        return content 

class QueryOneObservation(Observation):
    result: str = Field(description="执行结果")

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation with thinking styling."""
        content = Text()

        # Add thinking icon and header
       
        content.append("QueryOneObservation: ", style="bold yellow")
        content.append(f"itemCode:{self.result}")

        # Add the thought content with proper formatting
        return content 

ItemCodePriceMap:dict[str,str] = {
    "itemCode1":"1",
    "itemCode2":"2"
}
class QueryOneExecutor(ToolExecutor):

    def __call__(
        self,
        action: QueryOneAction,
        context: RunnerContext
        | None = None,  # 【修改2】参数名+类型：conversation→context，LocalConversation→RunnerContext
    ) -> QueryOneObservation:
    # 根据ItemCode 返回ItemPrice
        itemPrice = ItemCodePriceMap[action.item_code]
        return QueryOneObservation(result=f'{"item_price":{itemPrice}}')

class QueryOneDefinition(ToolDefinition):

    def create(cls)->Sequence[QueryOneDefinition]:
        return [cls(
            description = DESCRIPTION,
            action_type = QueryOneAction,
            observation_type = QueryOneObservation,
            executor = QueryOneExecutor(),
        )]
    
    
