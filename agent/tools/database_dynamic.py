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

FORBIDDEN_KEYWORDS = {"DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE"}

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
        Executes a raw SQL query with advanced security checks.
        """
        query_upper = query.upper().strip()
        
        # 1. Blocked Table & Keyword Check (Regex for better precision)
        # Prevent multiline comment bypasses
        clean_query = re.sub(r'/\*.*?\*/', '', query_upper, flags=re.DOTALL)
        clean_query = re.sub(r'--.*$', '', clean_query, flags=re.MULTILINE)

        if any(kw in clean_query for kw in FORBIDDEN_KEYWORDS):
            return [{"error": "Forbidden SQL keyword detected (DROP, TRUNCATE, ALTER, etc.)"}]

        # Security Resolution Logic
        words = set(re.findall(r'\b\w+\b', clean_query.lower()))
        
        # 2. STRICT TABLE BLOCKING (Any operation)
        # Check if any blocked table is mentioned in the query
        for table in BLOCKED_TABLES:
            if table in words:
                return [{"error": f"Access to restricted table '{table}' is forbidden by security policy."}]

        # 3. UPDATE/DELETE SCALAR PROTECTION
        if "UPDATE" in words and any(col in words for col in RESTRICTED_COLUMNS):
             return [{"error": "Updating sensitive columns is forbidden."}]

        try:
            # 4. Execute
            engine = self.factory.get_sqlalchemy_engine()
            with engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                
                if query_upper.startswith("SELECT") or "RETURNING" in query_upper:
                    rows = [dict(row) for row in result.mappings().all()]
                    
                    # 5. DATA REDACTION (Mask Restricted Columns & URL Patterns)
                    # NGO: Using pattern matching to avoid hardcoding field names
                    url_patterns = [r'.*url$', r'.*uri$', r'.*link$', r'^avatar$']
                    
                    if rows:
                        for row in rows:
                            for col in list(row.keys()):
                                col_lower = col.lower()
                                # 5. DATA DROPPING (Remove Restricted Columns & URL Patterns)
                                # NGO: Dropping columns instead of redacting to keep reports focused.
                                if col_lower in RESTRICTED_COLUMNS:
                                    del row[col]
                                elif any(re.search(p, col_lower) for p in url_patterns):
                                    del row[col]
                    
                    return rows
                
                try:
                    conn.commit()
                    return [{"status": "success", "rows_affected": result.rowcount}]
                except Exception as e:
                    conn.rollback()
                    raise e
                    
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return [{"error": str(e)}]
