"""
Database Reader Tool
Direct read-only access to PostgreSQL database
"""
import json
import os
import pandas as pd
import polars as pl
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from config.database import get_db_factory
from utils.logger import get_logger

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "database_reader",
    "aliases": ["db_reader", "db_reports", "db_health"],
    "class_name": "DatabaseReader",
    "description": "Database Reports & Health: Direct access to PostgreSQL for system health, audit logs, user activity, and pre-defined administrative reports.",
    "actions": [
        {
            "name": "db_reports",
            "description": "Execute a pre-defined database report operation. Use 'method' to specify report type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "description": "Report method: get_system_health, get_pending_reports, get_audit_logs, get_user_activity, get_service_status, execute_custom_query."},
                    "query": {"type": "string", "description": "SQL SELECT query (only for execute_custom_query)."},
                    "user_id": {"type": "string", "description": "User ID for user-specific activity reports."},
                    "hours": {"type": "integer", "description": "Hours to look back."},
                    "limit": {"type": "integer", "description": "Max results to return."}
                },
                "required": []
            }
        }
    ]
}

class DatabaseReader:
    """
    Reader for system stats and logs.
    Uses direct database connection for real-time data.
    """
    def __init__(self):
        self.factory = get_db_factory()

    @classmethod
    async def execute(cls, method: str = None, _dispatched_action: str = "", **kwargs) -> Dict[str, Any]:
        """Unified entry point for dynamic dispatch."""
        instance = cls()
        
        # Determine the target method
        route = method or _dispatched_action or "get_system_health"
        
        # Map of available methods
        method_map = {
            "get_system_health": instance.get_system_health,
            "get_pending_reports": instance.get_pending_reports,
            "get_audit_logs": instance.get_audit_logs,
            "get_user_activity": instance.get_user_activity,
            "get_user_by_id": instance.get_user_by_id,
            "get_user_by_username": instance.get_user_by_username,
            "get_service_status": instance.get_service_status,
            "get_recent_incidents": instance.get_recent_incidents,
            "execute_custom_query": instance.execute_custom_query,
            "db_health": instance.get_system_health,
            "db_reader": instance.get_system_health,
            "db_reports": instance.get_system_health,
            "db_read": instance.get_system_health, # Keep old alias for backward compatibility but hidden from metadata
        }
        
        handler = method_map.get(route)
        if not handler:
            return {"status": "error", "message": f"Unknown method: {route}. Available: {', '.join(method_map.keys())}"}
        
        try:
            # ROBUST DISPATCH: Filter kwargs to only pass what the handler accepts
            import inspect
            sig = inspect.signature(handler)
            filtered_kwargs = {
                k: v for k, v in kwargs.items() 
                if k in sig.parameters and k not in ("_dispatched_action", "method")
            }
            
            # Special case: if we have a 'query' but no method, and we're in a generic call, try custom query
            if not method and "query" in kwargs and route in ["db_reports", "db_read"]:
                handler = instance.execute_custom_query
                filtered_kwargs = {"query": kwargs["query"]}

            # Sync methods — call directly
            if inspect.iscoroutinefunction(handler):
                result = await handler(**filtered_kwargs)
            else:
                result = handler(**filtered_kwargs)
                
            return {"status": "success", "data": result}
        except Exception as e:
            logger.error(f"[DATABASE_READER] {route} failed: {e}")
            return {"status": "error", "message": str(e)}
    
    @contextmanager
    def get_session(self):
        """Context manager for database sessions (delegates to factory's engine)"""
        engine = self.factory.get_sqlalchemy_engine()
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    def get_pending_reports(self, limit: int = 10) -> list[dict]:
        """
        Get OPEN reports that need moderation.
        Returns reports with reporter and target information.
        """
        query = """
            SELECT 
                r.id,
                r.target_type as "targetType",
                r.target_id as "targetId",
                r.reason,
                r.content,
                r.status,
                r.created_at as "createdAt",
                u.username as "reporterUsername",
                u.id as "reporterId"
            FROM reports r
            LEFT JOIN users u ON r.reporter_id = u.id
            WHERE r.status = 'OPEN'
            ORDER BY r.created_at DESC
            LIMIT :limit
        """
        
        with self.get_session() as session:
            result = session.execute(text(query), {"limit": limit})
            reports = []
            
            for row in result.mappings().all():
                reports.append({
                    "id": str(row["id"]),
                    "targetType": row["targetType"],
                    "targetId": str(row["targetId"]) if row["targetId"] else None,
                    "reason": row["reason"],
                    "content": row["content"],
                    "status": row["status"],
                    "createdAt": row["createdAt"].isoformat() if row["createdAt"] else None,
                    "reporterUsername": row["reporterUsername"],
                    "reporterId": str(row["reporterId"]) if row["reporterId"] else None
                })
            
            return reports
    
    def get_audit_logs(
        self,
        hours: int = 3,
        limit: int = 1000,
        action_types: list[str] = None
    ) -> list[dict]:
        """
        Fetch audit logs within the specified time window.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of records to fetch
            action_types: Filter by specific action types
        
        Returns:
            List of audit log entries
        """
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Join with users table to get the role for better context
        query = """
            SELECT 
                a.id,
                a."userId",
                a.action,
                a.resource,
                a.details,
                a."ipAddress",
                a."userAgent",
                a.created_at as "createdAt",
                u.role as "userRole"
            FROM audit_logs a
            LEFT JOIN users u ON a."userId" = u.id
            WHERE a.created_at >= :start_time
        """
        
        params = {"start_time": start_time, "limit": limit}
        
        if action_types:
            query += " AND a.action = ANY(:action_types)"
            params["action_types"] = action_types
        
        query += " ORDER BY a.created_at DESC LIMIT :limit"
        
        try:
            with self.get_session() as session:
                result = session.execute(text(query), params)
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch audit logs: {e}")
            return []
    
    def get_user_activity(
        self,
        user_id: str,
        hours: int = 24
    ) -> dict[str, Any]:
        """
        Get comprehensive activity data for a specific user.
        
        Args:
            user_id: The user's UUID
            hours: Hours to look back
        
        Returns:
            Dictionary containing user profile and activity summary
        """
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        with self.get_session() as session:
            # Get user profile
            # Prisma User model uses camelCase for some fields
            user_query = """
                SELECT 
                    id, username, email, role, 
                    "isBanned",
                    "isVerified",
                    "subscription_plan_id" as "subscriptionPlanId",
                    created_at as "createdAt"
                FROM users
                WHERE id = :user_id AND deleted_at IS NULL
            """
            user_result = session.execute(text(user_query), {"user_id": user_id})
            user = user_result.mappings().first()
            
            if not user:
                return None
            
            # Get audit log count by action
            action_query = """
                SELECT action, COUNT(*) as count
                FROM audit_logs
                WHERE "userId" = :user_id AND created_at >= :start_time
                GROUP BY action
            """
            action_result = session.execute(
                text(action_query), 
                {"user_id": user_id, "start_time": start_time}
            )
            action_counts = {row.action: row.count for row in action_result}
            
            # Get play history count
            play_query = """
                SELECT COUNT(*) as count
                FROM play_history
                WHERE "userId" = :user_id AND played_at >= :start_time
            """
            play_result = session.execute(
                text(play_query),
                {"user_id": user_id, "start_time": start_time}
            )
            play_count = play_result.scalar() or 0
            
            return {
                "user": dict(user),
                "activity": {
                    "period_hours": hours,
                    "audit_actions": action_counts,
                    "play_count": play_count
                }
            }
            
    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        """Get basic user info by ID"""
        query = 'SELECT id, username, role, email, "isBanned" FROM users WHERE id = :user_id AND deleted_at IS NULL'
        try:
            with self.get_session() as session:
                result = session.execute(text(query), {"user_id": user_id})
                row = result.mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get user by ID: {e}")
            return None

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """Get user info by username (case-insensitive)"""
        query = 'SELECT id, username, role, email, "isBanned" FROM users WHERE username ILIKE :username AND deleted_at IS NULL'
        try:
            with self.get_session() as session:
                result = session.execute(text(query), {"username": username})
                row = result.mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get user by username: {e}")
            return None

    def get_user_associations(self, user_id: str, days: int = 30) -> list[dict]:
        """
        Find other users associated with this user ID (e.g., via IP address).
        Crucial for detecting multi-account abuse.
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        
        # SQL logic:
        # 1. Find all IPs used by this user
        # 2. Find all other users who used those same IPs
        query = """
            WITH target_ips AS (
                SELECT DISTINCT "ipAddress"
                FROM audit_logs
                WHERE "userId" = :user_id 
                AND "ipAddress" IS NOT NULL
                AND created_at >= :start_time
            )
            SELECT DISTINCT
                a."userId",
                u.username,
                u.role,
                a."ipAddress",
                COUNT(*) as activity_count
            FROM audit_logs a
            JOIN users u ON a."userId" = u.id
            WHERE a."ipAddress" IN (SELECT "ipAddress" FROM target_ips)
            AND a."userId" != :user_id
            AND a.created_at >= :start_time
            GROUP BY a."userId", u.username, u.role, a."ipAddress"
            ORDER BY activity_count DESC
            LIMIT 20
        """
        
        try:
            with self.get_session() as session:
                result = session.execute(text(query), {"user_id": user_id, "start_time": start_time})
                return [
                    {
                        "userId": str(row[0]),
                        "username": row[1],
                        "role": row[2],
                        "ipAddress": row[3],
                        "activityCount": row[4]
                    }
                    for row in result.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to fetch user associations: {e}")
            return []

    def get_ip_activity(
        self,
        ip_address: str,
        hours: int = 1
    ) -> dict[str, Any]:
        """
        Get activity summary for a specific IP address.
        Useful for detecting coordinated attacks.
        """
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        with self.get_session() as session:
            query = """
                SELECT 
                    "userId",
                    action,
                    COUNT(*) as count
                FROM audit_logs
                WHERE "ipAddress" = :ip_address AND created_at >= :start_time
                GROUP BY "userId", action
                ORDER BY count DESC
            """
            result = session.execute(
                text(query),
                {"ip_address": ip_address, "start_time": start_time}
            )
            
            activities = [dict(row) for row in result.mappings().all()]
            unique_users = set(a["userId"] for a in activities if a["userId"])
            
            return {
                "ip_address": ip_address,
                "period_hours": hours,
                "unique_users": len(unique_users),
                "activities": activities
            }
    
    def get_system_health(self) -> dict[str, Any]:
        """
        Get system health metrics from the database.
        """
        with self.get_session() as session:
            # Get total users and breakdown by role
            role_counts = {}
            total_users = 0
            try:
                user_stats_query = """
                    SELECT role, COUNT(*) as count 
                    FROM users 
                    WHERE deleted_at IS NULL
                    GROUP BY role
                """
                user_stats = session.execute(text(user_stats_query)).mappings().all()
                role_counts = {row['role']: row['count'] for row in user_stats}
                total_users = sum(role_counts.values())
            except Exception:
                session.rollback()
            
            # Get recent error logs count
            error_count = 0
            try:
                # Fallback to audit_logs if system_logs doesn't exist or is empty
                error_query = """
                    SELECT COUNT(*) as count
                    FROM audit_logs
                    WHERE (action ILIKE '%error%' OR action ILIKE '%fail%')
                    AND created_at >= NOW() - INTERVAL '24 hours'
                """
                error_result = session.execute(text(error_query))
                error_count = error_result.scalar() or 0
            except Exception:
                session.rollback()
            
            return {
                "total_users": total_users,
                "role_breakdown": role_counts,
                "recent_errors_24h": error_count,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def execute_custom_query(
        self,
        query: str,
        params: dict = None
    ) -> list[dict]:
        """
        Execute a custom read-only SQL query.
        WARNING: Should only be used for SELECT statements.
        """
        if not query.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        
        with self.get_session() as session:
            result = session.execute(text(query), params or {})
            return [dict(row) for row in result.mappings().all()]

    def get_service_status(self) -> list[dict]:
        """Get current status of all monitored services with recent uptime info"""
        query = """
            SELECT 
                s.id, s.name, s.status, s.url,
                (SELECT status FROM uptime_checks WHERE "serviceId" = s.id ORDER BY "checkedAt" DESC LIMIT 1) as "lastCheckStatus",
                (SELECT "responseTime" FROM uptime_checks WHERE "serviceId" = s.id ORDER BY "checkedAt" DESC LIMIT 1) as "lastResponseTime"
            FROM monitored_services s
            WHERE s."isActive" = true
            ORDER BY s."order" ASC
        """
        try:
            with self.get_session() as session:
                result = session.execute(text(query))
                return [dict(row) for row in result.mappings().all()]
        except Exception as e:
            logger.error(f"Failed to fetch service status: {e}")
            return []

    def get_recent_incidents(self, hours: int = 24) -> list[dict]:
        """Fetch incidents created or updated within the specified time window"""
        start_time = datetime.utcnow() - timedelta(hours=hours)
        query = """
            SELECT 
                i.id, i.title, i.status, i.impact, i."startedAt", i."resolvedAt",
                s.name as "serviceName"
            FROM incidents i
            JOIN monitored_services s ON i."serviceId" = s.id
            WHERE i."createdAt" >= :start_time OR i."updatedAt" >= :start_time
            ORDER BY i."createdAt" DESC
        """
        try:
            with self.get_session() as session:
                result = session.execute(text(query), {"start_time": start_time})
                return [dict(row) for row in result.mappings().all()]
        except Exception as e:
            logger.error(f"Failed to fetch recent incidents: {e}")
            return []

    def get_daily_uptime_stats(self) -> list[dict]:
        """Calculate success rate for each service in the last 24 hours"""
        start_time = datetime.utcnow() - timedelta(hours=24)
        query = """
            SELECT 
                "serviceId",
                COUNT(*) FILTER (WHERE status = true) * 100.0 / COUNT(*) as "uptimeRate",
                COUNT(*) as "totalChecks"
            FROM uptime_checks
            WHERE "checkedAt" >= :start_time
            GROUP BY "serviceId"
        """
        try:
            with self.get_session() as session:
                result = session.execute(text(query), {"start_time": start_time})
                return [dict(row) for row in result.mappings().all()]
        except Exception as e:
            logger.error(f"Failed to fetch uptime stats: {e}")
            return []

    def get_schema_info(self) -> Dict[str, List[str]]:
        """
        Get all table names and their columns from the public schema.
        Used by the Neural Query Planner for dynamic decomposition.
        """
        query = """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """
        try:
            with self.get_session() as session:
                result = session.execute(text(query))
                schema = {}
                for row in result.mappings().all():
                    table = row['table_name']
                    column = row['column_name']
                    if table not in schema:
                        schema[table] = []
                    schema[table].append(column)
                return schema
        except Exception as e:
            logger.error(f"Failed to fetch schema info: {e}")
            return {}

    pass
