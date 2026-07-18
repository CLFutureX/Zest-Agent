#!/usr/bin/env python3
"""Refactor task_service.py _dispatch_task method"""
import re

TARGET = 'd:/spacex/Zest-Agent/zest-app-server/app/core/services/task_service.py'

with open(TARGET, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new _dispatch_task method and helper methods
new_dispatch = '''    async def _dispatch_task(
        self,
        session_id: str,
        task: TaskInfo
    ) -> dict:
        """
        Based on task + session + user info, build a StartConversationRequest
        and dispatch it to zest-service's Conversation API.

        Architecture:
        - SessionInfo: interaction session between zest-app-server and frontend
        - Task: user message sent within a session
        - zest-service Conversation: the actual agent-level conversation

        Returns:
            dict: fields to update in storage (including conversation_id)
        """
        import httpx

        # 1. Get session info
        session = await self.session_storage.get_session(session_id)
        if not session:
            return {"status": TaskStatus.FAILED, "error_message": f"Session {session_id} not found"}

        server_id = session.agent_server_id
        if not server_id:
            return {"status": TaskStatus.FAILED, "error_message": "No AgentServer bound to session"}

        # 2. Get AgentServer address
        host = "localhost"
        port = 8080
        if self.agent_registry:
            server_info = await self.agent_registry.get_server(server_id)
            if server_info:
                host = server_info.host
                port = server_info.port

        # 3. Build StartConversationRequest payload
        payload = self._build_conversation_request(task, session)

        # 4. Call zest-service /api/conversations endpoint
        url = f"http://{host}:{port}/api/conversations"

        try:
            async with httpx.AsyncClient(timeout=self.task_dispatch_timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                result = resp.json()

            # Extract conversation_id from response
            conversation_id = result.get("id") or result.get("conversation_id")

            return {
                "status": TaskStatus.RUNNING,
                "conversation_id": conversation_id,
                "result": result,
                "updated_at": datetime.utcnow()
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP dispatch failed for task {task.task_id}: "
                f"{e.response.status_code} {e.response.text}"
            )
            return {
                "status": TaskStatus.FAILED,
                "error_message": f"HTTP {e.response.status_code}: {e.response.text}"
            }
        except httpx.RequestError as e:
            logger.error(f"HTTP dispatch error for task {task.task_id}: {e}")
            return {
                "status": TaskStatus.FAILED,
                "error_message": f"Connection failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected dispatch error for task {task.task_id}: {e}")
            return {
                "status": TaskStatus.FAILED,
                "error_message": str(e)
            }

    def _build_conversation_request(
        self,
        task: TaskInfo,
        session: "SessionInfo",
    ) -> dict:
        """
        Assemble task + session + user info into zest-service's StartConversationRequest.

        Reference zest-service StartConversationRequest structure:
        - agent: { llm: { usage_id, model, api_key } }
        - workspace: { working_dir }
        - initial_message: { role, content: [{ text }] }
        """
        # Get user LLM config
        user_llm = self._get_user_llm_config(task.user_id)

        # Get workspace directory
        workspace_dir = self._get_workspace_dir(task, session)

        # Build initial_message (task is the user's message in the session)
        task_message = task.metadata.get("message", task.title)
        initial_message = {
            "role": "user",
            "content": [{"kind": "TextContent", "text": task_message}],
            "run": True,
        }

        # Build complete StartConversationRequest
        request_body = {
            "agent": {
                "llm": {
                    "usage_id": user_llm.get("usage_id", "default"),
                    "model": user_llm.get("model", "openai/gpt-4o"),
                    "api_key": user_llm.get("api_key", ""),
                }
            },
            "workspace": {
                "working_dir": workspace_dir,
            },
            "initial_message": initial_message,
        }

        return request_body

    def _get_user_llm_config(self, user_id: str) -> dict:
        """Get user's LLM config (returns default config for now, can connect to user_storage later)"""
        return {
            "usage_id": "openai",
            "model": "openai/gpt-4o",
            "api_key": "",
        }

    def _get_workspace_dir(self, task: TaskInfo, session: "SessionInfo") -> str:
        """Get task workspace directory"""
        # Prefer session metadata workspace
        workspace = session.metadata.get("workspace")
        if workspace:
            return workspace
        # Fallback to task metadata workspace
        workspace = task.metadata.get("workspace")
        if workspace:
            return workspace
        # Default workspace
        return "workspace/project"

'''

# Use regex to find and replace the _dispatch_task method
# Match from "async def _dispatch_task" to the next method definition or end of class
pattern = r'(    async def _dispatch_task\([\s\S]*?)(\n    async def get_task\()'

match = re.search(pattern, content)
if match:
    old_method = match.group(1)
    print(f"Found _dispatch_task method: {len(old_method)} chars")
    
    # Replace the method
    new_content = content[:match.start()] + new_dispatch + match.group(2) + content[match.end():]
    
    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("Successfully refactored _dispatch_task method")
else:
    print("Could not find _dispatch_task method pattern")
    # Try a simpler approach - find the method by line numbers
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'async def _dispatch_task' in line:
            print(f"Found _dispatch_task at line {i+1}: {line}")
