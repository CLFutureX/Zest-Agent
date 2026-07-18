from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import pathlib
import re

 
from sdk.agent.runner_context import RunnerContext
from sdk.agent.runtime import AgentRuntime
 


from common.logger import get_logger

from sdk.agent.agent_spec import  AgentSpec
from sdk.agent.runtime import AgentRuntime
 
from sdk.context.prompts.prompt import render_template
from sdk.context.skills.skill import Skill, load_public_skills, load_user_skills, to_prompt
from sdk.llm.utils.model_prompt_spec import get_model_prompt_spec
from sdk.mcp.utils import create_mcp_tools
from sdk.tool.builtins import BUILT_IN_TOOL_CLASSES
from sdk.tool.builtins.sub_agent_tool import SUBAGENT_DESCRIPTION, SubAgentTool
from sdk.tool.registry import resolve_tool
from sdk.tool.tool import ToolDefinition

PROMPT_DIR = pathlib.Path(__file__).parent / "prompts" / "templates"

logger = get_logger(__name__)


class PromptBuildStage:


    def run(self, agent_spec:AgentSpec, context, runtime: AgentRuntime) -> AgentRuntime:

    
        trace: list[str] = []
        if agent_spec.custom_system_prompt:
            system_message = agent_spec.custom_system_prompt
            trace.append("custom_system_prompt")
        else:
            template_kwargs = dict(agent_spec.system_prompt_kwargs)
            template_kwargs["security_policy_filename"] = agent_spec.security_policy_filename
            template_kwargs.setdefault("model_name", agent_spec.llm.model)
            if (
                "model_family" not in template_kwargs
                or "model_variant" not in template_kwargs
            ):
                spec = get_model_prompt_spec(
                    agent_spec.llm.model,
                    getattr(agent_spec.llm, "model_canonical_name", None),
                )
                if "model_family" not in template_kwargs and spec.family:
                    template_kwargs["model_family"] = spec.family
                if "model_variant" not in template_kwargs and spec.variant:
                    template_kwargs["model_variant"] = spec.variant
            system_message = render_template(
                prompt_dir=agent_spec.prompt_dir,
                template_name=agent_spec.system_prompt_filename,
                **template_kwargs,
            )
            trace.append("system_prompt_template")

        if agent_spec.agent_context_spec:
            suffix = self._get_system_message_suffix(
                runtime=runtime,
                system_message_suffix=agent_spec.agent_context_spec.system_message_suffix,
                llm_model=agent_spec.llm.model,
                llm_model_canonical=agent_spec.llm.model_canonical_name,
                skills=runtime.skills,
            )
            if suffix:
                system_message += "\n\n" + suffix
                trace.append("agent_context_suffix")
      

        return runtime.copy_with(system_message=system_message, prompt_trace=trace)
    def _get_system_message_suffix(
        self,
        runtime: AgentRuntime,
        system_message_suffix: str | None,
        llm_model: str | None = None,
        llm_model_canonical: str | None = None,
        skills: list[Skill] | None = None,
        
    ) -> str | None:
        """Get the system message with repo skill content and custom suffix.

        Custom suffix can typically includes:
        - Repository information (repo name, branch name, PR number, etc.)
        - Runtime information (e.g., available hosts, current date)
        - Conversation instructions (e.g., user preferences, task details)
        - Repository-specific instructions (collected from repo skills)
        - Available skills list (for AgentSkills-format and triggered skills)

        Skill categorization:
        - AgentSkills-format (SKILL.md): Always in <available_skills> (progressive
          disclosure). If has triggers, content is ALSO auto-injected on trigger
          in user prompts.
        - Legacy with trigger=None: Full content in <REPO_CONTEXT> (always active)
        - Legacy with triggers: Listed in <available_skills>, injected on trigger
        """
        # Categorize skills based on format and trigger:
        # - AgentSkills-format: always in available_skills (progressive disclosure)
        # - Legacy: trigger=None -> REPO_CONTEXT, else -> available_skills
        repo_skills: list[Skill] = []
        available_skills: list[Skill] = []

        for s in skills:
            if s.is_agentskills_format:
                # AgentSkills: always list (triggers also auto-inject via
                # get_user_message_suffix)
                available_skills.append(s)
            elif s.trigger is None:
                # Legacy Zest: no trigger = full content in REPO_CONTEXT
                repo_skills.append(s)
            else:
                # Legacy Zest: has trigger = list in available_skills
                available_skills.append(s)

        # Gate vendor-specific repo skills based on model family.
        if llm_model or llm_model_canonical:
            spec = get_model_prompt_spec(llm_model or "", llm_model_canonical)
            family = (spec.family or "").lower()
            if family:
                filtered: list[Skill] = []
                for s in repo_skills:
                    n = (s.name or "").lower()
                    if n == "claude" and not (
                        "anthropic" in family or "claude" in family
                    ):
                        continue
                    if n == "gemini" and not (
                        "gemini" in family or "google_gemini" in family
                    ):
                        continue
                    filtered.append(s)
                repo_skills = filtered

        logger.debug(f"Loaded {len(repo_skills)} repository skills: {repo_skills}")

        # Generate available skills prompt
        available_skills_prompt = ""
        if available_skills:
            available_skills_prompt = to_prompt(available_skills)
            logger.debug(
                f"Generated available skills prompt for {len(available_skills)} skills"
            )

        # Build the workspace context information
        secret_infos = runtime.get_secret_infos()
        has_content = (
            repo_skills
            or system_message_suffix
            or secret_infos
            or available_skills_prompt
        )
        if has_content:
            formatted_text = render_template(
                prompt_dir=str(PROMPT_DIR),
                template_name="system_message_suffix.j2",
                repo_skills=repo_skills,
                system_message_suffix=system_message_suffix or "",
                secret_infos=secret_infos,
                available_skills_prompt=available_skills_prompt,
            ).strip()
            return formatted_text
        elif system_message_suffix and system_message_suffix.strip():
            return system_message_suffix.strip()
        return None




class ToolAssembleStage:



    def run(self, agent_spec: AgentSpec, context, runtime: AgentRuntime) -> AgentRuntime:


        trace: list[str] = []
        tools: list[ToolDefinition] = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(resolve_tool, tool_spec, context) for tool_spec in agent_spec.tools]
            if agent_spec.mcp_config:
                futures.append(executor.submit(create_mcp_tools, agent_spec.mcp_config, 30))
            for future in futures:
                result = future.result()
                tools.extend(result)
        trace.append("declared_tools")

        if agent_spec.filter_tools_regex:
            pattern = re.compile(agent_spec.filter_tools_regex)
            tools = [tool for tool in tools if pattern.match(tool.name)]
            trace.append("regex_filtered")

        for tool_name in agent_spec.include_default_tools:
            tool_class = BUILT_IN_TOOL_CLASSES.get(tool_name)
            if tool_class is None:
                raise ValueError(f"Unknown built-in tool class: '{tool_name}'")
            tools.extend(tool_class.create(context))
        trace.append("default_tools")

        tool_names = [tool.name for tool in tools]
        if len(tool_names) != len(set(tool_names)):
            duplicates = set(name for name in tool_names if tool_names.count(name) > 1)
            raise ValueError(f"Duplicate tool names found: {duplicates}")
        trace.append("validated")
        tools_map = {tool.name: tool for tool in tools}

        return runtime.copy_with(tools_map=tools_map, tool_trace=trace)



class SkillBuildStage:
    def run(self, agent_spec: AgentSpec, context, runtime: AgentRuntime) -> AgentRuntime:
        if not agent_spec.agent_context_spec or not agent_spec.agent_context_spec.skills:
            return runtime
        self._validate_skills(agent_spec.agent_context_spec.skills) 
        skills: list[Skill] = agent_spec.agent_context_spec.skills
        self._load_user_skills(agent_spec, skills)
        self._load_public_skills(agent_spec, skills)
        return runtime.copy_with(skills=skills)  
        
        
    def _validate_skills(self, v: list[Skill], _info):
        if not v:
            return v
        # Check for duplicate skill names
        seen_names = set()
        for skill in v:
            if skill.name in seen_names:
                raise ValueError(f"Duplicate skill name found: {skill.name}")
            seen_names.add(skill.name)
        return v
    
    def _load_user_skills(self,agent_spec: AgentSpec, exist_skills: list[Skill]):
        """Load user skills from home directory if enabled."""
        if not self.agent_spec.agent_context_spec.load_user_skills:
            return

        try:
            skills: list[Skill] = []
            user_skills = load_user_skills()
            # Merge user skills with explicit skills, avoiding duplicates
            existing_names = {skill.name for skill in exist_skills}
            for user_skill in user_skills:
                if user_skill.name not in existing_names:
                    skills.append(user_skill)
                else:
                    logger.warning(
                        f"Skipping user skill '{user_skill.name}' "
                        f"(already in explicit skills)"
                    )
        except Exception as e:
            logger.warning(f"Failed to load user skills: {str(e)}")

        exist_skills + skills

   
    def _load_public_skills(self,agent_spec: AgentSpec, exist_skills: list[Skill]):
        """Load public skills from Zest skills repository if enabled."""
        if not self.agent_context_spec.load_public_skills:
            return 
        try:
            skills:list[Skill] = []
            public_skills = load_public_skills()
            # Merge public skills with explicit skills, avoiding duplicates
            existing_names = {skill.name for skill in exist_skills}
            for public_skill in public_skills:
                if public_skill.name not in existing_names:
                    skills.append(public_skill)
                else:
                    logger.warning(
                        f"Skipping public skill '{public_skill.name}' "
                        f"(already in existing skills)"
                    )
        except Exception as e:
            logger.warning(f"Failed to load public skills: {str(e)}")
        exist_skills + skills
 
class SubAgentRuntimeStage:

    def run(self, agent_spec: AgentSpec, context, runtime: AgentRuntime) -> AgentRuntime:

        if not agent_spec.subagent_spec:

            return runtime



        system_message = runtime.system_message + SUBAGENT_DESCRIPTION

        tools_map = dict(runtime.tools_map)

        tool_trace = list(runtime.tool_trace)

        prompt_trace = list(runtime.prompt_trace)

        warnings = list(runtime.warnings)



        prompt_trace.append("subagent_description")

        for subagent_spec in agent_spec.subagent_spec:

            try:

                subagent_tools = SubAgentTool.create(

                    subagent_spec=subagent_spec,

                    tools=agent_spec.tools,

                )

                tools_map[subagent_spec.name] = subagent_tools[0]

                tool_trace.append(f"subagent:{subagent_spec.name}")

            except Exception as exc:

                warning = f"Failed to add SubAgentTool '{subagent_spec.name}': {exc}"

                warnings.append(warning)

                logger.error(warning, exc_info=True)



        return runtime.copy_with(

            system_message=system_message,

            tools_map=tools_map,

            prompt_trace=prompt_trace,

            tool_trace=tool_trace,

            warnings=warnings,

        )



class MemoryManagerStage:
    def run(self, agent_spec: AgentSpec, context:RunnerContext, runtime: AgentRuntime) -> AgentRuntime:
        return runtime.copy_with(memory_manager = context.memory_manager)