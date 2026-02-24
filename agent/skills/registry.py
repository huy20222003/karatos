from typing import Any, Optional
from .mcp_realm import get_mcp_realm
from .markdown_skill import MarkdownSkill
import os
from utils.logger import get_logger

logger = get_logger()

class SkillRegistry:
    """
    Central hub for all Skill Realms.
    Handles dynamic dispatching of actions to realms.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SkillRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        self.mcp_realm = get_mcp_realm()
        self.definitions_dir = os.path.join(os.path.dirname(__file__), "definitions")
        self.dynamic_skills = {}
        self._load_markdown_skills()
        self._initialized = True
        logger.info(f"SkillRegistry initialized with {len(self.dynamic_skills)} dynamic skills and MCP")
    
    def _load_markdown_skills(self):
        """Load skills from .md files in definitions directory."""
        # Clear schema cache
        if hasattr(self, "_cached_schemas"):
            self._cached_schemas = None
            
        definitions_dir = self.definitions_dir
        if not os.path.exists(definitions_dir):
            return
            
        for filename in os.listdir(definitions_dir):
            if filename.endswith(".md"):
                try:
                    path = os.path.join(definitions_dir, filename)
                    skill = MarkdownSkill(path)
                    
                    # Register purely by skill name
                    key = skill.name.lower()
                    self.dynamic_skills[key] = skill
                except Exception as e:
                    logger.error(f"[Registry] Failed to load skill {filename}: {e}")

    def get(self, name: str) -> Any:
        """Retrieve a skill by name."""
        name_lower = name.lower()
        if ":" in name_lower:
            name_lower = name_lower.split(":", 1)[1]
        
        if name_lower in self.dynamic_skills:
            return self.dynamic_skills[name_lower]
        return None

    async def dispatch(self, skill_name: str, params: dict = None) -> Any:
        """Dispatch an action dynamically to a skill."""
        if params is None: params = {}
        
        # Strip legacy Realm formats if they sneak in
        if ":" in skill_name:
            skill_name = skill_name.split(":", 1)[1]

        # 1. Check MCP Tools
        if self.mcp_realm and hasattr(self.mcp_realm, "has_tool") and await self.mcp_realm.has_tool(skill_name):
            return await self.mcp_realm.execute(skill_name, params)
            
        # 2. Check Dynamic Skills
        skill_name_lower = skill_name.lower()
        if skill_name_lower in self.dynamic_skills:
            logger.info(f"[Registry] Dispatching to dynamic skill: {skill_name_lower}")
            return await self.dynamic_skills[skill_name_lower].execute(params)
            
        logger.error(f"[Registry] Unknown Skill: {skill_name}")
        return {"status": "error", "message": f"Skill '{skill_name}' not found."}

    async def get_tool_schemas(self) -> list[dict]:
        # ... (cached/memoized approach)
        if hasattr(self, "_cached_schemas") and self._cached_schemas:
            return self._cached_schemas
        
        schemas = []
        # ... (same logic as before to build schemas)
        # 1. Dynamic Skills
        for key, skill in self.dynamic_skills.items():
            schemas.append({
                "name": key.lower(),
                "description": f"{skill.description} (Defined in {os.path.basename(skill.file_path)})",
                "parameters": {
                    "type": "object",
                    "properties": skill.input_schema or {},
                    "required": list(skill.input_schema.keys())
                }
            })
            
        # 2. MCP Tools
        if self.mcp_realm:
            mcp_tools = await self.mcp_realm.list_tools()
            for tool in mcp_tools:
                schemas.append({
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                })
        
        self._cached_schemas = schemas
        return schemas

    async def get_relevant_tools(self, query_vector: list[float], limit: int = 8) -> list[dict]:
        """
        Sparse Prompting: Select only relevant tools using semantic similarity.
        """
        import numpy as np
        from utils.embeddings import get_embedding_engine
        
        schemas = await self.get_tool_schemas()
        
        # 1. Ensure tool embeddings are cached
        if not hasattr(self, "_tool_embeddings") or not self._tool_embeddings:
            logger.info("[Registry] Generating semantic embeddings for all tools...")
            engine = get_embedding_engine()
            descriptions = [s["description"] for s in schemas]
            embeddings = await engine.get_embeddings(descriptions)
            self._tool_embeddings = list(zip(schemas, embeddings))
            logger.info(f"[Registry] Cached {len(self._tool_embeddings)} tool embeddings.")
            
        if not query_vector:
            return schemas[:limit] # Fallback to first few if no vector
            
        # 2. Compute Cosine Similarity
        qv = np.array(query_vector)
        matches = []
        for schema, tool_vec in self._tool_embeddings:
            if tool_vec:
                tv = np.array(tool_vec)
                similarity = np.dot(qv, tv) / (np.linalg.norm(qv) * np.linalg.norm(tv))
                matches.append((schema, similarity))
        
        # 3. Sort and limit
        matches.sort(key=lambda x: x[1], reverse=True)
        return [m[0] for m in matches[:limit]]

    async def get_compressed_schemas(self, query_vector: Optional[list[float]] = None) -> str:
        """Return a highly compact text representation of relevant tools."""
        if query_vector:
            tools = await self.get_relevant_tools(query_vector)
            logger.info(f"[Registry] Sparse Prompting active: selected {len(tools)} relevant tools.")
        else:
            tools = await self.get_tool_schemas()
            
        lines = ["AVAILABLE TOOLS (Skill:Action) - Description:"]
        for s in tools:
            lines.append(f"- {s['name']}: {s['description']}")
        return "\n".join(lines)

    def to_json(self) -> str:
        """DEPRECATED: Use get_tool_schemas() instead."""
        import json
        return json.dumps(self.get_tool_schemas(), indent=2)

    async def get_routing_examples(self) -> str:
        """
        Gathers routing examples defined in the frontmatter of all Markdown skills
        and formats them as a string for injection into the Router prompt.
        """
        examples = []
        for key, skill in self.dynamic_skills.items():
            if hasattr(skill, 'routing_examples') and skill.routing_examples:
                for example in skill.routing_examples:
                    examples.append(f"- {example}")
        
        if not examples:
            return "- (No dynamic routing examples found in skills)"
            
        return "\n  ".join(examples)

# Singleton helper
_registry = None
def get_skill_registry():
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
