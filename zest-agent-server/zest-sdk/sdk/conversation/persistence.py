from abc import ABC, abstractmethod
import json
from pathlib import Path

from common.storage.event_log.event_store import StateStore, create_state_store
from common.utils.cipher import Cipher
from common.utils.common import ConversationID
from sdk.conversation.snapshot import ConversationStateMeta, ConversationStateSnapshot


class ConversationPersistence(ABC):
    @abstractmethod
    def load_meta(self) -> ConversationStateMeta | None: ...

    @abstractmethod
    def save_meta(self, meta_data: ConversationStateMeta) -> None: ...

    @abstractmethod
    def load_snapshot(self) -> ConversationStateSnapshot | None: ...

    @abstractmethod
    def save_snapshot(self, snapshot: ConversationStateSnapshot) -> None: ...

    @abstractmethod
    def has_meta(self) -> bool: ...

    @abstractmethod
    def has_snapshot(self) -> bool: ...


class FileConversationPersistence(ConversationPersistence):
    def __init__(self,  conversation_id: ConversationID, cipher: Cipher | None = None):
        self._state_store: StateStore = create_state_store(conversation_id=conversation_id)
        self._cipher = cipher

    def load_meta(self) -> ConversationStateMeta | None:
        # 传入cipher，反序列化，此时会解密
        return ConversationStateMeta.model_validate_json(self._state_store.read("meta"), context={"cipher": self._cipher})

    def save_meta(self, meta: ConversationStateMeta) -> None:
        # 传入cipher，序列化，保证加密不丢失
        self._state_store.write(meta.model_dump_json(context={"cipher": self._cipher}), "meta")
    
    def load_snapshot(self) -> ConversationStateSnapshot | None: 
        payload = self._state_store.read("snapshot")
        if not payload:
            return None
        context = {"cipher": self._cipher} if self._cipher else None
        return ConversationStateSnapshot.model_validate(json.loads(payload), context=context)

    def save_snapshot(self, snapshot: ConversationStateSnapshot) -> None:
        # create empty snapshot file to acquire lock
        context = {"cipher": self._cipher} if self._cipher else None
        self._state_store.write(snapshot.model_dump_json(exclude_none=True, context=context), "snapshot")

    def has_meta(self) -> bool:
        return self._state_store.exists("meta")

    def has_snapshot(self) -> bool:
        return self._state_store.exists("snapshot")
