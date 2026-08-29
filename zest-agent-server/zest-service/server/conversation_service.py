import asyncio
import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from common.utils.common import ConversationID
from common.query.query_models import ConversationStateView, TodoItem
from sdk.conversation.persistence import FileConversationPersistence
import httpx

from sdk import LLM, TextContent, Tool
from sdk.agent.agent import Agent 
from sdk.agent.agent_spec import AgentContextSpec
from sdk.context.skills.skill import Skill
from sdk.conversation.snapshot import ConversationStateMeta
from sdk.memory.memory_manager import get_memory_manager
from server.config import Config, WebhookSpec, get_default_config

from server.event_service import EventService

from server.models import (
    ConversationAccessInfo,
    ConversationInfo,
    ConversationPage,
    ConversationSortOrder,
    SendMessageRequest,
    StartConversationRequest,
)
from server.pub_sub import Subscriber
from server.server_details_router import update_last_execution_time
from server.utils import safe_rmtree
from sdk import Event, Message
from sdk.conversation.state import (
    ExecutionStatus,
    ConversationState,
)
from common.utils.cipher import Cipher
from server.model import ConversationCreatePayload
from tools.preset.default import get_default_agent, get_default_tools, register_memory_tools, register_sale_tools


logger = logging.getLogger(__name__)


def _build_conversation_access_info(
    conversation_id: ConversationID,
    config: Config,
) -> ConversationAccessInfo:
    host = config.agent_server_host
    if host == "0.0.0.0":
        host = "127.0.0.1"

    base_url = f"http://{host}:{config.agent_server_port}/api"
    websocket_url = f"ws://{host}:{config.agent_server_port}/sockets/events/{conversation_id}"
    if config.session_api_keys:
        websocket_url = f"{websocket_url}?session_api_key={config.session_api_keys[0]}"

    return ConversationAccessInfo(
        conversation_id=str(conversation_id),
        base_url=base_url,
        events_url=f"{base_url}/conversations/{conversation_id}/events",
        websocket_url=websocket_url,
        session_api_key=config.session_api_keys[0] if config.session_api_keys else None,
    )


def _compose_conversation_info(
    meta_data: ConversationStateMeta,
    state: ConversationState,
    access: ConversationAccessInfo | None = None,
) -> ConversationInfo:
    return ConversationInfo(
        **state.model_dump(),
        access=access,
    )


def _resolve_execution_status(
    execution_status: ExecutionStatus,
    agent_state: ConversationState | object | None,
) -> ExecutionStatus:
    if agent_state is not None and hasattr(agent_state, "execution_status"):
        return agent_state.execution_status
    logger.error("Missing main_agent_state while resolving historical execution status")
    return ExecutionStatus.ERROR


@dataclass
class ConversationService:
    """
    Conversation service which stores to a local file store. When the context starts
    all event_services are loaded into memory, and stored when it stops.
    """

    conversations_dir: Path = field()
    webhook_specs: list[WebhookSpec] = field(default_factory=list)
    session_api_key: str | None = field(default=None)
    cipher: Cipher | None = None
    _event_services: dict[UUID, EventService] | None = field(default=None, init=False)
    _conversation_webhook_subscribers: list["ConversationWebhookSubscriber"] = field(
        default_factory=list, init=False
    )

    async def get_conversation(self, conversation_id: ConversationID) -> ConversationInfo | None:
        if self._event_services is None:
            raise ValueError("inactive_service")
        event_service = self._event_services.get(conversation_id)
        if event_service is None:
            return None
        state = await event_service.get_state()
        access = _build_conversation_access_info(conversation_id, get_default_config())
        return _compose_conversation_info(event_service.meta_data, state, access)

    async def get_state_view(self, conversation_id: ConversationID) -> ConversationStateView | None:
        """Return a lightweight state view.
        Active conversations read from in-memory state (most up-to-date).
        Historical conversations fall back to FileConversationPersistence.
        """
        if self._event_services is None:
            raise ValueError("inactive_service")

        event_service = self._event_services.get(conversation_id)
        if event_service is not None:
            state = await event_service.get_state()
            meta = event_service.meta_data
            agent_state = state.main_agent_state if state.main_agent_state else None
            todos = [
                TodoItem(content=t.get("content", ""), status=t.get("status", "pending"))
                for t in (agent_state.todos if agent_state else [])
            ]
            exec_status = state.execution_status
            return ConversationStateView(
                conversation_id=str(conversation_id),
                execution_status=exec_status.value if hasattr(exec_status, "value") else str(exec_status),
                task_description=agent_state.task_description if agent_state else "",
                todos=todos,
                agent_id=str(meta.agent.id) if meta.agent else None,
            )

        # Historical: read from persistence
        persistence = FileConversationPersistence(conversation_id=conversation_id)
        if not persistence.has_snapshot():
            return None
        snapshot = persistence.load_snapshot()
        if snapshot is None:
            return None
        meta = persistence.load_meta() if persistence.has_meta() else None
        agent_state = snapshot.main_agent_state if snapshot.main_agent_state else None
        todos = [
            TodoItem(content=t.get("content", ""), status=t.get("status", "pending"))
            for t in (agent_state.todos if agent_state else [])
        ]
        exec_status = _resolve_execution_status(snapshot.execution_status, agent_state)
        return ConversationStateView(
            conversation_id=str(conversation_id),
            execution_status=exec_status.value if hasattr(exec_status, "value") else str(exec_status),
            task_description=agent_state.task_description if agent_state else "",
            todos=todos,
            agent_id=str(meta.agent.id) if meta and meta.agent else None,
        )


    async def search_conversations(
        self,
        page_id: str | None = None,
        limit: int = 100,
        execution_status: ExecutionStatus | None = None,
        sort_order: ConversationSortOrder = ConversationSortOrder.CREATED_AT_DESC,
    ) -> ConversationPage:
        if self._event_services is None:
            raise ValueError("inactive_service")

        # Collect all conversations with their info
        all_conversations = []
        for id, event_service in self._event_services.items():
            state = await event_service.get_state()
            conversation_info = _compose_conversation_info(event_service.meta_data, state)
            # Apply status filter if provided
            if (
                execution_status is not None
                and conversation_info.execution_status != execution_status
            ):
                continue

            all_conversations.append((id, conversation_info))

        # Sort conversations based on sort_order
        if sort_order == ConversationSortOrder.CREATED_AT:
            all_conversations.sort(key=lambda x: x[0])
        elif sort_order == ConversationSortOrder.CREATED_AT_DESC:
            all_conversations.sort(key=lambda x: x[0], reverse=True)
        elif sort_order == ConversationSortOrder.UPDATED_AT:
            all_conversations.sort(key=lambda x: x[0])
        elif sort_order == ConversationSortOrder.UPDATED_AT_DESC:
            all_conversations.sort(key=lambda x: x[0], reverse=True)

        # Handle pagination
        items = []
        start_index = 0

        # Find the starting point if page_id is provided
        if page_id:
            for i, (id, _) in enumerate(all_conversations):
                if id.hex == page_id:
                    start_index = i
                    break

        # Collect items for this page
        next_page_id = None
        for i in range(start_index, len(all_conversations)):
            if len(items) >= limit:
                # We have more items, set next_page_id
                if i < len(all_conversations):
                    next_page_id = all_conversations[i][0].hex
                break
            items.append(all_conversations[i][1])

        return ConversationPage(items=items, next_page_id=next_page_id)

    async def count_conversations(
        self,
        execution_status: ExecutionStatus | None = None,
    ) -> int:
        """Count conversations matching the given filters."""
        if self._event_services is None:
            raise ValueError("inactive_service")

        count = 0
        for event_service in self._event_services.values():
            state = await event_service.get_state()

            # Apply status filter if provided
            if (
                execution_status is not None
                and state.execution_status != execution_status
            ):
                continue

            count += 1

        return count

    async def batch_get_conversations(
        self, conversation_ids: list[UUID]
    ) -> list[ConversationInfo | None]:
        """Given a list of ids, get a batch of conversation info, returning
        None for any that were not found."""
        results = await asyncio.gather(
            *[
                self.get_conversation(conversation_id)
                for conversation_id in conversation_ids
            ]
        )
        return results

    async def _notify_conversation_webhooks(self, conversation_info: ConversationInfo):
        """Notify all conversation webhook subscribers about conversation changes."""
        if not self._conversation_webhook_subscribers:
            return

        # Send notifications to all conversation webhook subscribers in the background
        async def _notify_and_log_errors():
            results = await asyncio.gather(
                *[
                    subscriber.post_conversation_info(conversation_info)
                    for subscriber in self._conversation_webhook_subscribers
                ],
                return_exceptions=True,  # Don't fail if one webhook fails
            )

            # Log any exceptions that occurred
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    subscriber = self._conversation_webhook_subscribers[i]
                    logger.error(
                        (
                            f"Failed to notify conversation webhook "
                            f"{subscriber.spec.base_url}: {result}"
                        ),
                        exc_info=result,
                    )

        # Create task to run in background without awaiting

        asyncio.create_task(_notify_and_log_errors())



    # Write Methods



    def _convert_confirmation_policy(self, payload):
        from sdk.security.confirmation_policy import (
            AlwaysConfirm,
            ConfirmRiskyAndAction,
            NeverConfirm,
        )
        from sdk.security.risk import SecurityRisk

        if payload is None or payload.mode == "never":
            return NeverConfirm()
        if payload.mode == "always":
            return AlwaysConfirm()
        return ConfirmRiskyAndAction(
            threshold=SecurityRisk[payload.threshold or "HIGH"],
            confirm_unknown=payload.confirm_unknown,
            need_confirm_name=payload.need_confirm_tools,
        )

    def convert_create_payload(
        self, payload: ConversationCreatePayload
    ) -> StartConversationRequest:
        from sdk.workspace import LocalWorkspace

        llm_payload = payload.agent_config.llm
        llm = LLM(
            model=llm_payload.model,
            base_url=llm_payload.base_url,
            api_key=llm_payload.api_key,
            usage_id=llm_payload.usage_id,
        )
        
        skills = [
            Skill(
                name=skill.name,
                content=skill.content,
                description=skill.description,
                source=skill.source,
                trigger=skill.trigger,
            )
            for skill in payload.agent_config.skills
        ]
        agent_context_spec = AgentContextSpec(skills=skills )
        tools = [Tool(name=tool_name) for tool_name in payload.agent_config.selected_tool_names]
        if not tools:
            tools = tools = get_default_tools(# Disable browser tools in CLI mode
                                              enable_browser=False)
        register_memory_tools(tools, enable_base_memory=payload.enable_base_memory, enable_experience_memory=payload.enable_experience_memory)
        # 临时测试，添加售后tools
        register_sale_tools(tools)
        agent_kwargs = {
            "llm": llm,
            "tools": tools,
            "agent_context_spec": agent_context_spec,
            "custom_system_prompt": payload.agent_config.custom_system_prompt,
            "system_prompt_kwargs": payload.agent_config.system_prompt_kwargs,
            "include_default_tools": [],
        }
        if payload.agent_config.subagent_configs:
            agent_kwargs["subagent_spec"] = payload.agent_config.subagent_configs
        agent = Agent(**agent_kwargs)

        initial_message = None
        if payload.initial_message:
            initial_message = SendMessageRequest(
                role=payload.initial_message.role,
                content=[TextContent(text=payload.initial_message.text)],
                run=payload.initial_message.run,
            )

        return StartConversationRequest(
            agent=agent,
            workspace=LocalWorkspace(working_dir=payload.workspace.working_dir),
            conversation_id=payload.conversation_id,
            user_id=payload.user_id,
            confirmation_policy=self._convert_confirmation_policy(
                payload.confirmation_policy
            ),
            initial_message=initial_message,
            max_iterations=payload.max_iterations,
            stuck_detection=payload.stuck_detection,
            enable_base_memory=payload.enable_base_memory,
            enable_experience_memory=payload.enable_experience_memory,
        )



    async def start_conversation(

        self, request: StartConversationRequest

    ) -> tuple[ConversationInfo, bool]:

        """Start a local event_service and return its id."""

        if self._event_services is None:

            raise ValueError("inactive_service")

        conversation_id = request.conversation_id or uuid4()

        existing_event_service = self._event_services.get(conversation_id)

        if existing_event_service and existing_event_service.is_open():

            state = await existing_event_service.get_state()
            access = _build_conversation_access_info(conversation_id, get_default_config())
            conversation_info = _compose_conversation_info(
                existing_event_service.meta_data,
                state,
                access,
            )

            return conversation_info, False
 
        if request.tool_module_qualnames:

            import importlib



            for tool_name, module_qualname in request.tool_module_qualnames.items():

                try:

                    importlib.import_module(module_qualname)

                    logger.debug(

                        f"Tool '{tool_name}' registered via module '{module_qualname}'"

                    )

                except ImportError as e:

                    logger.warning(

                        f"Failed to import module '{module_qualname}' for tool "

                        f"'{tool_name}': {e}. Tool will not be available."

                    )

            logger.info(

                f"Dynamically registered {len(request.tool_module_qualnames)} "

                f"tools for conversation {conversation_id}: "

                f"{list(request.tool_module_qualnames.keys())}"

            )

 
        meta_data = ConversationStateMeta( 
            id=conversation_id, 
            user_id=request.user_id,
            agent=request.agent, 
            workspace=request.workspace, 
            confirmation_policy=request.confirmation_policy, 
            security_analyzer=request.security_analyzer,
            max_iterations=request.max_iterations,
 
            stuck_detection=request.stuck_detection,



            secrets=request.secrets,

            

            tool_module_qualnames=request.tool_module_qualnames,



            plugins=request.plugins,



            hook_config=request.hook_config,
            enable_base_memory=request.enable_base_memory,
            enable_experience_memory=request.enable_experience_memory,



        )

        event_service = await self._start_event_service(meta_data)

        initial_message = request.initial_message

        if initial_message:

            message = Message(

                role=initial_message.role, user_id = request.user_id , content=initial_message.content

            )

            await event_service.send_message(message, True)



        state = await event_service.get_state()
        access = _build_conversation_access_info(conversation_id, get_default_config())
        conversation_info = _compose_conversation_info(event_service.meta_data, state, access)

        await self._notify_conversation_webhooks(conversation_info)

        return conversation_info, True

    async def pause_conversation(self, conversation_id: ConversationID) -> bool:
        if self._event_services is None:
            raise ValueError("inactive_service")
        event_service = self._event_services.get(conversation_id)
        if event_service:
            await event_service.pause()
            # Notify conversation webhooks about the paused conversation
            state = await event_service.get_state()
            conversation_info = _compose_conversation_info(event_service.meta_data, state)
            await self._notify_conversation_webhooks(conversation_info)
        return bool(event_service)

    async def resume_conversation(self, conversation_id: ConversationID) -> tuple[ConversationInfo, bool] | None:
        """Restore a conversation from disk persistence.

        Used when zest-service restarts and in-memory event_services are lost.
        Loads ConversationStateMeta from FileConversationPersistence on disk,
        then re-creates the event_service via _start_event_service.

        Returns (ConversationInfo, is_restored) if successful, None if no persisted meta found.
        """
        if self._event_services is None:
            raise ValueError("inactive_service")

        # Already loaded in memory -> just return existing
        existing = self._event_services.get(conversation_id)
        if existing:
            state = await existing.get_state()
            access = _build_conversation_access_info(conversation_id, get_default_config())
            return _compose_conversation_info(existing.meta_data, state, access), False

        # Try to load from disk persistence
        from sdk.conversation.persistence import FileConversationPersistence

        persistence = FileConversationPersistence(
            conversation_id=conversation_id, cipher=self.cipher
        )
        if not persistence.has_meta():
            logger.info(f"No persisted meta found for conversation: {conversation_id}")
            raise ValueError("No persisted meta found for conversation: {conversation_id}")

        meta_data = persistence.load_meta()
        if meta_data is None:
            logger.warning(f"Failed to load meta for conversation: {conversation_id}")
            raise ValueError("Failed to load meta for conversation: {conversation_id}")

        logger.info(f"Restoring conversation from disk: {conversation_id}")

        # Re-import dynamically registered tool modules so they are available
        # after a server restart. Mirrors the behavior in start_conversation.
        if meta_data.tool_module_qualnames:
            import importlib
            for tool_name, module_qualname in meta_data.tool_module_qualnames.items():
                try:
                    importlib.import_module(module_qualname)
                    logger.debug(
                        f"Tool '{tool_name}' re-registered via module "
                        f"'{module_qualname}'"
                    )
                except ImportError as e:
                    logger.warning(
                        f"Failed to import module '{module_qualname}' for tool "
                        f"'{tool_name}': {e}. Tool will not be available."
                    )
            logger.info(
                f"Re-registered {len(meta_data.tool_module_qualnames)} "
                f"tools for restored conversation {conversation_id}: "
                f"{list(meta_data.tool_module_qualnames.keys())}"
            )

        event_service = await self._start_event_service(meta_data)

        state = await event_service.get_state()
        access = _build_conversation_access_info(conversation_id, get_default_config())
        conversation_info = _compose_conversation_info(
            event_service.meta_data, state, access
        )
        return conversation_info, True

    async def delete_conversation(self, conversation_id: ConversationID) -> bool:
        if self._event_services is None:
            raise ValueError("inactive_service")
        event_service = self._event_services.pop(conversation_id, None)
        if event_service:
            # Notify conversation webhooks about the stopped conversation before closing
            try:
                state = await event_service.get_state()
                conversation_info = _compose_conversation_info(
                    event_service.meta_data, state
                )
                conversation_info.deleting = True
                await self._notify_conversation_webhooks(conversation_info)
            except Exception as e:
                logger.warning(
                    f"Failed to notify webhooks for conversation {conversation_id}: {e}"
                )

            # Close the event service
            try:
                await event_service.close()
            except Exception as e:
                logger.warning(
                    f"Failed to close event service for conversation "
                    f"{conversation_id}: {e}"
                )

            # Safely remove only the conversation directory (workspace is preserved).
            # This operation may fail due to permission issues, but we don't want that
            # to prevent the conversation from being marked as deleted.
            safe_rmtree(
                event_service.conversation_dir,
                f"conversation directory for {conversation_id}",
            )

            logger.info(f"Successfully deleted conversation {conversation_id}")
            return True
        return False

    async def get_event_service(self, conversation_id: ConversationID) -> EventService | None:
        if self._event_services is None:
            raise ValueError("inactive_service")
        return self._event_services.get(conversation_id)

    async def ask_agent(self, conversation_id: ConversationID, question: str) -> str | None:
        """Ask the agent a simple question without affecting conversation state."""
        if self._event_services is None:
            raise ValueError("inactive_service")
        event_service = self._event_services.get(conversation_id)
        if event_service is None:
            return None

        # Delegate to EventService to avoid accessing private conversation internals
        response = await event_service.ask_agent(question)
        return response

    async def condense(self, conversation_id: ConversationID) -> bool:
        """Force condensation of the conversation history."""
        if self._event_services is None:
            raise ValueError("inactive_service")
        event_service = self._event_services.get(conversation_id)
        if event_service is None:
            return False

        # Delegate to EventService to avoid accessing private conversation internals
        await event_service.condense()
        return True

    async def __aenter__(self):

        self.conversations_dir.mkdir(parents=True, exist_ok=True)

        self._event_services = {}



        # Initialize conversation webhook subscribers

        self._conversation_webhook_subscribers = [

            ConversationWebhookSubscriber(

                spec=webhook_spec,

                session_api_key=self.session_api_key,

            )

            for webhook_spec in self.webhook_specs

        ]



        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        event_services = self._event_services
        if event_services is None:
            return
        self._event_services = None
        # This stops conversations and persists the latest descriptor snapshot
        await asyncio.gather(
            *[
                event_service.__aexit__(exc_type, exc_value, traceback)
                for event_service in event_services.values()
            ]
        )

    @classmethod
    def get_instance(cls, config: Config) -> "ConversationService":
        return ConversationService(
            conversations_dir=config.conversations_path,
            webhook_specs=config.webhooks,
            session_api_key=(
                config.session_api_keys[0] if config.session_api_keys else None
            ),
            cipher=config.cipher,
        )

    async def _start_event_service(self,meta_data: ConversationStateMeta) -> EventService:
        event_services = self._event_services
        if event_services is None:
            raise ValueError("inactive_service")
        
        event_service = EventService(
            meta_data=meta_data,
            conversations_dir=self.conversations_dir,
            cipher=self.cipher,
        )
        # Create subscribers...  仅仅只是更新事件的执行时间。
        await event_service.subscribe_to_events(_EventSubscriber(service=event_service))
        asyncio.gather(
            *[
                event_service.subscribe_to_events(
                    WebhookSubscriber(
                        conversation_id=meta_data.id,
                        service=event_service,
                        spec=webhook_spec,
                        session_api_key=self.session_api_key,
                    )
                )
                for webhook_spec in self.webhook_specs
            ]
        )

        try:
            await event_service.start()
        except Exception:
            # Clean up the event service if startup fails
            await event_service.close()
            raise

        event_services[meta_data.id] = event_service
        return event_service


@dataclass
class _EventSubscriber(Subscriber):
    service: EventService

    async def __call__(self, _event: Event):
        update_last_execution_time()


@dataclass
class WebhookSubscriber(Subscriber):
    conversation_id: ConversationID
    service: EventService
    spec: WebhookSpec
    session_api_key: str | None = None
    queue: list[Event] = field(default_factory=list)
    _flush_timer: asyncio.Task | None = field(default=None, init=False)

    async def __call__(self, event: Event):
        if self.spec.base_url is None:
            return 
        """Add event to queue and post to webhook when buffer size is reached."""
        self.queue.append(event)

        if len(self.queue) >= self.spec.event_buffer_size:
            # Cancel timer since we're flushing due to buffer size
            self._cancel_flush_timer()
            await self._post_events()
        elif not self._flush_timer:
            self._flush_timer = asyncio.create_task(self._flush_after_delay())

    async def close(self):
        """Post any remaining items in the queue to the webhook."""
        # Cancel any pending flush timer
        self._cancel_flush_timer()

        if self.queue:
            await self._post_events()

    async def _post_events(self):
        """Post queued events to the webhook with retry logic."""
        if not self.queue:
            return

        events_to_post = self.queue.copy()
        self.queue.clear()

        # Prepare headers
        headers = self.spec.headers.copy()
        if self.session_api_key:
            headers["X-Session-API-Key"] = self.session_api_key

        # Convert events to serializable format
        event_data = [
            event.model_dump() if hasattr(event, "model_dump") else event.__dict__
            for event in events_to_post
        ]

        # Construct events URL
        events_url = (
            f"{self.spec.base_url.rstrip('/')}/events/{self.conversation_id}"
        )

        # Retry logic
        for attempt in range(self.spec.num_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method="POST",
                        url=events_url,
                        json=event_data,
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    logger.debug(
                        f"Successfully posted {len(event_data)} events "
                        f"to webhook {events_url}"
                    )
                    return
            except Exception as e:
                logger.warning(f"Webhook post attempt {attempt + 1} failed: {e}")
                if attempt < self.spec.num_retries:
                    await asyncio.sleep(self.spec.retry_delay)
                else:
                    logger.error(
                        f"Failed to post events to webhook {events_url} "
                        f"after {self.spec.num_retries + 1} attempts"
                    )
                    # Re-queue events for potential retry later
                    self.queue.extend(events_to_post)

    def _cancel_flush_timer(self):
        """Cancel the current flush timer if it exists."""
        if self._flush_timer and not self._flush_timer.done():
            self._flush_timer.cancel()
        self._flush_timer = None
    # 异步推送
    async def _flush_after_delay(self):
        """Wait for flush_delay seconds then flush events if any exist."""
        try:
            await asyncio.sleep(self.spec.flush_delay)
            # Only flush if there are events in the queue
            if self.queue:
                await self._post_events()
        except asyncio.CancelledError:
            # Timer was cancelled, which is expected behavior
            pass
        finally:
            self._flush_timer = None


@dataclass
class ConversationWebhookSubscriber:
    """Webhook subscriber for conversation lifecycle events (start, pause, stop)."""

    spec: WebhookSpec
    session_api_key: str | None = None

    async def post_conversation_info(self, conversation_info: ConversationInfo):
        """Post conversation info to the webhook immediately (no batching)."""
        # Prepare headers
        headers = self.spec.headers.copy()
        if self.session_api_key:
            headers["X-Session-API-Key"] = self.session_api_key
        
        if self.spec.base_url is None:
            return 
        # Construct conversations URL
        conversations_url = f"{self.spec.base_url.rstrip('/')}/conversations"

        # Convert conversation info to serializable format
        conversation_data = conversation_info.model_dump(mode="json")

        # Retry logic
        for attempt in range(self.spec.num_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method="POST",
                        url=conversations_url,
                        json=conversation_data,
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    logger.debug(
                        f"Successfully posted conversation info "
                        f"to webhook {conversations_url}"
                    )
                    return
            except Exception as e:
                logger.warning(
                    f"Conversation webhook post attempt {attempt + 1} failed: {e}"
                )
                if attempt < self.spec.num_retries:
                    await asyncio.sleep(self.spec.retry_delay)
                else:
                    logger.error(
                        f"Failed to post conversation info to webhook "
                        f"{conversations_url} after {self.spec.num_retries + 1} "
                        "attempts"
                    )


_conversation_service: ConversationService | None = None


def get_default_conversation_service() -> ConversationService:
    global _conversation_service
    if _conversation_service:
        return _conversation_service

    from server.config import (
        get_default_config,
    )

    config = get_default_config()
    _conversation_service = ConversationService.get_instance(config)
    return _conversation_service
