"""
Database Dynamic Tool
Provides CRUD access to the database with security guardrails.
Parses schema.prisma to understand the database structure.
"""
import re
import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy import text
from config.database import get_db_factory
from utils.logger import get_logger

logger = get_logger()

# Security Configuration
BLOCKED_TABLES = {
    # Auth & Security
    "verification_tokens", 
    "user_encrypted_keys",
    "role_permissions",
    
    # Privacy & Blocking
    "user_blocks",
    "mystic_blocks",
    "bad_words",
    
    # System Internals
    "system_settings",
    "play_fraud_logs",
    "_prisma_migrations"
}

RESTRICTED_COLUMNS = {
    # Auth
    "password", "password_hash", "token", "verification_code",
    
    # Encryption
    "public_key", "private_key", "iv", "encrypted_key",
    "fingerprint", "device_fingerprint", "fingerprint_hash",
    
    # PII
    "email", # Generally hide emails unless specifically needed
    "ip_address", "client_ip", "last_known_ip",
    
    # Geo
    "latitude", "longitude"
}

FORBIDDEN_KEYWORDS = {"DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE", "DELETE"}

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "database_dynamic",
    "aliases": ["dynamic_db", "db_query", "sql"],
    "class_name": "DatabaseDynamic",
    "description": "Dynamic Database Engine: Provides CRUD access to the PostgreSQL database with schema awareness, security guardrails, and SQL injection prevention.",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "actions": [
        {
            "name": "dynamic_db",
            "description": "Execute a SQL query against the database with safety checks. Supports SELECT, INSERT, UPDATE, DELETE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The SQL query to execute."}
                },
                "required": ["query"]
            }
        }
    ]
}

class DatabaseDynamic:
    """
    Dynamic database engine for CRUD operations.
    Includes schema-aware parsing and safety checks.
    """
    def __init__(self, schema_path: str = None):
        if schema_path is None:
            # New path in agent/config
            self.schema_path = os.path.join(os.path.dirname(__file__), "..", "config", "schema.prisma")
        else:
            self.schema_path = schema_path
        
        self.factory = get_db_factory()

    @classmethod
    async def execute(cls, query: str = "", sql_query: str = "", **kwargs) -> Dict[str, Any]:
        """
        Unified entry point for dynamic dispatch.
        Routes: query → execute_query, no query → get_schema_summary.
        """
        instance = cls()
        q = query or sql_query
        if not q:
            schema = instance.get_schema_summary()
            return {"status": "success", "data": schema, "message": "Database schema retrieved."}
        return await instance.execute_query(q)

    def get_schema_summary(self) -> str:
        """
        Parses schema.prisma to return a summary of available tables and columns.
        Enhanced to detect relationships and basic constraints.
        """
        if not os.path.exists(self.schema_path):
            return "Error: Prisma schema file not found."

        tables = {}
        
        try:
            # Split into models
            # shortcuts list to collect cheatsheet items
            shortcuts = []
            
            with open(self.schema_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Split into model blocks
            models = re.findall(r'model\s+(\w+)\s+{(.*?)}', content, re.DOTALL)
            model_names = {m[0] for m in models} # Set of all model names for relation filtering
            
            # NGO: PRE-SCAN FOR DESCRIPTORS (PURELY DYNAMIC)
            # Find all String fields that aren't technical (ID, URL, Code)
            descriptors = {}
            for model_name, body in models:
                m_map = re.search(r'@@map\("([^"]+)"\)', body)
                t_name = m_map.group(1) if m_map else model_name
                
                # Find descriptive strings in this model
                d_fields = []
                for line in body.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("@") or line.startswith("//"): continue
                    parts = line.split()
                    if len(parts) >= 2:
                        f_name, f_type = parts[0], parts[1].strip("?")
                        if f_type == "String" and not f_name.lower().endswith("id") and not any(k in f_name.lower() for k in ["url", "uri", "link", "code", "path", "password", "iv"]):
                            # This is a descriptive field candidate (e.g. username, title, fullName)
                            f_map = re.search(r'@map\("([^"]+)"\)', line)
                            real_name = f_map.group(1) if f_map else f_name
                            d_fields.append(real_name)
                descriptors[model_name] = d_fields

            for model_name, body in models:
                map_match = re.search(r'@@map\("([^"]+)"\)', body)
                table_name = map_match.group(1) if map_match else model_name
                is_restricted = table_name.lower() in BLOCKED_TABLES
                    
                columns = []
                table_hints = []
                lines = body.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("//") or line.startswith("@@"):
                        continue
                    
                    parts = line.split()
                    if len(parts) >= 2:
                        field_name = parts[0]
                        field_type = parts[1].strip("?")
                        if "@relation" in line or "[]" in line:
                            continue
                        if field_type in model_names:
                            continue
                            
                        col_map_match = re.search(r'@map\("([^"]+)"\)', line)
                        column_name = col_map_match.group(1) if col_map_match else field_name
                        
                        # NGO: ADD EXPLICIT JOIN HINTS WITH DESCRIPTORS
                        hint = ""
                        is_fk = False
                        target_model = None
                        
                        if column_name.lower().endswith("id"):
                            base = column_name.lower().removesuffix("id").rstrip("_")
                            target = next((m for m in model_names if m.lower() == base or m.lower() == base + "s" or base == m.lower() + "s"), None)
                            
                            if target:
                                is_fk = True
                                target_model = target
                                tm = next((re.search(r'@@map\("([^"]+)"\)', b).group(1) for n, b in models if n == target and '@@map' in b), target)
                                
                                # Find what descriptive fields are available in the target
                                target_descriptors = descriptors.get(target, [])
                                desc_hint = f" ({', '.join(target_descriptors)})" if target_descriptors else ""
                                hint = f" -> [FK: joins {tm}{desc_hint}]"
                                
                        columns.append(f"{column_name} ({field_type}){hint}")
                        
                        if is_fk and "@unique" in line and target_model:
                             table_hints.append(f"[1:1 Extension of {target_model} - IDENTITY IN PARENT]")
                
                # Append hints to table name
                if table_hints:
                    table_name += f" {table_hints[0]}"
                    # NGO: Explicitly tell them where the identity is
                    for h in table_hints:
                        if "Extension of" in h:
                            parent = h.split("Extension of ")[1].split(" ")[0].lower()
                            parent_model_name = next((m for m in model_names if m.lower() == parent or m.lower() == parent + "s"), None)
                            
                            identity_msg = ""
                            if parent_model_name:
                                # Look up descriptors for the parent
                                parent_descs = descriptors.get(parent_model_name, [])
                                if parent_descs:
                                    identity_msg = f" (Contains: {', '.join(parent_descs[:3])}...)"
                            
                            if not parent.endswith("s"): parent += "s" # Naive pluralization for hint
                            table_name += f" [❌ EMPTY SHELL (NO NAMES). JOIN '{parent}' FOR IDENTITY!]"
                elif not descriptors.get(model_name) and any("FK:" in c for c in columns):
                    table_name += " [⚠️ RAW DATA (NO IDENTITY) - MUST JOIN FKs]"
                
                tables[table_name] = {
                    "columns": columns,
                    "restricted": is_restricted,
                }

                # NGO: Collect shortcuts for the final summary
                if table_hints and "EMPTY SHELL" in table_name:
                    shortcuts.append(f"- To get Name/Identity for '{table_name.split()[0]}': JOIN '{parent}'")

            # Format summary
            summary_parts = ["### DATABASE SCHEMA SUMMARY"]
            
            # NGO: Add Cheatsheet at the top for smaller models
            if shortcuts:
                summary_parts.append("### 🚀 RELATIONSHIP CHEAT SHEET (FOLLOW THESE):")
                summary_parts.append("\n".join(shortcuts))
                summary_parts.append("------------------------------------------------")

            for table, info in tables.items():
                marker = " [RESTRICTED: DELETE/UPDATE]" if info["restricted"] else ""
                summary_parts.append(f"#### TABLE: {table}{marker}")
                summary_parts.append("\n".join([f"- {c}" for c in info["columns"]]))
                
            return "\n\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error parsing schema: {e}")
            return f"Error parsing schema: {str(e)}"

    async def execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Executes a SQL query with advanced security checks.
        If `query` is natural language, auto-converts to SQL using the schema + LLM.
        """
        logger.info(f"[DYNAMIC_DB] Query received: {query[:200]}")
        
        # --- STEP 0: Detect if query is natural language or SQL ---
        sql_to_execute = query.strip()
        is_natural_language = not self._looks_like_sql(sql_to_execute)
        
        if is_natural_language:
            logger.info(f"[DYNAMIC_DB] Detected natural language input. Converting to SQL...")
            sql_to_execute = await self._natural_language_to_sql(sql_to_execute)
            if not sql_to_execute:
                logger.error("[DYNAMIC_DB] NL→SQL conversion failed. No SQL generated.")
                return {"status": "error", "data": [], "sql_executed": None, "row_count": 0,
                        "message": "Could not convert your request to a valid SQL query. Please try rephrasing or provide SQL directly."}
            logger.info(f"[DYNAMIC_DB] Generated SQL: {sql_to_execute[:300]}")
        
        query_upper = sql_to_execute.upper().strip()
        
        # 1. Blocked Table & Keyword Check
        clean_query = re.sub(r'/\*.*?\*/', '', query_upper, flags=re.DOTALL)
        clean_query = re.sub(r'--.*$', '', clean_query, flags=re.MULTILINE)

        # NGO: Specialized check for DELETE - allow only if WHERE is present
        if "DELETE" in clean_query:
            if "WHERE" not in clean_query and "LIMIT" not in clean_query:
                return {"status": "error", "data": [], "sql_executed": sql_to_execute, "row_count": 0,
                        "message": "Mass DELETE without WHERE/LIMIT is strictly forbidden for safety."}
        
        # Other forbidden keywords (except DELETE which we guarded above)
        other_forbidden = FORBIDDEN_KEYWORDS - {"DELETE"}
        if any(kw in clean_query for kw in other_forbidden):
            return {"status": "error", "data": [], "sql_executed": sql_to_execute, "row_count": 0,
                    "message": f"Forbidden SQL keyword detected in query."}

        # Security Resolution Logic
        words = set(re.findall(r'\b\w+\b', clean_query.lower()))
        
        # 2. STRICT TABLE BLOCKING
        for table in BLOCKED_TABLES:
            if table in words:
                return {"status": "error", "data": [], "sql_executed": sql_to_execute, "row_count": 0,
                        "message": f"Access to restricted table '{table}' is forbidden by security policy."}

        # 3. UPDATE/DELETE SCALAR PROTECTION
        is_mutation = "UPDATE" in words or "DELETE" in words
        if is_mutation:
            if "WHERE" not in clean_query and "LIMIT" not in clean_query:
                return {"status": "error", "data": [], "sql_executed": sql_to_execute, "row_count": 0,
                        "message": f"Bulk {words.intersection({'UPDATE', 'DELETE'})} operations must include a WHERE or LIMIT clause."}
            
            if "UPDATE" in words and any(col in words for col in RESTRICTED_COLUMNS):
                return {"status": "error", "data": [], "sql_executed": sql_to_execute, "row_count": 0,
                        "message": "Updating sensitive columns is forbidden."}

        try:
            # 4. Execute
            logger.info(f"[DYNAMIC_DB] Executing SQL: {sql_to_execute[:300]}")
            engine = self.factory.get_sqlalchemy_engine()
            with engine.connect() as conn:
                result = conn.execute(text(sql_to_execute), params or {})
                
                if query_upper.startswith("SELECT") or "RETURNING" in query_upper:
                    rows = [dict(row) for row in result.mappings().all()]
                    
                    # 5. DATA DROPPING (Remove Restricted Columns & URL Patterns)
                    url_patterns = [r'.*url$', r'.*uri$', r'.*link$', r'^avatar$']
                    
                    if rows:
                        for row in rows:
                            for col in list(row.keys()):
                                col_lower = col.lower()
                                if col_lower in RESTRICTED_COLUMNS:
                                    del row[col]
                                elif any(re.search(p, col_lower) for p in url_patterns):
                                    del row[col]
                    
                    row_count = len(rows)
                    logger.info(f"[DYNAMIC_DB] Query executed successfully. Rows returned: {row_count}")
                    return {"status": "success", "data": rows, "sql_executed": sql_to_execute, "row_count": row_count}
                
                try:
                    conn.commit()
                    affected = result.rowcount
                    logger.info(f"[DYNAMIC_DB] Write query executed. Rows affected: {affected}")
                    return {"status": "success", "data": [{"rows_affected": affected}], "sql_executed": sql_to_execute, "row_count": affected}
                except Exception as e:
                    conn.rollback()
                    raise e
                    
        except Exception as e:
            logger.error(f"[DYNAMIC_DB] Query execution failed: {e}")
            # Add a diagnostic hint for self-healing if table is missing
            error_msg = str(e)
            hint = ""
            if "relation" in error_msg and "does not exist" in error_msg:
                hint = " (HINT: The table name might be slightly different or need a schema prefix. Check the schema summary.)"
            
            return {"status": "error", "data": [], "sql_executed": sql_to_execute, "row_count": 0,
                    "message": f"SQL execution error: {error_msg}{hint}"}

    @staticmethod
    def _looks_like_sql(query: str) -> bool:
        """Heuristic: Check if input looks like SQL rather than natural language."""
        q = query.strip().upper()
        sql_starters = ("SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "CREATE", "EXPLAIN", "SHOW")
        return q.startswith(sql_starters)

    async def _natural_language_to_sql(self, nl_query: str) -> Optional[str]:
        """Convert a natural language query to SQL using schema context + LLM."""
        import asyncio
        try:
            schema = self.get_schema_summary()
            
            prompt = f"""You are an expert PostgreSQL query generator. Convert the following natural language request into a valid SQL SELECT query.

DATABASE SCHEMA:
{schema[:8000]}

USER REQUEST: "{nl_query}"

RULES:
1. Return ONLY the SQL query. No explanations, no markdown, no code fences.
2. Use proper JOINs when the user asks about data from multiple tables.
3. Use ORDER BY when the user implies ordering (first, latest, top, etc.).
4. Use LIMIT when the user asks for a specific number of results.
5. Never use DROP, TRUNCATE, ALTER, or any destructive operations.
6. Use actual PostgreSQL column names from the schema (with @map mappings).

SQL:"""

            from core.brain.model import SharedModelProvider
            model = SharedModelProvider.get_model(mode="brief")
            
            response = await asyncio.wait_for(
                model.ainvoke(prompt),
                timeout=60.0
            )
            content = response.content if hasattr(response, "content") else str(response)
            
            # Clean the response — extract just the SQL
            sql = content.strip()
            # Remove markdown code fences if present
            if sql.startswith("```"):
                sql = re.sub(r'^```(?:sql)?\s*', '', sql)
                sql = re.sub(r'\s*```$', '', sql)
            sql = sql.strip().rstrip(";") + ";"
            
            # Final validation
            if not self._looks_like_sql(sql.rstrip(";")):
                logger.warning(f"[DYNAMIC_DB] NL→SQL produced non-SQL output: {sql[:100]}")
                return None
            
            return sql
            
        except Exception as e:
            logger.error(f"[DYNAMIC_DB] NL→SQL conversion error: {e}")
            return None

