import os
from typing import Any, Dict, List, Optional
from .markdown_skill import MarkdownSkill
from utils.logger import get_logger

logger = get_logger()

class SkillRegistry:
    """
    Central hub for managing skills.
    Delegates tool execution to ToolRegistry (realm-free architecture).
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SkillRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        
        self.skills_root = os.path.join(os.path.dirname(__file__), "definitions")
        self.skills: Dict[str, MarkdownSkill] = {}
        self._tool_registry = None  # Lazy-loaded
        self._load_skills()
        self._initialized = True
        logger.info(f"SkillRegistry initialized with {len(self.skills)} skills.")
    
    @property
    def tool_registry(self):
        """Lazy-load ToolRegistry to avoid circular imports."""
        if self._tool_registry is None:
            from tools.registry import get_tool_registry
            self._tool_registry = get_tool_registry()
        return self._tool_registry

    def _load_skills(self):
        if not os.path.exists(self.skills_root):
            os.makedirs(self.skills_root, exist_ok=True)
            return

        for filename in os.listdir(self.skills_root):
            if filename.endswith(".md"):
                self._add_skill(os.path.join(self.skills_root, filename))

        for foldername in os.listdir(self.skills_root):
            # Skip the _template folder — it's not a real skill
            if foldername.startswith("_"):
                continue
            folder_path = os.path.join(self.skills_root, foldername)
            if os.path.isdir(folder_path):
                skill_md_path = os.path.join(folder_path, "SKILL.md")
                if os.path.exists(skill_md_path):
                    self._add_skill(skill_md_path)

    def _add_skill(self, path: str):
        try:
            skill = MarkdownSkill(path)
            self.skills[skill.name.lower()] = skill
        except Exception as e:
            logger.error(f"[Registry] Failed to load skill at {path}: {e}")

    def get_skill(self, name: str) -> Optional[MarkdownSkill]:
        return self.skills.get(name.lower())

    async def dispatch(self, action_name: str, params: dict = None) -> Any:
        """
        Dispatch an action. Priority:
        1. Markdown Skills (instructional guidance for Brain)
        2. ToolRegistry (tool execution)
        """
        if params is None: params = {}
        
        clean_action = action_name.lower().strip()
        if clean_action.startswith("mcp:"):
            parts = clean_action.split(":")
            if len(parts) == 2:
                 clean_action = parts[1]

        # 1. Shadowing Prevention: If params are provided, prioritize ToolRegistry
        # Markdown skills are instructional for the LLM. If the code is calling dispatch with params,
        # it intends to execute a tool, not just read instructions.
        if params and clean_action in self.tool_registry._dispatch_map:
            return await self.tool_registry.dispatch(action_name, params)

        # 2. Check Markdown Skills (instructional/guidance)
        skill = self.get_skill(clean_action)
        if skill:
            return {
                "status": "success",
                "skill_type": "markdown",
                "instructions": skill.instructions,
                "metadata": skill.metadata,
                "message": f"Specialized skill '{clean_action}' activated. Proceed by following the instructions below."
            }
            
        # 3. Delegate to ToolRegistry (fallback for everything else)
        return await self.tool_registry.dispatch(action_name, params)

    def generate_skills_prompt(self) -> str:
        if not self.skills: return "(No specialized skills available)"
        lines = []
        for name, skill in self.skills.items():
            try: rel_path = os.path.relpath(skill.file_path, os.path.dirname(os.path.dirname(os.path.dirname(self.skills_root))))
            except: rel_path = skill.file_path
            lines.append(f"- {skill.name}: {skill.description} (location: {rel_path})")
        return "\n".join(lines)

    def get_skill_summaries(self) -> str:
        """Return compact name:description pairs for capability scanning."""
        lines = []
        for name, skill in self.skills.items():
            lines.append(f"- {skill.name}: {skill.description}")
        return "\n".join(lines)

    def get_enriched_capabilities(self) -> str:
        """
        Produce a high-fidelity summary of all capabilities (Skills + Tools).
        Includes names, descriptions, aliases, and routing examples.
        """
        lines = ["### 🟢 SPECIALIZED SKILLS (Reasoning Guidance)"]
        for skill in self.skills.values():
            examples = skill.metadata.get("routing_examples", [])
            # Format examples nicely
            examples_str = ""
            if examples:
                examples_str = "\n     - Examples: " + " | ".join(examples[:3])
            lines.append(f"- **{skill.name}**: {skill.description}{examples_str}")
            
        lines.append("\n### 🛠️ EXECUTABLE TOOLS (Action & Data Execution)")
        tool_schemas = self.tool_registry.list_tools()
        for t in tool_schemas:
            aliases = t.get("aliases", [])
            alias_str = f" (Aliases: {', '.join(aliases)})" if aliases else ""
            params = t.get("parameters", {}).get("properties", {})
            param_str = f" [Params: {', '.join(params.keys())}]" if params else ""
            lines.append(f"- **{t['name']}**{alias_str}: {t['description']}{param_str}")
            
        return "\n".join(lines)

    async def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Collect and normalize schemas from ToolRegistry + Skills."""
        schemas = []
        
        # 1. ToolRegistry schemas (tools + MCP)
        try:
            tool_schemas = await self.tool_registry.get_tool_schemas()
            # Ensure aliases are preserved in the schema for the planner
            schemas.extend(tool_schemas)
        except Exception as e:
            logger.warning(f"[Registry] Failed to get tool schemas: {e}")
                
        # 2. Markdown Skills
        for skill in self.skills.values():
            p = skill.metadata.get("parameters") or skill.metadata.get("inputs") or skill.metadata.get("input_schema") or {}
            if p and "properties" not in p and isinstance(p, dict):
                 p = {"type": "object", "properties": p}
            s = {
                "name": skill.name,
                "description": skill.description,
                "parameters": p,
                "routing_examples": skill.metadata.get("routing_examples", [])
            }
            schemas.append(s)
            
        return schemas

    async def get_routing_examples(self) -> str:
        """Collect and format all routing examples from loaded skills."""
        examples = []
        for skill in self.skills.values():
            if skill.metadata and "routing_examples" in skill.metadata:
                examples.extend(skill.metadata["routing_examples"])
        
        if not examples:
            return ""
            
        return "\n".join([f"- {ex}" for ex in examples])

_registry = None
def get_skill_registry():
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
