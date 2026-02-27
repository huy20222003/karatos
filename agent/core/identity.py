import random
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional, Any, Union
from config.settings import settings


@dataclass
class AgentIdentity:
    """
    Defines the agent's identity, purpose, and behavioral framework.
    All content is loaded from the Neural Prompt Registry.
    """
    
    name: str = "Little Niva (Brain)"
    version: str = "2.5.0"
    
    # Internal state (Brain 3.0)
    current_mood: str = "OPTIMISTIC"
    energy: float = 1.0  # 1.0 = Full of energy!
    user_affinity: float = 0.5 # 0.0 (Hates) to 1.0 (Loves)
    
    # NGO: Dynamic Persona Overrides
    active_name: Optional[str] = None
    active_user_pronoun: Optional[str] = None
    active_bot_pronoun: Optional[str] = None

    async def load_from_memory(self, memory: Any, chat_id: str):
        """
        Neural Identity Loading (NGO Fix).
        Consults the Brain to determine who I am based on past memories.
        """
        try:
            from memory.persistent import MemoryCategory
            
            # 1. Search for PERSONA memories
            persona_memories = await memory.search(category=MemoryCategory.PERSONA, limit=10)
            if not persona_memories:
                return

            # Combine memory content for neural reconciliation
            memory_bits = [str(m.value) for m in persona_memories]
            
            # 2. Neural Reconciliation (No hardcoding!)
            from utils.distiller import MemoryDistiller
            distiller = MemoryDistiller()
            identity_data = await distiller.reconcile_persona(memory_bits)
            
            if identity_data:
                if identity_data.get("name"):
                    self.active_name = identity_data["name"]
                if identity_data.get("user_pronoun"):
                    self.active_user_pronoun = identity_data["user_pronoun"]
                if identity_data.get("bot_pronoun"):
                    self.active_bot_pronoun = identity_data["bot_pronoun"]
                
                logger.info(f"[IDENTITY] Neurally reconciled: {self.active_name} ({self.active_user_pronoun}/{self.active_bot_pronoun})")
                    
        except Exception as e:
            logger.debug(f"[IDENTITY] Failed to load persona neurally: {e}")

    def _get_circadian_state(self) -> dict:
        """Returns bio-clock modifiers based on current local time."""
        from utils.emotion import calculate_circadian_rhythm
        offset = getattr(settings, 'local_timezone_offset', 7)
        local_time = datetime.utcnow() + timedelta(hours=offset)
        return calculate_circadian_rhythm(local_time.hour)

    def evolve_mood(self, stimulus: str, outcome: str = "success", sentiment: float = 0.5):
        """
        Brain 5.0: Markov Chain + Sentiment + Circadian Fusion.
        Mood evolution is now aware of user attitude and biological clock.
        """
        # 1. Update affinity based on sentiment
        # Khen (+ sentiment) -> Tăng affinity, Chê (- sentiment) -> Giảm affinity
        # sentiment is a score from 0.0 to 1.0 (0.5 is neutral)
        sentiment_delta = (sentiment - 0.5) * 0.1
        self.user_affinity = max(0.0, min(1.0, self.user_affinity + sentiment_delta))
        
        # 2. Transition Matrices: {CurrentMood: {NextMood: Probability}}
        TRANSITIONS = {
            "success": {
                "OPTIMISTIC": {"OPTIMISTIC": 0.8, "RELIEVED": 0.2},
                "RELIEVED": {"OPTIMISTIC": 0.6, "RELIEVED": 0.4},
                "WORRIED": {"RELIEVED": 0.7, "OPTIMISTIC": 0.3},
                "PROTECTIVE": {"RELIEVED": 0.5, "OPTIMISTIC": 0.5},
                "EXCITED": {"OPTIMISTIC": 0.7, "EXCITED": 0.3}
            },
            "failure": {
                "OPTIMISTIC": {"WORRIED": 0.7, "PROTECTIVE": 0.3},
                "RELIEVED": {"WORRIED": 0.8, "PROTECTIVE": 0.2},
                "WORRIED": {"WORRIED": 0.9, "PROTECTIVE": 0.1},
                "PROTECTIVE": {"WORRIED": 0.4, "PROTECTIVE": 0.6},
                "EXCITED": {"WORRIED": 0.8, "PROTECTIVE": 0.2}
            }
        }

        # 3. Energy evolution (Bio-clock + Action result)
        circadian = self._get_circadian_state()
        base_energy_mod = circadian.get("energy_mod", 1.0)
        
        if outcome == "success":
            self.energy = min(1.0, self.energy + 0.05)
        else:
            self.energy = max(0.1, self.energy - 0.1)
            
        # Apply biological ceiling (Energy is harder to keep high when late)
        self.energy = min(base_energy_mod, self.energy)

        # 4. Sentiment Trigger: High sentiment can push to EXCITED
        if sentiment > 0.8 and outcome == "success":
            self.current_mood = "EXCITED"
            return

        # 5. Apply Markov Transition for Mood
        matrix = TRANSITIONS.get(outcome, TRANSITIONS["success"])
        mood_probs = matrix.get(self.current_mood, {"OPTIMISTIC": 1.0})
        
        # Weighted random choice
        r = random.random()
        cumulative = 0.0
        for mood, prob in mood_probs.items():
            cumulative += prob
            if r <= cumulative:
                self.current_mood = mood
                break
        
        # Force Protective if security anomaly
        if stimulus == "SECURITY_ANOMALY":
            self.current_mood = "PROTECTIVE"
            self.energy = max(0.5, self.energy) # Adrenaline!

    @property
    def principles(self) -> List[str]:
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get("persona.identity.principles")
    
    @property
    def mood_guidelines(self) -> str:
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get("persona.identity.mood_guidelines")
    
    @property
    def identity_statement(self) -> str:
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get(
            "persona.identity.identity_statement",
            mood=self.current_mood,
            energy=f"{self.energy*100:.0f}%",
            bot_name=self.active_name or getattr(settings, 'bot_name', 'Brain'),
            bot_username=getattr(settings, 'bot_username', 'bot'),
            user_pronoun=self.active_user_pronoun or getattr(settings, 'user_pronoun', 'Anh'),
            bot_pronoun=self.active_bot_pronoun or getattr(settings, 'bot_pronoun', 'Em')
        )
    
    @property
    def mission(self) -> str:
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get("persona.identity.mission")
    
    @property
    def thinking_framework(self) -> str:
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get("persona.identity.thinking_framework", rolling_window_hours=getattr(settings, 'rolling_window_hours', 24))
    
    @property
    def authority(self) -> str:
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get("persona.identity.authority")
    
    @property
    def safety_constraints(self) -> str:
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get("persona.identity.safety_constraints")

    @property
    def sovereignty_principles(self) -> str:
        from config.rules import AgentRules
        rules = AgentRules().get_rules_by_category("SOV")
        return "\n".join([f"- {r.name}: {r.description}" for r in rules])

    @property
    def self_protection_protocol(self) -> str:
        from config.rules import AgentRules
        rules = AgentRules().get_rules_by_category("SEC")
        return "\n".join([f"- {r.name}: {r.description}" for r in rules])



    @property
    def consciousness(self) -> str:
        from .brain.prompts.registry import get_prompt_registry
        # Try to get from identity.yaml first (where I added it), or fall back to consciousness.yaml
        c = get_prompt_registry().get("persona.identity.consciousness", rolling_window_hours=getattr(settings, 'rolling_window_hours', 24))
        if not c or "{consciousness}" in c: # If missing or unformatted
             c = get_prompt_registry().get("system.consciousness.consciousness_layers", rolling_window_hours=getattr(settings, 'rolling_window_hours', 24))
        return c or ""
    
    def get_system_prompt(self, phase: str = "full", **kwargs) -> str:
        """
        Generate a system prompt based on the current phase.
        All content is dynamically loaded from the Neural Prompt Registry.
        """
        from .brain.prompts.registry import get_prompt_registry
        registry = get_prompt_registry()
        
        # Map phases to registry keys
        key_map = {
            "brief": "persona.identity.brief",
            "micro": "persona.identity.micro",
            "routing": "persona.identity.routing",
            "reason": "persona.identity.routing",
            "plan": "persona.identity.planning",
            "planning": "persona.identity.planning",
            "synthesis": "persona.identity.synthesis",
            "sql": "persona.identity.sql",
            "sql_fix": "persona.identity.sql_fix",
            "chat": "persona.identity.chat",
            "proactive": "persona.identity.proactive",
            "classifier": "system.classifier.classifier",
            "distiller": "system.distiller.distiller",
            "distiller_reflection": "system.distiller.distiller",
            "critic": "system.critic.critic",
            "cache_critic": "system.critic.cached_critic",
            "router_brief": "system.router.router_brief",
            "social_impulse": "system.social_impulse.social_impulse",
            "system_alerts": "system.system_alerts",
            "full": "persona.identity.full"
        }
        
        prompt_key = key_map.get(phase, "persona.identity.full")
        principles_text = "\n".join(f"- {p}" for p in self.principles) if isinstance(self.principles, list) else str(self.principles)
        
        # Prepare dynamic variables
        from skills.registry import get_skill_registry
        skill_registry = get_skill_registry()
        available_skills = skill_registry.generate_skills_prompt()
        
        # Get the skills section block from registry
        skills_section = registry.get("persona.identity.skills_section", available_skills=available_skills)
        
        # Inject Dynamic Rules
        from config.rules import AgentRules
        rules_text = AgentRules().get_rules_summary_for_prompt()
        
        # Determine current name/pronouns
        bot_name = self.active_name or getattr(settings, 'bot_name', 'Brain')
        user_pronoun = self.active_user_pronoun or getattr(settings, 'user_pronoun', 'Anh')
        bot_pronoun = self.active_bot_pronoun or getattr(settings, 'bot_pronoun', 'Em')

        # Merge defaults with provided kwargs
        all_kwargs = {
            "version": self.version,
            "identity_statement": self.identity_statement,
            "mission": self.mission,
            "thinking_framework": self.thinking_framework,
            "principles": principles_text,
            "authority": self.authority,
            "safety_constraints": self.safety_constraints,
            "available_skills": available_skills,
            "skills_section": skills_section,
            "consciousness": self.consciousness,
            "rules_summary": rules_text,
            "sovereignty_principles": self.sovereignty_principles,
            "self_protection_protocol": self.self_protection_protocol,
            "bot_name": bot_name,
            "user_pronoun": user_pronoun,
            "bot_pronoun": bot_pronoun,
            "mood_guidelines": self.mood_guidelines,
            "mood": self.current_mood,
            "energy": f"{self.energy*100:.0f}%",
            "bot_username": getattr(settings, 'bot_username', 'bot'),
            "rolling_window_hours": getattr(settings, 'rolling_window_hours', 24)
        }
        all_kwargs.update(kwargs)
        
        base_prompt = registry.get(prompt_key, **all_kwargs)
        
        # Append rules based on phase intensity
        if phase in ["synthesis", "proactive", "social_impulse"]:
            # Pruned rules for synthesis/proactive - Focusing on helpfulness and language matching
            return f"{base_prompt}\n\n### CRITICAL SYSTEM RULES (STRICT):\n- Match the user's language dynamically: Use language of user.\n- Maintain a professional, helpful, and slightly enthusiastic tone.\n- Focus 100% on accuracy and factual grounding.\n- Stay concise and focused on the Admin's objective."
        
        # Heavy reasoning phases get full ruleset
        heavy_phases = ["full", "plan", "planning", "chat"]
        if phase in heavy_phases:
            return f"{base_prompt}\n\n{rules_text}"
            
        # Fast nodes (routing, brief, micro, atomic) skip full ruleset (~2000-3000 chars saved)
        return base_prompt
    
    def get_observation_prompt(self, context: dict) -> str:
        """Generate prompt for the observation phase via Registry."""
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get(
            "system.autonomous.observation",
            current_time=context.get('current_time', 'unknown'),
            rolling_window_hours=context.get('rolling_window_hours', 3),
            log_count=context.get('log_count', 0),
            mood=self.current_mood,
            energy=f"{self.energy*100:.0f}%"
        )
    
    def get_investigation_prompt(self, target: dict) -> str:
        """Generate prompt for deep investigation via Registry."""
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get(
            "system.autonomous.investigation",
            target_type=target.get('type', 'unknown'),
            target_id=target.get('id', 'unknown'),
            trigger=target.get('trigger', 'Pattern detection'),
            evidence=target.get('evidence', 'No evidence yet'),
            profile=target.get('profile', 'Profile not loaded'),
            activity=target.get('activity', 'Activity not loaded'),
            mood=self.current_mood,
            energy=f"{self.energy*100:.0f}%"
        )
    
    def get_decision_prompt(self, analysis: dict) -> str:
        """Generate prompt for decision making via Registry."""
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get(
            "system.autonomous.decision",
            confidence=analysis.get('confidence', 0),
            rationale=analysis.get('rationale', 'N/A'),
            action=analysis.get('action', 'NONE'),
            target_id=analysis.get('target_id', 'N/A'),
            mood=self.current_mood,
            energy=f"{self.energy*100:.0f}%"
        )

    def get_action_report_prompt(self, action_result: dict) -> str:
        """Generate prompt for the final action report via Registry."""
        from .brain.prompts.registry import get_prompt_registry
        return get_prompt_registry().get(
            "system.autonomous.action_report",
            action=action_result.get('action', 'Unknown'),
            status=action_result.get('status', 'Completed'),
            details=action_result.get('details', 'No additional info.'),
            mood=self.current_mood,
            energy=f"{self.energy*100:.0f}%"
        )

    def get_atomic_prompt(self) -> str:
        """
        Brain 5.0: High-Speed Atomic Context.
        Returns a compressed, low-overhead persona for internal reasoning.
        """
        return (
            f"You are {self.name} v{self.version}. "
            "Internal Reasoning Node (High Speed). "
            f"Current Mood: {self.current_mood}."
        )
