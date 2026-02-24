from pydantic import BaseModel, Field
from typing import List, Optional
import time
import uuid

class MailboxMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    target: str
    chat_id: str
    content: str
    timestamp: float = Field(default_factory=time.time)

class AgentIdentity(BaseModel):
    name: str
    username: str
