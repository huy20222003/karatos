import os
import re
import yaml
from typing import Any, Dict, Optional, List
from utils.logger import get_logger

logger = get_logger()

class MarkdownSkill:
    """
    Represents a skill defined in a Markdown file.
    Follows the AgentSkills/OpenClaw pattern: Instruction-first, not execution-first.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.name = ""
        self.description = ""
        self.metadata = {}
        self.instructions = ""
        self._parse_file()
        
    def _parse_file(self):
        """Parse the markdown file to extract metadata and instructions."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Skill file not found: {self.file_path}")
            
        with open(self.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 1. Parse YAML Frontmatter
        frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if frontmatter_match:
            try:
                self.metadata = yaml.safe_load(frontmatter_match.group(1))
                self.name = self.metadata.get("name", os.path.basename(os.path.dirname(self.file_path)))
                self.description = self.metadata.get("description", "")
                self.enabled = self.metadata.get("enabled", False)
            except yaml.YAMLError as e:
                logger.error(f"[MarkdownSkill] Error parsing frontmatter in {self.file_path}: {e}")
        
        # 2. Extract Instructions (everything after frontmatter)
        self.instructions = content
        if frontmatter_match:
            self.instructions = content[frontmatter_match.end():].strip()
                
    def get_summary(self) -> str:
        """Get a 1-line summary for the system prompt."""
        return f"{self.name}: {self.description}"

    def get_full_prompt(self) -> str:
        """Get the full content for the agent to read and follow."""
        return f"# Skill: {self.name}\n\n{self.instructions}"
