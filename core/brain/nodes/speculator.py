
import re
from core.brain.state import ChatState
from utils.logger import get_logger
from tools.database_dynamic import DatabaseDynamic

logger = get_logger()

# Keywords that trigger DB Schema Pre-fetching
DB_KEYWORDS = {
    "database", "db", "sql", "query", "schema", "table",
    "user", "account", "profile", "ban", "block",
    "money", "transaction", "payment", "doanh thu", "revenue",
    "track", "music", "nivasound", "artist", "album",
    "log", "audit", "history", "trace", "monitor"
}

async def data_speculator_node(state: ChatState) -> ChatState:
    """
    DATA SPECULATOR: 
    Detects if the user message likely requires database access.
    Pre-fetches schema context in parallel with the Router to save time.
    """
    msg = state.get("user_message", "").lower()
    
    # Check for keywords (Simple heuristic for speed)
    # intersection of msg words and DB_KEYWORDS
    msg_words = set(re.findall(r'\w+', msg))
    if msg_words.intersection(DB_KEYWORDS):
        logger.info(f"[SPECULATOR] Detected DB intent keywords. Pre-fetching logic schema...")
        
        try:
            # Initialize Dynamic DB (lightweight, just path setup)
            db = DatabaseDynamic()
            
            # Fetch Schema Summary (Reads local file, fast)
            schema_summary = db.get_schema_summary()
            
            # Inject into state
            state["speculative_data_context"] = {
                "schema_summary": schema_summary,
                "source": "speculator_prefetch"
            }
            logger.debug("[SPECULATOR] Schema context injected successfully.")
            
        except Exception as e:
            logger.warning(f"[SPECULATOR] Failed to pre-fetch schema: {e}")
            state["speculative_data_context"] = {}
    else:
        logger.debug("[SPECULATOR] No DB keywords detected. Skipping pre-fetch.")
        state["speculative_data_context"] = {}

    return state
