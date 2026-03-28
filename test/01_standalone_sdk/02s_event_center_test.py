"""事件中心使用示例（优化版 - Topic+Tag语义）

本文档展示如何使用优化后的EventCenter，支持类似MQ的Topic+Tag过滤机制。
"""

from sdk.event.base import Event
from sdk.event.event_center import (
    EventCenter,
    EventConsumer,
    create_function_consumer,
)
from sdk.event.llm_convertible.system import SystemPromptEvent
from sdk.llm.message import TextContent


# ===== 示例1：全局消费者（接收所有事件） =====


def example_global_consumer():
    """全局消费者：不设置conversation_id和agent_id，接收所有事件"""

    event_center = EventCenter()

    # 定义全局监控消费者
    class GlobalMonitorConsumer(EventConsumer):
        def on_event(self, event: Event):
            print(f"[GLOBAL MONITOR] Received event: {event.id}")

    # 订阅全局事件（不设置conversation_id和agent_id）
    monitor_consumer = GlobalMonitorConsumer()
    event_center.subscribe(monitor_consumer)

    class GlobalMonitorConsumers(EventConsumer):
        def on_event(self, event: Event):
            print(f"[GLOBAL MONITOR] Received event: {event.id}")

    # 订阅全局事件（不设置conversation_id和agent_id）
    monitor_consumer = GlobalMonitorConsumers(event_types=[Event])
    event_center.subscribe(monitor_consumer)
    event = SystemPromptEvent(
        source="agent", system_prompt=TextContent(text="test demos"), tools=[]
    )
    event_center.publish(event)

    # 发布事件
    # event = ...
    # event_center.publish(event, conversation_id="conv_001", agent_id="agent_001")
    # 全局消费者会收到这个事件


# ===== 示例2：会话级消费者（接收该会话所有Agent的事件） =====


def example_conversation_consumer():
    """会话级消费者：只设置conversation_id，接收该会话所有Agent的事件"""

    event_center = EventCenter()

    # 定义会话级消费者
    class ConversationStateConsumer(EventConsumer):
        def on_event(self, event: Event):
            print(
                f"[CONVERSATION] Received event from conversation {self.conversation_id}: {event.id}"
            )

    # 订阅会话级事件（只设置conversation_id）
    conv_consumer = ConversationStateConsumer(conversation_id="conv_001")
    event_center.subscribe(conv_consumer)

    # 发布事件
    # event1 = ...
    # event_center.publish(event1, conversation_id="conv_001", agent_id="agent_001")
    # 会话消费者会收到（因为conversation_id匹配）

    # event2 = ...
    # event_center.publish(event2, conversation_id="conv_001", agent_id="agent_002")
    # 会话消费者也会收到（因为conversation_id匹配，不管agent_id）

    # event3 = ...
    # event_center.publish(event3, conversation_id="conv_002", agent_id="agent_001")
    # 会话消费者不会收到（因为conversation_id不匹配）


# ===== 示例3：Agent级消费者（只接收特定Agent的事件） =====


def example_agent_consumer():
    """Agent级消费者：同时设置conversation_id和agent_id，只接收特定Agent的事件"""

    event_center = EventCenter()

    # 定义Agent级消费者
    class AgentMetricsConsumer(EventConsumer):
        def on_event(self, event: Event):
            print(f"[AGENT] Agent {self.agent_id} received event: {event.id}")

    # 订阅Agent级事件（同时设置conversation_id和agent_id）
    agent_consumer = AgentMetricsConsumer(
        conversation_id="conv_001", agent_id="agent_001"
    )
    event_center.subscribe(agent_consumer)

    # 发布事件
    # event1 = ...
    # event_center.publish(event1, conversation_id="conv_001", agent_id="agent_001")
    # Agent消费者会收到（conversation_id和agent_id都匹配）

    # event2 = ...
    # event_center.publish(event2, conversation_id="conv_001", agent_id="agent_002")
    # Agent消费者不会收到（agent_id不匹配）

    # event3 = ...
    # event_center.publish(event3, conversation_id="conv_002", agent_id="agent_001")
    # Agent消费者不会收到（conversation_id不匹配）


# ===== 示例4：混合场景（多级消费者共存） =====


def example_mixed_consumers():
    """演示全局、会话级、Agent级消费者共存的场景"""

    event_center = EventCenter()

    # 1. 全局消费者：监控所有事件
    global_consumer = create_function_consumer(
        callback=lambda e: print(f"[GLOBAL] {e.id}")
    )
    event_center.subscribe(global_consumer)

    # 2. 会话级消费者：监控conv_001的所有事件
    conv_consumer = create_function_consumer(
        callback=lambda e: print(f"[CONV] {e.id}"), conversation_id="conv_001"
    )
    event_center.subscribe(conv_consumer)

    # 3. Agent级消费者：只监控conv_001中agent_001的事件
    agent_consumer = create_function_consumer(
        callback=lambda e: print(f"[AGENT] {e.id}"),
        conversation_id="conv_001",
        agent_id="agent_001",
    )
    event_center.subscribe(agent_consumer)

    # 发布事件：conversation_id="conv_001", agent_id="agent_001"
    # event = ...
    # event_center.publish(event, conversation_id="conv_001", agent_id="agent_001")
    # 输出：
    # [GLOBAL] event_id
    # [CONV] event_id
    # [AGENT] event_id
    # （三个消费者都会收到）


# ===== 示例5：事件类型过滤 =====


def example_event_type_filtering():
    """结合Topic+Tag和事件类型过滤"""

    from sdk.event.llm_convertible import ActionEvent

    event_center = EventCenter()

    # 只接收conv_001中agent_001的ActionEvent
    class ActionConsumer(EventConsumer):
        def on_event(self, event: Event):
            print(f"[ACTION] {event.id}")

    action_consumer = ActionConsumer(
        conversation_id="conv_001",
        agent_id="agent_001",
        event_types=[ActionEvent],  # 只接收ActionEvent
    )
    event_center.subscribe(action_consumer)

    # 发布ActionEvent - 会被接收
    # action_event = ActionEvent(...)
    # event_center.publish(action_event, conversation_id="conv_001", agent_id="agent_001")

    # 发布MessageEvent - 会被过滤掉
    # message_event = MessageEvent(...)
    # event_center.publish(message_event, conversation_id="conv_001", agent_id="agent_001")


# ===== 示例6：SubAgent场景 =====


def example_subagent_scenario():
    """演示MainAgent和SubAgent的事件订阅"""

    event_center = EventCenter()

    # MainAgent订阅会话级事件（接收所有SubAgent的事件）
    class MainAgentConsumer(EventConsumer):
        def on_event(self, event: Event):
            print(f"[MAIN AGENT] Received event from conversation: {event.id}")

    main_consumer = MainAgentConsumer(conversation_id="conv_001")
    event_center.subscribe(main_consumer)

    # SubAgent1订阅自己的Agent级事件
    class SubAgent1Consumer(EventConsumer):
        def on_event(self, event: Event):
            print(f"[SUB AGENT 1] Received my event: {event.id}")

    sub1_consumer = SubAgent1Consumer(
        conversation_id="conv_001", agent_id="sub_agent_001"
    )
    event_center.subscribe(sub1_consumer)

    # SubAgent2订阅自己的Agent级事件
    class SubAgent2Consumer(EventConsumer):
        def on_event(self, event: Event):
            print(f"[SUB AGENT 2] Received my event: {event.id}")

    sub2_consumer = SubAgent2Consumer(
        conversation_id="conv_001", agent_id="sub_agent_002"
    )
    event_center.subscribe(sub2_consumer)

    # SubAgent1发布事件
    # event = ...
    # event_center.publish(event, conversation_id="conv_001", agent_id="sub_agent_001")
    # 输出：
    # [MAIN AGENT] Received event from conversation: event_id
    # [SUB AGENT 1] Received my event: event_id
    # （MainAgent和SubAgent1都会收到，SubAgent2不会收到）


# ===== 示例7：动态订阅和取消订阅 =====


def example_dynamic_subscription():
    """演示动态订阅和取消订阅"""

    event_center = EventCenter()

    # 创建消费者
    consumer = create_function_consumer(
        callback=lambda e: print(f"Event: {e.id}"),
        conversation_id="conv_001",
        agent_id="agent_001",
    )

    # 订阅
    event_center.subscribe(consumer)

    # 检查消费者数量
    count = event_center.get_consumer_count(
        conversation_id="conv_001", agent_id="agent_001"
    )
    print(f"Consumer count: {count}")  # 输出: 1

    # 取消订阅
    event_center.unsubscribe(consumer)

    # 再次检查
    count = event_center.get_consumer_count(
        conversation_id="conv_001", agent_id="agent_001"
    )
    print(f"Consumer count: {count}")  # 输出: 0


# ===== 示例8：清理消费者 =====


def example_cleanup():
    """演示清理消费者的不同方式"""

    event_center = EventCenter()

    # 添加多个消费者
    global_consumer = create_function_consumer(
        callback=lambda e: print(f"Global: {e.id}")
    )
    event_center.subscribe(global_consumer)

    conv_consumer = create_function_consumer(
        callback=lambda e: print(f"Conv: {e.id}"), conversation_id="conv_001"
    )
    event_center.subscribe(conv_consumer)

    agent_consumer = create_function_consumer(
        callback=lambda e: print(f"Agent: {e.id}"),
        conversation_id="conv_001",
        agent_id="agent_001",
    )
    event_center.subscribe(agent_consumer)

    # 1. 清空特定Agent的消费者
    event_center.clear_agent("conv_001", "agent_001")

    # 2. 清空整个会话的消费者（包括会话级和所有Agent级）
    event_center.clear_conversation("conv_001")

    # 3. 清空所有消费者
    event_center.clear_all()


# ===== 示例9：与ConversationState集成 =====


def example_integration_with_conversation_state():
    """演示如何在ConversationState中使用优化后的EventCenter"""

    # 在ConversationState中添加事件中心
    # class ConversationState:
    #     _event_center: EventCenter = PrivateAttr(default_factory=EventCenter)
    #
    #     def __init__(self, conversation_id, ...):
    #         super().__init__(...)
    #         self.conversation_id = conversation_id
    #
    #         # 订阅会话级事件（接收该会话所有Agent的事件）
    #         state_consumer = create_function_consumer(
    #             callback=self._on_state_change_event,
    #             conversation_id=str(self.conversation_id),
    #             event_types=[ConversationStateUpdateEvent]
    #         )
    #         self._event_center.subscribe(state_consumer)
    #
    #     def add_event(self, event: Event, agent_id: Optional[str] = None):
    #         # 1. 持久化到EventLog
    #         self._events.append(event)
    #
    #         # 2. 发布到事件中心
    #         self._event_center.publish(
    #             event,
    #             conversation_id=str(self.conversation_id),
    #             agent_id=agent_id  # 可选的agent_id
    #         )
    pass


# ===== 示例10：调试和监控 =====


def example_debugging():
    """演示调试和监控功能"""

    event_center = EventCenter()

    # 添加多个消费者
    event_center.subscribe(
        create_function_consumer(callback=lambda e: print(f"Global: {e.id}"))
    )

    event_center.subscribe(
        create_function_consumer(
            callback=lambda e: print(f"Conv: {e.id}"), conversation_id="conv_001"
        )
    )

    event_center.subscribe(
        create_function_consumer(
            callback=lambda e: print(f"Agent: {e.id}"),
            conversation_id="conv_001",
            agent_id="agent_001",
        )
    )

    # 获取所有订阅键
    keys = event_center.get_all_subscription_keys()
    print(f"Subscription keys: {keys}")
    # 输出: ['global', 'conv:conv_001', 'conv:conv_001:agent:agent_001']

    # 获取各级消费者数量
    global_count = event_center.get_consumer_count()
    print(f"Global consumers: {global_count}")  # 输出: 1

    conv_count = event_center.get_consumer_count(conversation_id="conv_001")
    print(f"Conversation consumers: {conv_count}")  # 输出: 1

    agent_count = event_center.get_consumer_count(
        conversation_id="conv_001", agent_id="agent_001"
    )
    print(f"Agent consumers: {agent_count}")  # 输出: 1


# ===== 对比：优化前 vs 优化后 =====


def example_comparison():
    """对比优化前后的API"""

    event_center = EventCenter()

    # ===== 优化前（基于Scope） =====
    # class OldConsumer(EventConsumer):
    #     def __init__(self):
    #         super().__init__(consumer_id="conv_001")
    #
    # consumer = OldConsumer()
    # event_center.subscribe(EventScope.CONVERSATION, consumer)
    # event_center.publish(EventScope.CONVERSATION, event, conversation_id="conv_001")

    # ===== 优化后（基于Topic+Tag） =====
    class NewConsumer(EventConsumer):
        def on_event(self, event):
            pass

    # 会话级消费者
    consumer = NewConsumer(conversation_id="conv_001")
    event_center.subscribe(consumer)  # 不再需要scope参数

    # event = ...
    # event_center.publish(event, conversation_id="conv_001")  # 简化的API

    # Agent级消费者
    agent_consumer = NewConsumer(conversation_id="conv_001", agent_id="agent_001")
    event_center.subscribe(agent_consumer)

    # event = ...
    # event_center.publish(event, conversation_id="conv_001", agent_id="agent_001")


if __name__ == "__main__":
    print("=== EventCenter Usage Examples (Optimized) ===\n")

    print("1. Global Consumer")
    example_global_consumer()

    print("\n2. Conversation Consumer")
    example_conversation_consumer()

    print("\n3. Agent Consumer")
    example_agent_consumer()

    print("\n4. Mixed Consumers")
    example_mixed_consumers()

    print("\n5. Event Type Filtering")
    example_event_type_filtering()

    print("\n6. SubAgent Scenario")
    example_subagent_scenario()

    print("\n7. Dynamic Subscription")
    example_dynamic_subscription()

    print("\n8. Cleanup")
    example_cleanup()

    print("\n9. Integration with ConversationState")
    example_integration_with_conversation_state()

    print("\n10. Debugging")
    example_debugging()

    print("\n11. Comparison")
    example_comparison()
