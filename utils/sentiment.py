"""
Sentiment Analysis Utility
Provides lightweight sentiment detection for agent mood evolution.
"""
import re
import logging
from core.brain.model import SharedModelProvider
from core.brain.prompts.registry import get_prompt_registry
from core.brain.utils import get_llm_content
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import settings

logger = logging.getLogger(__name__)

POSITIVE_KEYWORDS = set()
NEGATIVE_KEYWORDS = set()

async def analyze_sentiment(text: str) -> float:
    """
    Analyzes text sentiment using neural LLM reasoning (Digital Soul).
    Returns a score from 0.0 to 1.0.
    0.0 = Very Negative, 0.5 = Neutral, 1.0 = Very Positive.
    """
    if not text:
        return 0.5
        
    # Neural Emotional Intelligence (Brain-based)
    try:
        model = SharedModelProvider.get_model()
        registry = get_prompt_registry()
        
        # Get bot name from settings as fallback for utility
        bot_name = getattr(settings, 'bot_name', 'Niva')
        
        # Load externalized prompt
        prompt_content = registry.get(
            "system.sentiment.sentiment", 
            text=text,
            bot_name=bot_name
        )

        messages = [
            HumanMessage(content=prompt_content)
        ]
        
        response = await model.ainvoke(messages)
        content = get_llm_content(response).strip()
        
        # Extract number
        match = re.search(r"(\d+\.?\d*)", content)
        if match:
            return max(0.0, min(1.0, float(match.group(1))))
            
    except Exception as e:
        logger.warning(f"[SENTIMENT] Neural analysis failed: {e}. Defaulting to neutral.")
    
    return 0.5
