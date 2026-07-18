import asyncio

from psutil import Process
from tools.sandbox.base import Sandbox
from tools.sandbox.config.settings import RuntimeType, SandboxConfig
from tools.sandbox.impl.process_sandbox import ProcessSandbox
from tools.sandbox.provider.process_provider import ProcessSandboxProvider
 
async def test_process_sandbox():
    
    config = SandboxConfig(
        mode = RuntimeType.PROCESS,
        max_sandboxes=10,
        idle_timeout=600
    )
    
    provider = ProcessSandboxProvider(config)
    
    sandbox = await provider.get("session_1")
     
    result = await sandbox.execute_command("pwd")
    print(result.stdout)
    
    await sandbox.write("/tmp/workspace/test.py", "print('hello')")
    content = await sandbox.read("/tmp/workspace/test.py")

    # 5. 释放沙箱
    await provider.release("session_123")

    # 6. 清理
    await provider.destroy_all()
    

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_process_sandbox())