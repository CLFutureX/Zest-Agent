"""SubAgent集成示例 - 完整的使用演示

这个模块展示了如何在OpenHands中使用SubAgent功能：
1. 创建SubAgent实例
2. 配置SubAgent
3. 创建主Agent并传入SubAgent配置
4. 使用Conversation运行任务

增强功能：
- 支持直接的system_prompt参数
- 提示词验证和优化
- 便利函数create_agent_with_custom_prompt
"""

import os

from sdk import LLM, Agent
from sdk.agent.agent_prompt_enhancement import create_agent_with_custom_prompt
from sdk.conversation import LocalConversation
from sdk.tool.builtins.sub_agent_tool import SubAgentConfig


# ============================================================================
# 示例1：基础SubAgent集成（使用直接的system_prompt）
# ============================================================================


def example_basic_subagent_integration(
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
    base_url: str | None = None,
):
    """基础SubAgent集成示例

    这个示例展示了：
    1. 创建SubAgent实例（使用直接的system_prompt）
    2. 配置SubAgent
    3. 创建主Agent并传入SubAgent配置
    4. 使用Conversation运行任务

    Args:
        model: LLM模型名称
        api_key: API密钥
        base_url: API基础URL
    """

    print("=" * 80)
    print("示例1: 基础SubAgent集成（使用直接的system_prompt）")
    print("=" * 80)

    # 步骤1: 创建LLM实例
    llm = LLM(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    # 步骤2: 创建SubAgent实例（使用直接的system_prompt参数）
    # SubAgent1: 代码审查员
    code_reviewer = Agent(
        id="code_reviewer_agent",
        llm=llm,
        tools=[
            # Tool(name=FileEditorTool.name),
            # Tool(name=TerminalTool.name),
        ],
        custom_system_prompt="""You are an expert code reviewer with 10+ years of experience.
Your responsibilities:
1. Review code for correctness and efficiency
2. Identify potential bugs and security issues
3. Suggest improvements following best practices
4. Provide constructive feedback
5. Rate code quality on a scale of 1-10

Always be professional and helpful in your reviews.""",
    )

    # SubAgent2: 测试运行器
    test_runner = Agent(
        id= "tetest_runner_agent",
        llm=llm,
        tools=[
            # Tool(name=TerminalTool.name),
        ],
        custom_system_prompt="""You are an expert test engineer.
Your responsibilities:
1. Write comprehensive unit tests
2. Ensure high code coverage (>80%)
3. Test edge cases and error conditions
4. Verify performance requirements
5. Document test cases clearly

Focus on quality and completeness.""",
    )

    # 步骤3: 配置SubAgent
    subagent_configs = [
        SubAgentConfig(
            name="code_reviewer",
            description="Review code and provide feedback on quality, style, and best practices",
            agent=code_reviewer,
        ),
        SubAgentConfig(
            name="test_runner",
            description="Run tests and report results",
            agent=test_runner,
        ),
    ]

    # 步骤4: 创建主Agent并传入SubAgent配置
    main_agent = Agent(
        id="mainAgent",
        llm=llm,
        tools=[
            # Tool(name=TerminalTool.name),
            # Tool(name=FileEditorTool.name),
            # Tool(name=TaskTrackerTool.name),
        ],
        subagent_configs=subagent_configs,  # 传入SubAgent配置
        custom_system_prompt="""You are the main project coordinator.
Your responsibilities:
1. Coordinate with code_reviewer for code quality
2. Coordinate with test_runner for test execution
3. Provide comprehensive project analysis
4. Generate final reports and recommendations

Always ensure quality and completeness.""",
    )

    # 步骤5: 创建Conversation
    cwd = os.getcwd()
    conversation = LocalConversation(
        agent=main_agent,
        workspace=cwd,
        persistence_dir="D:\\spacex\\agent_data2\\aaa"
    )

    # 步骤6: 发送任务消息
    conversation.send_message(
        "Write 3 facts about the current project into FACTS.txt. "
        "You can use the code_reviewer subagent to analyze the code structure."
    )

    # 步骤7: 运行Conversation
    conversation.run()

    print("\n✅ 任务完成！")
    print("=" * 80)


# ============================================================================
# 示例2: 多SubAgent协作（使用便利函数）
# ============================================================================


def example_multi_subagent_collaboration(
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
    base_url: str | None = None,
):
    """多SubAgent协作示例

    这个示例展示了：
    1. 使用便利函数create_agent_with_custom_prompt创建Agent
    2. 创建多个专门的SubAgent
    3. 主Agent如何协调多个SubAgent
    4. SubAgent之间的协作流程

    Args:
        model: LLM模型名称
        api_key: API密钥
        base_url: API基础URL
    """

    print("=" * 80)
    print("示例2: 多SubAgent协作（使用便利函数）")
    print("=" * 80)

    # 创建LLM实例
    llm = LLM(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    # 创建多个专门的SubAgent

    # SubAgent1: 代码分析员
    code_analyzer = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are a code analysis expert.
Analyze code structure, identify patterns, and provide insights.
Focus on architecture, design patterns, and code organization.""",
    )

    # SubAgent2: 文档生成器
    doc_generator = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are a technical documentation expert.
Generate clear, comprehensive documentation for code.
Include examples, usage patterns, and best practices.""",
    )

    # SubAgent3: 测试工程师
    test_engineer = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are a test engineering expert.
Write comprehensive tests covering all scenarios.
Ensure high code coverage and edge case handling.""",
    )

    # SubAgent4: 性能优化师
    performance_optimizer = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are a performance optimization expert.
Identify bottlenecks and optimize code for speed and efficiency.
Provide detailed performance analysis and recommendations.""",
    )

    # 配置SubAgent
    subagent_configs = [
        SubAgentConfig(
            name="code_analyzer",
            description="Analyze code structure and identify issues",
            agent=code_analyzer,
        ),
        SubAgentConfig(
            name="doc_generator",
            description="Generate documentation for code",
            agent=doc_generator,
        ),
        SubAgentConfig(
            name="test_engineer",
            description="Write and run tests",
            agent=test_engineer,
        ),
        SubAgentConfig(
            name="performance_optimizer",
            description="Optimize code performance",
            agent=performance_optimizer,
        ),
    ]

    # 创建主Agent
    main_agent = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are the project lead coordinating multiple specialists.
Your responsibilities:
1. Delegate tasks to appropriate specialists
2. Ensure all aspects are covered (analysis, documentation, testing, performance)
3. Synthesize findings into comprehensive report
4. Provide actionable recommendations

Coordinate effectively with all team members.""",
        subagent_configs=subagent_configs,
    )

    # 创建Conversation
    cwd = os.getcwd()
    conversation = LocalConversation(
        agent=main_agent,
        workspace=cwd,
    )

    # 发送复杂任务
    conversation.send_message(
        """Please perform a comprehensive code review:
        1. Use code_analyzer to analyze the project structure
        2. Use doc_generator to create documentation
        3. Use test_engineer to write tests
        4. Use performance_optimizer to optimize critical paths
        5. Provide a summary of all findings
        """
    )

    # 运行Conversation
    conversation.run()

    print("\n✅ 多SubAgent协作完成！")
    print("=" * 80)


# ============================================================================
# 示例3: 嵌套SubAgent调用
# ============================================================================


def example_nested_subagent_call(
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
    base_url: str | None = None,
):
    """嵌套SubAgent调用示例

    这个示例展示了：
    1. SubAgent本身也可以有SubAgent
    2. 形成多层级的Agent架构
    3. 复杂任务的递归委托

    Args:
        model: LLM模型名称
        api_key: API密钥
        base_url: API基础URL
    """

    print("=" * 80)
    print("示例3: 嵌套SubAgent调用")
    print("=" * 80)

    # 创建LLM实例
    llm = LLM(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    # 第一层：创建最底层的SubAgent
    code_formatter = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="You are a code formatter. Format code according to best practices.",
    )

    code_linter = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="You are a code linter. Check code for style and quality issues.",
    )

    # 第二层：创建中间层SubAgent
    code_quality_checker = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="You are a code quality checker. Coordinate formatter and linter.",
        subagent_configs=[
            SubAgentConfig(
                name="formatter",
                description="Format code",
                agent=code_formatter,
            ),
            SubAgentConfig(
                name="linter",
                description="Check code quality",
                agent=code_linter,
            ),
        ],
    )

    security_checker = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="You are a security checker. Check code for security vulnerabilities.",
    )

    # 第三层：创建主Agent
    main_agent = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="You are the main code review coordinator. Delegate to quality and security checkers.",
        subagent_configs=[
            SubAgentConfig(
                name="quality_checker",
                description="Check code quality and format",
                agent=code_quality_checker,
            ),
            SubAgentConfig(
                name="security_checker",
                description="Check code security",
                agent=security_checker,
            ),
        ],
    )

    # 创建Conversation
    cwd = os.getcwd()
    conversation = LocalConversation(
        agent=main_agent,
        workspace=cwd,
    )

    # 发送任务
    conversation.send_message(
        """Please perform a comprehensive code review:
        1. Use quality_checker to check code quality (which will use formatter and linter)
        2. Use security_checker to check for security issues
        3. Provide a final summary with recommendations
        """
    )

    # 运行Conversation
    conversation.run()

    print("\n✅ 嵌套SubAgent调用完成！")
    print("=" * 80)


# ============================================================================
# 示例4: 自定义SubAgent提示词（高级用法）
# ============================================================================


def example_custom_subagent_prompt(
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
    base_url: str | None = None,
):
    """自定义SubAgent提示词示例

    这个示例展示了如何为SubAgent设置自定义的系统提示词

    Args:
        model: LLM模型名称
        api_key: API密钥
        base_url: API基础URL
    """

    print("=" * 80)
    print("示例4: 自定义SubAgent提示词（高级用法）")
    print("=" * 80)

    # 创建LLM实例
    llm = LLM(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    # 创建具有详细自定义提示词的SubAgent
    code_reviewer = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are an expert code reviewer with 10+ years of experience.

## Your Expertise
- Python, Java, JavaScript, Go, Rust
- System design and architecture
- Performance optimization
- Security best practices

## Review Process
1. **Correctness**: Check for logical errors and edge cases
2. **Efficiency**: Identify performance bottlenecks
3. **Security**: Look for vulnerabilities and unsafe patterns
4. **Maintainability**: Assess code clarity and documentation
5. **Best Practices**: Verify adherence to standards

## Output Format
Provide reviews in the following format:
- **Summary**: One-line overview
- **Strengths**: What's done well
- **Issues**: Problems found (critical, major, minor)
- **Suggestions**: Specific improvements
- **Rating**: 1-10 score with justification""",
    )

    # 创建具有详细自定义提示词的测试工程师SubAgent
    test_engineer = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are an expert test engineer with deep expertise in:
- Unit testing frameworks (pytest, unittest, jest)
- Integration testing strategies
- Test coverage analysis
- Performance testing
- Security testing

## Testing Responsibilities
1. **Unit Tests**: Cover all functions and edge cases
2. **Integration Tests**: Verify component interactions
3. **Coverage**: Aim for >80% code coverage
4. **Performance**: Test performance requirements
5. **Security**: Test for security vulnerabilities

## Test Quality Metrics
- Coverage: >80%
- Execution time: <5 seconds for unit tests
- Maintainability: Clear test names and documentation
- Reliability: No flaky tests

## Output Format
Provide test reports including:
- Test summary and statistics
- Coverage analysis
- Performance metrics
- Recommendations for improvement""",
    )

    # 配置SubAgent
    subagent_configs = [
        SubAgentConfig(
            name="code_reviewer",
            description="Expert code reviewer with detailed analysis",
            agent=code_reviewer,
        ),
        SubAgentConfig(
            name="test_engineer",
            description="Expert test engineer with comprehensive testing",
            agent=test_engineer,
        ),
    ]

    # 创建主Agent
    main_agent = create_agent_with_custom_prompt(
        llm=llm,
        system_prompt="""You are the project quality assurance lead.

## Your Responsibilities
1. Coordinate code review with code_reviewer
2. Coordinate testing with test_engineer
3. Synthesize findings into comprehensive quality report
4. Provide actionable recommendations for improvement

## Quality Standards
- Code quality: 8/10 or higher
- Test coverage: >80%
- Security: No critical vulnerabilities
- Performance: Meets requirements

## Report Format
Provide a comprehensive quality report including:
- Executive summary
- Code quality assessment
- Test coverage analysis
- Security assessment
- Performance evaluation
- Recommendations for improvement""",
        subagent_configs=subagent_configs,
    )

    # 创建Conversation
    cwd = os.getcwd()
    conversation = LocalConversation(
        agent=main_agent,
        workspace=cwd,
    )

    # 发送任务
    conversation.send_message(
        """Please perform a comprehensive quality assurance review:
        1. Use code_reviewer to review the main.py file with detailed analysis
        2. Use test_engineer to write comprehensive tests
        3. Provide a final quality report with recommendations
        """
    )

    # 运行Conversation
    conversation.run()

    print("\n✅ 自定义提示词示例完成！")
    print("=" * 80)


# ============================================================================
# 主函数
# ============================================================================

if __name__ == "__main__":
    import sys

    api_key = os.getenv("LLM_API_KEY")

    assert api_key is not None, "LLM_API_KEY environment variable is not set."
    model = os.getenv("LLM_MODEL", "dashscope/qwen3.5-plus")
    base_url = os.getenv("LLM_BASE_URL")
    # 从环境变量获取配置
    print("\n🚀 OpenHands SubAgent 集成示例（增强版）\n")

    # 运行示例
    if len(sys.argv) > 1:
        example_name = sys.argv[1]
        if example_name == "1":
            example_basic_subagent_integration(model, api_key, base_url)
        elif example_name == "2":
            example_multi_subagent_collaboration(model, api_key, base_url)
        elif example_name == "3":
            example_nested_subagent_call(model, api_key, base_url)
        elif example_name == "4":
            example_custom_subagent_prompt(model, api_key, base_url)
        else:
            print(f"❌ 未知示例: {example_name}")
            print("可用示例: 1, 2, 3, 4")
    else:
        # 默认运行示例1
        print("运行示例1: 基础SubAgent集成（使用直接的system_prompt）")
        print("(使用 'python subagent_examples.py <number>' 运行其他示例)\n")
        example_basic_subagent_integration(model, api_key, base_url)
