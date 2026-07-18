import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from common.storage.event_log.event_store import EventLog, create_event_log
from common.utils.async_utils import AsyncCallbackWrapper
from common.utils.cipher import Cipher
from common.utils.common import ExecutionStatus
from sdk.conversation.snapshot import ConversationStateMeta
from server.models import  EventPage, EventSortOrder, StartConversationRequest
from common.models import ConfirmationResponseRequest
from server.pub_sub import PubSub, Subscriber
from server.utils import utc_now
from sdk import LLM, Agent, AgentBase, Event, Message, get_logger
from sdk.conversation.factory import ConversationFactory
from sdk.conversation.impl.conversation_impl import LocalConversation
from sdk.conversation.persistence import FileConversationPersistence
from sdk.secret.secret_registry import SecretValue
from sdk.conversation.state import ConversationState
from sdk.conversation.visualizer.default import DefaultConversationVisualizer
from sdk.event import AgentErrorEvent
from sdk.event.conversation_state import ConversationStateUpdateEvent
from sdk.event.llm_completion_log import LLMCompletionLogEvent
from sdk.security.analyzer import SecurityAnalyzerBase
from sdk.security.confirmation_policy import ConfirmationPolicyBase
from sdk.workspace import LocalWorkspace

logger = get_logger(__name__)


@dataclass
class EventService:
    """
    Event service for a conversation running locally, analogous to a conversation
    in the SDK. Async mostly for forward compatibility
    """ 
    
    conversations_dir: Path
    cipher: Cipher | None = None

    meta_data: ConversationStateMeta | None = field(default=None)
    _conversation: LocalConversation | None = field(default=None, init=False)
    _pub_sub: PubSub[Event] = field(default_factory=lambda: PubSub[Event](), init=False)
    _run_task: asyncio.Task | None = field(default=None, init=False)
    _run_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _callback_wrapper: AsyncCallbackWrapper | None = field(default=None, init=False)
    _main_loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _persistence: FileConversationPersistence | None = field(default=None, init=False) 

    @property
    def conversation_dir(self):
        return self.conversations_dir
 
 

    def get_conversation(self):
        if not self._conversation:
            raise ValueError("inactive_service")
        return self._conversation

    def _get_event_sync(self, event_id: str) -> Event | None:
        """Private sync function to get event with state lock."""
        if not self._conversation:
            raise ValueError("inactive_service")
        with self._conversation._state as state:
            index = state.events.get_index(event_id)
            return state.events[index]
    
    # 检索服务需要改写-走common
    async def get_event(self, event_id: str) -> Event | None:
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_event_sync, event_id)

    def _search_events_sync(
        self,
        page_id: str | None = None,
        limit: int = 100,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> EventPage:
        """Private sync function to search events with state lock."""
        if not self._conversation:
            raise ValueError("inactive_service")

        timestamp_gte_str = timestamp__gte.isoformat() if timestamp__gte else None
        timestamp_lt_str = timestamp__lt.isoformat() if timestamp__lt else None

        all_events = []
        with self._conversation._state as state:
            for event in state.events:
                if kind is not None:
                    event_kind = f"{event.__class__.__module__}.{event.__class__.__name__}"
                    if event_kind != kind:
                        continue

                if source is not None and event.source != source:
                    continue

                if body is not None and not self._event_matches_body(event, body):
                    continue

                if timestamp_gte_str is not None and event.timestamp < timestamp_gte_str:
                    continue
                if timestamp_lt_str is not None and event.timestamp >= timestamp_lt_str:
                    continue

                all_events.append(event)

        if sort_order == EventSortOrder.TIMESTAMP:
            all_events.sort(key=lambda x: x.timestamp)
        elif sort_order == EventSortOrder.TIMESTAMP_DESC:
            all_events.sort(key=lambda x: x.timestamp, reverse=True)

        start_index = 0
        if page_id:
            for i, event in enumerate(all_events):
                if event.id == page_id:
                    start_index = i
                    break

        items = []
        next_page_id = None
        for i in range(start_index, len(all_events)):
            if len(items) >= limit:
                next_page_id = all_events[i].id if i < len(all_events) else None
                break
            items.append(all_events[i])

        return EventPage(items=items, next_page_id=next_page_id)

    async def search_events(
        self,
        page_id: str | None = None,
        limit: int = 100,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> EventPage:
        
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._search_events_sync,
            page_id, limit, kind, source, body,
            sort_order, timestamp__gte, timestamp__lt
        )

    def _count_events_sync(
        self,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> int:
        """Private sync function to count events with state lock."""
        if not self._conversation:
            raise ValueError("inactive_service")

        timestamp_gte_str = timestamp__gte.isoformat() if timestamp__gte else None
        timestamp_lt_str = timestamp__lt.isoformat() if timestamp__lt else None

        count = 0
        with self._conversation._state as state:
            for event in state.events:
                if kind is not None:
                    event_kind = f"{event.__class__.__module__}.{event.__class__.__name__}"
                    if event_kind != kind:
                        continue

                if source is not None and event.source != source:
                    continue

                if body is not None and not self._event_matches_body(event, body):
                    continue

                if timestamp_gte_str is not None and event.timestamp < timestamp_gte_str:
                    continue
                if timestamp_lt_str is not None and event.timestamp >= timestamp_lt_str:
                    continue

                count += 1

        return count

    async def count_events(
        self,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> int:
        """Count events matching the given filters."""
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._count_events_sync,
            kind, source, body, timestamp__gte, timestamp__lt
        )

    def _event_matches_body(self, event: Event, body: str) -> bool:
        """Check if event's message content matches body filter (case-insensitive)."""
        from sdk.event.llm_convertible.message import MessageEvent
        from sdk.llm.message import content_to_str

        if not isinstance(event, MessageEvent):
            return False

        text_parts = content_to_str(event.llm_message.content)
        if event.extended_content:
            text_parts.extend(content_to_str(event.extended_content))
        if event.reasoning_content:
            text_parts.append(event.reasoning_content)

        full_text = " ".join(text_parts).lower()
        return body.lower() in full_text

    async def batch_get_events(self, event_ids: list[str]) -> list[Event | None]:
        """Given a list of ids, get events (Or none for any which were not found)"""
        results = await asyncio.gather(*[self.get_event(eid) for eid in event_ids])
        return results

    async def send_message(self, message: Message, run: bool = False):
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._conversation.send_message, message)

        if run:
            with self._conversation.state as state:
                run = state.execution_status != ExecutionStatus.RUNNING

        if run:
            conversation = self._conversation

            async def _run_with_error_handling():
                try:
                    await loop.run_in_executor(None, conversation.run)
                except Exception:
                    logger.exception("Error during conversation run from send_message")

            loop.create_task(_run_with_error_handling())

    async def subscribe_to_events(self, subscriber: Subscriber[Event]) -> UUID:
        subscriber_id = self._pub_sub.subscribe(subscriber)

        if self._conversation:
            state = self._conversation._state
            with state:
                state_update_event = ConversationStateUpdateEvent.from_conversation_state(state)

            try:
                await subscriber(state_update_event)
            except Exception as e:
                logger.error(f"Error sending initial state to subscriber {subscriber_id}: {e}")

        return subscriber_id

    async def unsubscribe_from_events(self, subscriber_id: UUID) -> bool:
        return self._pub_sub.unsubscribe(subscriber_id)

    def _emit_event_from_thread(self, event: Event) -> None:
        if self._main_loop and self._main_loop.is_running() and self._conversation:
            conversation = self._conversation

            def locked_on_event():
                with conversation._state:
                    conversation.publish_event(event)

            self._main_loop.run_in_executor(None, locked_on_event)

    def _setup_llm_log_streaming(self, agent: AgentBase) -> None:
        for llm in agent.get_all_llms():
            if not llm.log_completions:
                continue

            usage_id = llm.usage_id
            model_name = llm.model

            def log_callback(filename: str, log_data: str, uid=usage_id, model=model_name):
                event = LLMCompletionLogEvent(
                    filename=filename,
                    log_data=log_data,
                    model_name=model,
                    usage_id=uid,
                )
                self._emit_event_from_thread(event)

            llm.telemetry.set_log_completions_callback(log_callback)

    def _setup_stats_streaming(self, agent: AgentBase) -> None:
        def stats_callback():
            if not self._conversation:
                return
            state = self._conversation._state
            with state:
                event = ConversationStateUpdateEvent(key="stats", value=state.stats)
            self._emit_event_from_thread(event)

        for llm in agent.get_all_llms():
            llm.telemetry.set_stats_update_callback(stats_callback)

    async def start(self):
        self._main_loop = asyncio.get_running_loop()
        # 为什么要创建本地目录？ 不需要，倒是workspace才应该需要。其余的都走本地或远程存储。
        #self.conversation_dir.mkdir(parents=True, exist_ok=True)
        
        workspace = self.meta_data.workspace
        assert isinstance(workspace, LocalWorkspace)
       
        self._persistence = FileConversationPersistence(conversation_id=self.meta_data.id, cipher=self.cipher)
     
        

        self._callback_wrapper = AsyncCallbackWrapper(self._pub_sub, loop=self._main_loop)
        enable_visualizer = os.getenv("ENABLE_VISUALIZER", default=False)

        self._conversation = ConversationFactory(conversation_id=self.meta_data.id, persistence=self._persistence).create(
            meta_data=self.meta_data,
            callbacks=[self._callback_wrapper],
            visualizer=DefaultConversationVisualizer if enable_visualizer else None,
            cipher=self.cipher,
        )
        self._setup_llm_log_streaming(self._conversation.agent)
        self._setup_stats_streaming(self._conversation.agent)

        state = self._conversation.state
        if state.execution_status == ExecutionStatus.RUNNING:
            state.set_execution_status(ExecutionStatus.ERROR)
            unmatched_actions = state.main_agent_state.get_unmatched_actions(self._conversation.events)
            if unmatched_actions:
                first_action = unmatched_actions[0]
                error_event = AgentErrorEvent(
                    tool_name=first_action.tool_name,
                    tool_call_id=first_action.tool_call_id,
                    error=(
                        "A restart occurred while this tool was in progress. "
                        "This may indicate a fatal memory error or system crash. "
                        "The tool execution was interrupted and did not complete."
                    ),
                )
                self._conversation.publish_event(error_event)

        await self._publish_state_update()

    async def run(self):
        if not self._conversation:
            raise ValueError("inactive_service")

        async with self._run_lock:
            with self._conversation._state as state:
                if state.execution_status == ExecutionStatus.RUNNING:
                    raise ValueError("conversation_already_running")

            if self._run_task is not None and not self._run_task.done():
                raise ValueError("conversation_already_running")

            conversation = self._conversation
            loop = asyncio.get_running_loop()

            async def _run_and_publish():
                try:
                    await loop.run_in_executor(None, conversation.run)
                except Exception:
                    logger.exception("Error during conversation run")
                finally:
                    if self._callback_wrapper:
                        await loop.run_in_executor(
                            None, self._callback_wrapper.wait_for_pending, 30.0
                        )
                    self._run_task = None
                    await self._publish_state_update()

            self._run_task = asyncio.create_task(_run_and_publish())

    async def respond_to_confirmation(self, request: ConfirmationResponseRequest):
        if request.accept:
            try:
                await self.run()
            except ValueError as e:
                if str(e) == "conversation_already_running":
                    logger.debug("Confirmation accepted but conversation already running")
                else:
                    raise
        else:
            await self.reject_pending_actions(request.reason)

    async def reject_pending_actions(self, reason: str):
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._conversation.reject_pending_actions, reason
        )

    async def pause(self):
        if self._conversation:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._conversation.pause)
            await self._publish_state_update()

    async def update_secrets(self, secrets: dict[str, SecretValue]):
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._conversation.update_secrets, secrets)

    async def set_confirmation_policy(self, policy: ConfirmationPolicyBase):
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._conversation.set_confirmation_policy, policy
        )
        if self.meta_data is not None:
            self.meta_data.confirmation_policy = policy

    async def set_security_analyzer(self, security_analyzer: SecurityAnalyzerBase | None):
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._conversation.set_security_analyzer, security_analyzer
        )
        if self.meta_data is not None:
            self.meta_data.security_analyzer = security_analyzer

    async def close(self):
        await self._pub_sub.close()
        if self._conversation:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._conversation.close)

    async def generate_title(self, llm: LLM | None = None, max_length: int = 50) -> str:
        if not self._conversation:
            raise ValueError("inactive_service")

        resolved_llm = llm
        if llm is not None:
            usage_id = llm.usage_id
            try:
                resolved_llm = self._conversation.llm_registry.get(usage_id)
            except KeyError:
                self._conversation.llm_registry.add(llm)
                resolved_llm = llm

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._conversation.generate_title, resolved_llm, max_length
        )

    async def ask_agent(self, question: str) -> str:
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._conversation.ask_agent, question)

    async def condense(self) -> None:
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._conversation.condense)

    async def get_state(self) -> ConversationState:
        if not self._conversation:
            raise ValueError("inactive_service")
        return self._conversation._state

    async def _publish_state_update(self):
        if not self._conversation:
            return

        state = self._conversation._state
        with state:
            state_update_event = ConversationStateUpdateEvent.from_conversation_state(state)
        await self._pub_sub(state_update_event)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.meta_data:
            self._persistence.save_meta(self.meta_data)
        if self._conversation:
            self._persistence.save_snapshot(self._conversation.state.to_snapshot())
        await self.close()

    def is_open(self) -> bool:
        return bool(self._conversation)





