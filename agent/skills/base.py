from typing import Any, Optional
from abc import ABC, abstractmethod

class BaseSkillRealm(ABC):
    """
    Base class for a functional Skill Realm.
    A Realm is a broad domain of capabilities (e.g., Data, Communication).
    """
    
    @abstractmethod
    async def execute(self, action: str, params: dict) -> Any:
        """
        Execute a specific action within this realm.
        
        Args:
            action: The name of the action to perform
            params: Dictionary of parameters for the action
            
        Returns:
            The result of the action execution
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__}>"
