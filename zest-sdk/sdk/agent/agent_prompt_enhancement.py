"""Agent系统提示词增强模块

这个模块提供了对Agent系统提示词的增强支持，包括：
1. 直接的system_prompt字符串支持
2. 自定义提示词模板
3. 提示词验证和优化
"""

import os
import tempfile
from pathlib import Path


# 默认的自定义系统提示词模板
DEFAULT_CUSTOM_PROMPT_TEMPLATE = """{{ custom_system_prompt }}

{% if tools %}
## Available Tools

You have access to the following tools:

{% for tool in tools %}
- **{{ tool.name }}**: {{ tool.description }}
{% endfor %}

Use these tools to help accomplish your tasks.
{% endif %}

{% if llm_security_analyzer %}
## Security Guidelines

Always consider the security implications of your actions. When using tools:
1. Verify the safety of operations before execution
2. Avoid operations that could compromise system security
3. Report any security concerns immediately
{% endif %}
"""


class SystemPromptManager:
    """管理Agent的系统提示词。

    提供以下功能：
    1. 创建自定义提示词模板
    2. 验证提示词内容
    3. 优化提示词格式
    """

    @staticmethod
    def create_custom_prompt_template(
        custom_prompt: str,
        template_dir: str | None = None,
    ) -> str:
        """创建自定义系统提示词模板文件。

        Args:
            custom_prompt: 自定义的系统提示词内容
            template_dir: 模板文件目录（可选）

        Returns:
            模板文件的路径
        """
        # 如果没有指定目录，使用临时目录
        if template_dir is None:
            template_dir = tempfile.gettempdir()

        # 确保目录存在
        Path(template_dir).mkdir(parents=True, exist_ok=True)

        # 创建模板文件
        template_path = os.path.join(template_dir, "custom_system_prompt.j2")

        with open(template_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CUSTOM_PROMPT_TEMPLATE)

        return template_path

    @staticmethod
    def validate_prompt(prompt: str) -> bool:
        """验证系统提示词的有效性。

        Args:
            prompt: 要验证的提示词

        Returns:
            如果提示词有效则返回True
        """
        if not prompt:
            return False

        if not isinstance(prompt, str):
            return False

        # 检查提示词长度（不应该太短或太长）
        if len(prompt) < 10:
            return False

        if len(prompt) > 10000:
            return False

        return True

    @staticmethod
    def optimize_prompt(prompt: str) -> str:
        """优化系统提示词格式。

        Args:
            prompt: 原始提示词

        Returns:
            优化后的提示词
        """
        # 移除多余的空白
        lines = [line.strip() for line in prompt.split("\n")]

        # 移除空行
        lines = [line for line in lines if line]

        # 重新组合
        optimized = "\n".join(lines)

        return optimized


def create_agent_with_custom_prompt(
    llm,
    system_prompt: str,
    tools: list | None = None,
    subagent_configs: list | None = None,
    **kwargs,
):
    """创建一个具有自定义系统提示词的Agent。

    这是一个便利函数，简化了创建具有自定义提示词的Agent的过程。

    Args:
        llm: LLM实例
        system_prompt: 自定义的系统提示词
        tools: 工具列表（可选）
        subagent_configs: SubAgent配置列表（可选）
        **kwargs: 其他Agent参数

    Returns:
        配置好的Agent实例

    Example:
        >>> from sdk import LLM
        >>> from openHands.agent_prompt_enhancement import create_agent_with_custom_prompt
        >>>
        >>> llm = LLM(model="claude-sonnet-4-20250514")
        >>> agent = create_agent_with_custom_prompt(
        ...     llm=llm,
        ...     system_prompt="You are an expert code reviewer...",
        ...     tools=[...],
        ... )
    """
    from openHands.agent import Agent

    # 验证提示词
    if not SystemPromptManager.validate_prompt(system_prompt):
        raise ValueError("Invalid system prompt provided")

    # 优化提示词
    optimized_prompt = SystemPromptManager.optimize_prompt(system_prompt)

    # 创建Agent
    agent = Agent(
        llm=llm,
        system_prompt=optimized_prompt,
        tools=tools or [],
        subagent_configs=subagent_configs or [],
        **kwargs,
    )

    return agent
