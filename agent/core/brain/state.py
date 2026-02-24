from typing import TypedDict, Optional, Any, List

# ===========================================
# STATE DEFINITION
# ===========================================
class AgentState(TypedDict):
    """The state that flows through the agent's thinking graph"""
    # Current phase
    phase: str
    
    # Input data
    audit_logs: list[dict]
    context: dict
    
    # Analysis results
    anomalies: list[dict]
    current_target: Optional[dict]
    evidence: list[dict]
    
    # Thoughts and decisions
    thoughts: list[str]
    analysis: Optional[str]
    decision: Optional[dict]
    
    # Action results
    action_result: Optional[dict]
    
    # Control flow
    should_investigate: bool
    investigation_complete: bool
    cycle_complete: bool
    
    # Brain 3.0: Dynamic Persona
    mood: str
    energy_level: float
    
    goals: list[dict] # Autonomously proposed goals/tasks
    error: Optional[str] # Error message if something failed


class ChatState(TypedDict):
    """The state for conversational chat with multi-step planning"""
    chat_id: str
    user_message: str
    chat_history: list[dict]
    context: dict
    thoughts: list[str]
    planning_thought: Optional[str] # Thought specific to planning phase
    plan: list[dict]               # List of tasks: [{"task": "...", "realm": "...", "action": "...", "params": {...}}]
    current_step: int              # Index of the current task being executed
    task_outputs: list[Any]        # Results from each executed task
    logic: Optional[str]           # High-priority system instructions
    associative_context: Optional[str] # Phase 27: Semantic/Contextual memories
    response: Any                  # Can be str or dict (structured response)
    decision: Optional[dict]       # Current task decision (used during execution)
    action_result: Optional[Any]   # Result of the last action
    phase: str
    needs_planning: bool           # Whether multi-step planning is required
    cycle_complete: bool
    is_fast_track: bool            # Brain 2.0: Reflex Mode flag

    # Brain 3.0: Dynamic Persona
    mood: str
    energy_level: float
    user_affinity: float
    
    # Brain 2.1: Performance Optimization
    query_vector: Optional[list[float]] # Pre-computed embedding
    error: Optional[str]               # Error tracking
    
    # Phase 15.4: Response Embedding for CIE Tier 2
    response_vector: Optional[list[float]]  # Computed after generation
    
    # Phase 19.1: High-Performance Parallel Speculation
    speculative_data_context: Optional[dict]

