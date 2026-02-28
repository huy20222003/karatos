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
    active_task: Optional[dict]
    
    # Action results
    action_result: Optional[dict]
    
    # Control flow
    should_investigate: bool
    investigation_complete: bool
    cycle_complete: bool
    
    # Brain 3.0: Dynamic Persona
    mood: str
    energy_level: float
    # Internal motivational drives (0.0 – 1.0) that influence autonomous behavior.
    # Example keys: "safety", "curiosity", "connection", "mastery".
    drives: dict
    
    goals: list[dict] # Autonomously proposed goals/tasks
    error: Optional[str] # Error message if something failed
    replan_context: Optional[str] # Phase 36: LLM-based error analysis
    retry_count: int               # Phase 36: Counter for self-healing loops


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
    active_task: Optional[dict]    # Current task/action decision (used during execution)
    action_result: Optional[Any]   # Result of the last action
    phase: str
    needs_planning: bool           # Whether multi-step planning is required
    cycle_complete: bool
    is_fast_track: bool            # Brain 2.0: Reflex Mode flag
    confidence: float              # Phase 21.1: Brain's current confidence in the interaction
    processed: Optional[Any]       # Metadata from InputPipeline
    reply_to: Optional[str]        # Original message ID to reply to

    # Brain 2.6: Advanced Routing & Escalation Tracking
    initial_decision: Optional[str] # The very first router decision (CHAT/PLAN/NONE)
    final_decision: Optional[str]  # The current active decision after escalation
    decision_history: list[dict]   # List of steps [{decision, reason, at_node, timestamp}]
    escalation_level: int          # Counter for how many times we've pivoted (0 -> 1 -> 2)
    episode_id: Optional[str]      # Brain 2.6: Unique ID for the current conversation episode


    # Brain 3.0: Dynamic Persona
    mood: str
    energy_level: float
    user_affinity: float
    
    # Brain 2.1: Performance Optimization
    query_vector: Optional[list[float]] # Pre-computed embedding
    error: Optional[str]               # Error tracking
    replan_context: Optional[str]      # Phase 36: LLM-based error analysis
    retry_count: int                   # Phase 36: Counter for self-healing loops
    
    # Phase 15.4: Response Embedding for CIE Tier 2
    response_vector: Optional[list[float]]  # Computed after generation
    
    # Phase 19.1: High-Performance Parallel Speculation
    speculative_data_context: Optional[dict]
    
    # Phase 30: Capability Scanner — selected skills/tools for planning
    selected_capabilities: Optional[dict]  # {"skills": [...], "tools": [...], "reasoning": "..."}

