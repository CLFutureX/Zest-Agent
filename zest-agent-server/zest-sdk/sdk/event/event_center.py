"""事件中心 - 轻量级发布订阅模式（优化版）

设计原则：
1. 简洁：核心只有subscribe/publish/unsubscribe三个方法
2. 可扩展：支持事件类型过滤、作用域隔离
3. 线程安全：支持多Agent并发场景
4. 容错：Consumer异常不影响其他Consumer
5. 解耦：通过事件中心解耦ConversationState和各种监听器
6. Topic+Tag语义：支持会话级和Agent级的灵活过滤

消费者过滤规则（类似MQ的Topic+Tag）：
- 只设置conversation_id：接收该会话的所有事件（所有Agent）
- 同时设置conversation_id和agent_id：只接收该会话中特定Agent的事件
- 都不设置（Global）：接收所有事件
"""

from __future__ import annotations

import enum
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from threading import Lock
from typing import TYPE_CHECKING, Any

 
 
from common.logger import get_logger
from common.utils.common import ConversationID,AgentID


if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class EventConsumer(ABC):
    """事件消费者抽象基类（优化版）

    设计要点：
    1. conversation_id: 会话ID（类似MQ的Topic）
    2. agent_id: Agent ID（类似MQ的Tag）
    3. event_types: 事件类型过滤

    过滤规则：
    - 只设置conversation_id：接收该会话的所有事件
    - 同时设置conversation_id和agent_id：只接收该会话中特定Agent的事件
    - 都不设置：接收所有事件（Global）
    """

    def __init__(
        self,
        conversation_id: ConversationID | None,
        agent_id: AgentID  | None = None,
        event_types: list[type] | None = None,
        **kwargs,
    ):
        """初始化消费者

        Args:
            conversation_id: 会话ID（类似Topic），None表示全局
            agent_id: Agent ID（类似Tag），None表示接收该会话所有Agent的事件
            event_types: 关心的事件类型列表，None表示接收所有事件
        """
        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.event_types = event_types

        # 生成唯一的consumer_id用于去重
        self._consumer_id = str(uuid.uuid4())

    @property
    def consumer_id(self) -> str:
        """返回唯一的消费者ID（用于去重）"""
        return self._consumer_id

    @property
    def subscription_key(self) -> str:
        """返回订阅键（用于分组）

        格式：
        - Global: "global"
        - Conversation: "conv:{conversation_id}"
        - Agent: "conv:{conversation_id}:agent:{agent_id}"
        """
        if self.conversation_id is None:
            return "global"
        elif self.agent_id is None:
            return f"conv:{self.conversation_id}"
        else:
            return f"conv:{self.conversation_id}:agent:{self.agent_id}"

    @abstractmethod
    def on_event(self, event: Any):
        """处理事件（由子类实现）"""
        pass

    def should_handle(self, event: Any) -> bool:
        """判断是否应该处理该事件（基于事件类型过滤）

        Args:
            event: 待判断的事件

        Returns:
            True表示应该处理，False表示跳过
        """
        if self.event_types is None:
            return True

        for event_type in self.event_types:
            try:
                if isinstance(event, event_type) or type(event) == event_type:
                    return True
            except TypeError:
                # 处理泛型类型或其他不支持isinstance的类型
                # 对于基础类型（如str），使用type()进行精确匹配
                if type(event) == event_type:
                    return True

        return False

    def match_event(
        self,
        event_conversation_id: ConversationID | None,
        event_agent_id: AgentID | None,
    ) -> bool:
        """判断事件是否匹配该消费者（类似MQ的Topic+Tag匹配）

        Args:
            event_conversation_id: 事件的会话ID
            event_agent_id: 事件的Agent ID

        Returns:
            True表示匹配，False表示不匹配
        """
        # 全局消费者：接收所有事件
        if self.conversation_id is None:
            return True

        # 会话ID不匹配：不接收
        if str(self.conversation_id) != str(event_conversation_id):
            return False

        # 会话ID匹配，但消费者指定了agent_id
        if self.agent_id is not None:
            # 只接收特定Agent的事件
            return str(self.agent_id) == str(event_agent_id)

        # 会话ID匹配，消费者未指定agent_id：接收该会话所有Agent的事件
        return True

    def __repr__(self) -> str:
        """开发者友好的表示"""
        return (
            f"{self.__class__.__name__}("
            f"conversation_id={self.conversation_id}, "
            f"agent_id={self.agent_id}, "
            f"event_types={[t.__name__ for t in self.event_types] if self.event_types else 'All'})"
        )


class EventScope(str, enum.Enum):
    """事件作用域（保留用于向后兼容，但推荐使用新的Topic+Tag方式）"""

    AGENT = "agent"  # 单个agent自己内部
    CONVERSATION = "conversation"  # 会话粒度
    GLOBAL = "global"  # 支持跨对话，全量场景


class EventCenter:
    """事件中心 - 轻量级发布订阅实现（优化版）

    核心特性：
    1. Topic+Tag语义：支持会话级和Agent级的灵活过滤
    2. 支持事件类型过滤：Consumer只接收关心的事件
    3. 线程安全：使用Lock保护内部状态
    4. 容错：单个Consumer异常不影响其他Consumer
    5. 生命周期管理：支持subscribe/unsubscribe

    数据结构（优化后）：
    {
        "global": [consumer1, consumer2],  # 全局消费者
        "conv:conv_001": [consumer3, consumer4],  # 会话级消费者
        "conv:conv_001:agent:agent_001": [consumer5],  # Agent级消费者
    }
    """

    def __init__(self):
        # 使用subscription_key作为键，简化数据结构
        self._consumers: dict[str, list[EventConsumer]] = defaultdict(list)
        self._lock = Lock()

    def subscribe(self, consumer: EventConsumer) -> None:
        """订阅事件（简化版，不再需要scope参数）

        Args:
            consumer: 事件消费者
        """
        with self._lock:
            subscription_key = consumer.subscription_key
            consumer_list = self._consumers[subscription_key]

            # 避免重复订阅（基于consumer_id）
            if any(c.consumer_id == consumer.consumer_id for c in consumer_list):
                logger.warning(
                    f"Consumer {consumer.consumer_id} already subscribed to {subscription_key}"
                )
                return

            consumer_list.append(consumer)
            logger.debug(f"Subscribed consumer {consumer} to {subscription_key}")

    def batch_subscribe(self, consumers: list[EventConsumer]) -> None:
        """批量订阅事件

        Args:
            consumers: 事件消费者列表
        """
        with self._lock:
            for consumer in consumers:
                subscription_key = consumer.subscription_key
                consumer_list = self._consumers[subscription_key]

                # 避免重复订阅
                if any(c.consumer_id == consumer.consumer_id for c in consumer_list):
                    logger.warning(
                        f"Consumer {consumer.consumer_id} already subscribed to {subscription_key}"
                    )
                    continue

                consumer_list.append(consumer)
                logger.debug(f"Subscribed consumer {consumer} to {subscription_key}")

    def unsubscribe(self, consumer: EventConsumer) -> None:
        """取消订阅

        Args:
            consumer: 事件消费者
        """
        with self._lock:
            subscription_key = consumer.subscription_key
            consumer_list = self._consumers.get(subscription_key, [])

            # 基于consumer_id查找并移除
            for i, c in enumerate(consumer_list):
                if c.consumer_id == consumer.consumer_id:
                    consumer_list.pop(i)
                    logger.debug(
                        f"Unsubscribed consumer {consumer} from {subscription_key}"
                    )
                    return

            logger.warning(
                f"Consumer {consumer.consumer_id} not found in {subscription_key}"
            )

    def publish(
        self,
        event: Any,
        conversation_id: ConversationID.ID  | None = None,
        agent_id: str | uuid.UUID | None = None,
    ) -> None:
        """发布事件（简化版，使用Topic+Tag语义）

        Args:
            event: 要发布的事件
            conversation_id: 会话ID（Topic）
            agent_id: Agent ID（Tag）
        """
        # 获取目标consumers（需要复制一份，避免在迭代时被修改）
        with self._lock:
            target_consumers = self._get_target_consumers(conversation_id, agent_id)

        if not target_consumers:
            logger.debug(
                f"No consumers for event {event.id} "
                f"(conversation_id={conversation_id}, agent_id={agent_id})"
            )
            return

        # 分发事件（在锁外执行，避免Consumer阻塞其他操作）
        self._dispatch_event(target_consumers, event, conversation_id, agent_id)

    def _get_target_consumers(
        self,
        conversation_id: ConversationID | None,
        agent_id: str | uuid.UUID | None,
    ) -> list[EventConsumer]:
        """获取目标消费者列表（内部方法，需要在锁内调用）

        匹配规则：
        1. 全局消费者：总是匹配
        2. 会话级消费者：conversation_id匹配
        3. Agent级消费者：conversation_id和agent_id都匹配
        目前已经在匹配时，支持， 会话级订阅可以消费会话级消息以及会话内agent级消息。  agent级订阅，则只能消费agent级消息。
        Args:
            conversation_id: 会话ID
            agent_id: Agent ID

        Returns:
            目标消费者列表（副本）
        """
        target_consumers = []

        # 1. 全局消费者：总是接收
        global_consumers = self._consumers.get("global", [])
        target_consumers.extend(global_consumers)

        # 2. 会话级消费者：conversation_id匹配
        if conversation_id is not None:
            conv_key = f"conv:{conversation_id}"
            conv_consumers = self._consumers.get(conv_key, [])
            target_consumers.extend(conv_consumers)

            # 3. Agent级消费者：conversation_id和agent_id都匹配
            if agent_id is not None:
                agent_key = f"conv:{conversation_id}:agent:{agent_id}"
                agent_consumers = self._consumers.get(agent_key, [])
                target_consumers.extend(agent_consumers)

        return list(target_consumers)  # 返回副本

    def _dispatch_event(
        self,
        consumers: list[EventConsumer],
        event: Any,
        conversation_id: ConversationID.UUID | str | None,
        agent_id: str | uuid.UUID | None,
    ) -> None:
        """分发事件给消费者（内部方法）

        Args:
            consumers: 目标消费者列表
            event: 要分发的事件
            conversation_id: 事件的会话ID
            agent_id: 事件的Agent ID
        """
        for consumer in consumers:
            try:
                # 1. 检查事件是否匹配消费者（Topic+Tag匹配）
                if not consumer.match_event(conversation_id, agent_id):
                    continue

                # 2. 检查事件类型过滤
                if not consumer.should_handle(event):
                    continue

                # 3. 调用消费者处理事件
                consumer.on_event(event)

            except Exception as e:
                # 容错：单个Consumer异常不影响其他Consumer
                logger.exception(
                    f"Consumer {consumer} failed to handle event {event.id}: {e}",
                    exc_info=True,
                )

    def clear_all(self) -> None:
        """清空所有消费者"""
        with self._lock:
            self._consumers.clear()
            logger.debug("Cleared all consumers")

    def clear_conversation(self, conversation_id: ConversationID.UUID | str) -> None:
        """清空指定会话的所有消费者（包括会话级和Agent级）

        Args:
            conversation_id: 会话ID
        """
        with self._lock:
            # 清空会话级消费者
            conv_key = f"conv:{conversation_id}"
            if conv_key in self._consumers:
                del self._consumers[conv_key]
                logger.debug(f"Cleared conversation consumers for {conversation_id}")

            # 清空该会话下所有Agent级消费者
            keys_to_delete = [
                key
                for key in self._consumers.keys()
                if key.startswith(f"conv:{conversation_id}:agent:")
            ]
            for key in keys_to_delete:
                del self._consumers[key]
                logger.debug(f"Cleared agent consumers for {key}")

    def clear_agent(
        self, conversation_id: ConversationID , agent_id: str | uuid.UUID
    ) -> None:
        """清空指定Agent的消费者

        Args:
            conversation_id: 会话ID
            agent_id: Agent ID
        """
        with self._lock:
            agent_key = f"conv:{conversation_id}:agent:{agent_id}"
            if agent_key in self._consumers:
                del self._consumers[agent_key]
                logger.debug(f"Cleared agent consumers for {agent_key}")

    def get_consumer_count(
        self,
        conversation_id: ConversationID | str | None = None,
        agent_id: str | uuid.UUID | None = None,
    ) -> int:
        """获取消费者数量（用于调试和监控）

        Args:
            conversation_id: 会话ID，None表示统计全局
            agent_id: Agent ID，None表示统计会话级

        Returns:
            消费者数量
        """
        with self._lock:
            if conversation_id is None:
                # 统计全局消费者
                return len(self._consumers.get("global", []))
            elif agent_id is None:
                # 统计会话级消费者
                conv_key = f"conv:{conversation_id}"
                return len(self._consumers.get(conv_key, []))
            else:
                # 统计Agent级消费者
                agent_key = f"conv:{conversation_id}:agent:{agent_id}"
                return len(self._consumers.get(agent_key, []))

    def get_all_subscription_keys(self) -> list[str]:
        """获取所有订阅键（用于调试）"""
        with self._lock:
            return list(self._consumers.keys())

    # ===== 向后兼容的API（保留旧的scope-based API） =====

    def subscribe_with_scope(self, scope: EventScope, consumer: EventConsumer) -> None:
        """订阅事件（向后兼容的API）

        Args:
            scope: 事件作用域（已废弃，仅用于向后兼容）
            consumer: 事件消费者
        """
        logger.warning(
            "subscribe_with_scope is deprecated, please use subscribe() directly"
        )
        self.subscribe(consumer)

    def publish_with_scope(
        self,
        scope: EventScope,
        event: Any,
        agent_id: str | uuid.UUID | None = None,
        conversation_id: ConversationID  | str | None = None,
    ) -> None:
        """发布事件（向后兼容的API）

        Args:
            scope: 事件作用域（已废弃，仅用于向后兼容）
            event: 要发布的事件
            agent_id: Agent ID
            conversation_id: 会话ID
        """
        logger.warning(
            "publish_with_scope is deprecated, please use publish() directly"
        )
        self.publish(event, conversation_id, agent_id)


# ===== 便捷工具函数 =====


def create_function_consumer(
    callback: Callable[[Any], None],
    conversation_id: ConversationID |   None = None,
    agent_id: str | uuid.UUID | None = None,
    event_types: list[type[Any]] | None = None,
) -> EventConsumer:
    """创建基于函数的消费者（便捷工具）

    Args:
        callback: 事件处理回调函数
        conversation_id: 会话ID（类似Topic），None表示全局
        agent_id: Agent ID（类似Tag），None表示接收该会话所有Agent的事件
        event_types: 关心的事件类型列表

    Returns:
        EventConsumer实例
    """

    class FunctionConsumer(EventConsumer):
        def on_event(self, event: Any) -> None:
            callback(event)

    return FunctionConsumer(conversation_id, agent_id, event_types)
