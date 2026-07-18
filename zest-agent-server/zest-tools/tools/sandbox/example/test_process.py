import asyncio
import subprocess
import tempfile
import time
import shutil
import os

async def test_execute_command():
    # 创建持久化 bash 进程（模拟 ProcessBackend）
    work_dir = tempfile.mkdtemp(prefix="sandbox_test_")
    
    print(f"工作目录: {work_dir}")
    print(f"工作目录(原始): {repr(work_dir)}")
    print("=" * 50)
    
    process = await asyncio.create_subprocess_exec(
        'bash',
        '-i',  # 交互模式（与 ProcessBackend 一致）
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir
    )
    
    print(f"进程 PID: {process.pid}")
    print("=" * 50)
    
    # 测试 execute_command 的核心逻辑
    async def execute_command(cmd, timeout=30):
        target_dir = work_dir
        timestamp = int(time.time() * 1000)
        start_marker = f"__EXEC_START_{timestamp}__"
        end_marker = f"__EXEC_END_{timestamp}__"
        
        # 处理路径：确保路径中的反斜杠被正确转义（Windows 兼容）
        target_dir = target_dir.replace('\\', '/')
        
        # 构造命令
        full_command = (
            f"echo '{start_marker}'; "
            f"cd '{target_dir}' && {cmd}; "
            f"EXIT_CODE=$?; "
            f"echo $EXIT_CODE; "
            f"echo '{end_marker}'\n"
        )
        
        print(f"\n[DEBUG] 发送的命令:")
        print(full_command)
        print("-" * 50)
        
        # 发送命令
        process.stdin.write(full_command.encode())
        await process.stdin.drain()
        
        # 读取输出
        stdout = ""
        stderr = ""
        exit_code = 0
        start_time = time.time()
        
        async def read_stdout():
            nonlocal stdout, exit_code
            found_start = False
            output_lines = []
            
            while True:
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=timeout)
                    line_str = line.decode('utf-8', errors='replace').rstrip('\n')
                    
                    if start_marker in line_str:
                        found_start = True
                        continue
                    
                    if end_marker in line_str and found_start:
                        break
                    
                    if found_start:
                        output_lines.append(line_str)
                except asyncio.TimeoutError:
                    print(f"[警告] 读取 stdout 超时")
                    break
            
            # 解析输出：最后一行是退出码，前面的是命令输出
            if output_lines:
                try:
                    exit_code = int(output_lines[-1])
                    stdout = '\n'.join(output_lines[:-1])
                except ValueError:
                    exit_code = -1
                    stdout = '\n'.join(output_lines)
        
        async def read_stderr():
            nonlocal stderr
            while time.time() - start_time < timeout:
                try:
                    line = await asyncio.wait_for(process.stderr.readline(), timeout=1)
                    if line:
                        line_str = line.decode('utf-8', errors='replace')
                        stderr += line_str
                except asyncio.TimeoutError:
                    break
        
        await asyncio.gather(read_stdout(), read_stderr(), return_exceptions=True)
        
        execution_time = time.time() - start_time
        
        return {
            'stdout': stdout.strip(),
            'stderr': stderr.strip(),
            'exit_code': exit_code,
            'execution_time': execution_time,
            'success': exit_code == 0
        }
    
    try:
        print("\n测试 1: execute_command('ls -a')")
        print("=" * 50)
        
        result = await execute_command("ls -a")
        print(f"成功: {result['success']}")
        print(f"退出码: {result['exit_code']}")
        print(f"执行时间: {result['execution_time']:.3f}s")
        print(f"\n标准输出:")
        print(result['stdout'][:500] if len(result['stdout']) > 500 else result['stdout'])
        print(f"\n标准错误:")
        print(result['stderr'][:200] if len(result['stderr']) > 200 else result['stderr'])
        
        print("\n" + "=" * 50)
        print("测试 2: execute_command('pwd')")
        print("=" * 50)
        
        result2 = await execute_command("pwd")
        print(f"成功: {result2['success']}")
        print(f"退出码: {result2['exit_code']}")
        print(f"输出: {result2['stdout']}")
        
        print("\n" + "=" * 50)
        print("测试 3: execute_command('echo hello world')")
        print("=" * 50)
        
        result3 = await execute_command("echo hello world")
        print(f"成功: {result3['success']}")
        print(f"退出码: {result3['exit_code']}")
        print(f"输出: {result3['stdout']}")
        
        print("\n" + "=" * 50)
        print("测试 4: execute_command('ls -la /nonexistent') - 应该失败")
        print("=" * 50)
        
        result4 = await execute_command("ls -la /nonexistent")
        print(f"成功: {result4['success']}")
        print(f"退出码: {result4['exit_code']}")
        print(f"标准错误: {result4['stderr']}")
        
        print("\n" + "=" * 50)
        print("测试 5: execute_command('whoami')")
        print("=" * 50)
        
        result5 = await execute_command("whoami")
        print(f"成功: {result5['success']}")
        print(f"退出码: {result5['exit_code']}")
        print(f"输出: {result5['stdout']}")
        
    finally:
        # 清理
        process.stdin.close()
        process.terminate()
        await process.wait()
        shutil.rmtree(work_dir, ignore_errors=True)
        print("\n测试完成！")

if __name__ == '__main__':
    asyncio.run(test_execute_command())
