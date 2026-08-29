
import logging
from typing import TYPE_CHECKING



from uuid import uuid4

from common.utils.cipher import Cipher

from common.utils.common import ConversationID
from common.utils.common import ExecutionStatus

from sdk.agent.agent_spec import AgentSpec
from sdk.agent.base import AgentBase

from sdk.agent.agent_state import AgentState
from sdk.conversation.base import ConversationCallbackType

from sdk.conversation.conversation_stats import ConversationStats
from sdk.conversation.persistence import ConversationPersistence, FileConversationPersistence
from pathlib import Path

from sdk.secret.secret_registry import SecretValue

from sdk.conversation.snapshot import ConversationStateMeta
from sdk.conversation.state import ConversationState
from sdk.agent.stuck_detection.types import ConversationTokenCallbackType

from sdk.conversation.visualizer import ConversationVisualizerBase, DefaultConversationVisualizer

from sdk.hooks import HookConfig

from sdk.plugin import PluginSource


from sdk.workspace.base import BaseWorkspace



if TYPE_CHECKING:

    from sdk.conversation.impl.conversation_impl import LocalConversation


logger = logging.getLogger(__name__)


class ConversationFactory:

    def __init__(self, conversation_id: ConversationID,persistence: ConversationPersistence | None = None):
       
        self._conversation_id = conversation_id
        self._persistence = persistence 
     
    def create(

        self,

        *,
        meta_data: ConversationStateMeta | None = None,
       
        callbacks: list[ConversationCallbackType] | None = None,

        token_callbacks: list[ConversationTokenCallbackType] | None = None,

        visualizer: type[ConversationVisualizerBase] | ConversationVisualizerBase | None = DefaultConversationVisualizer,

        cipher: Cipher | None = None,

    ) -> "LocalConversation":

        resolved_id = self._conversation_id 

        if meta_data is None:
            if self._persistence.has_meta():
                meta_data = self._persistence.load_meta()
            else:
                raise ValueError("meta_data is required for new conversation")
        else:
            if not self._persistence.has_meta():
                self._persistence.save_meta(meta_data)
            else:
                existing_meta = self._persistence.load_meta()
                if existing_meta and existing_meta != meta_data:
                    raise ValueError("meta_data mismatch with existing conversation")
        from sdk.conversation.impl.conversation_impl import LocalConversation

        return LocalConversation(

            agent_spec=meta_data.agent,

            workspace=meta_data.workspace,

            plugins=meta_data.plugins,

            conversation_id=meta_data.id,

            user_id = meta_data.user_id,
            callbacks=callbacks,

            token_callbacks=token_callbacks,

            confirmation_policy=meta_data.confirmation_policy,

            security_analyzer=meta_data.security_analyzer,

            hook_config=meta_data.hook_config,

            max_iteration_per_run=meta_data.max_iterations,

            stuck_detection=meta_data.stuck_detection,
            enable_base_memory=meta_data.enable_base_memory,
            enable_experience_memory=meta_data.enable_experience_memory,

            visualizer=visualizer,

            secrets=meta_data.secrets,

            cipher=cipher,

        )
    
    
    
    def create_state(

        self,

        id: ConversationID,

        agent_spec: AgentSpec,

        workspace: BaseWorkspace,

        max_iterations: int = 500,

        stuck_detection: bool = True,

        user_id: str | None = None,

    ) -> ConversationState:

       

        if self._persistence.has_snapshot():

            state_snapshot = self._persistence.load_snapshot()

            self._state = ConversationState.from_snapshot(

                snapshot=state_snapshot,

                workspace=workspace,

                user_id=user_id,

                max_iterations=max_iterations,

            )

            logger.info(f"Loaded existing conversation state for conversation {id}")

            return self._state

        

        if not agent_spec:

            raise ValueError("agent_spec is required for new ConversationState")



        state = ConversationState(

            id=id,

            workspace=workspace,

            max_iterations=max_iterations,

            stuck_detection=stuck_detection,

            execution_status=ExecutionStatus.IDLE,

        )

       

        state._user_id = user_id 

        state.stats = ConversationStats()
        # agent_state 不应该由ConversationState创建，而是下沉到agentRunner中
        state.main_agent_state = AgentState.build(

            conversation_id=id,
 

            agent_spec=agent_spec,

            task_description="Main conversation task",
        )



        logger.info(f"Created main agent state for new conversation {id}")

        self._persistence.save_snapshot(state.to_snapshot())

        logger.info(f"Created new conversation {state.id}")

        return state
