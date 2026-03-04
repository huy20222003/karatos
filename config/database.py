import adbc_driver_postgresql.dbapi as adbc_dbapi
from sqlalchemy import create_engine
from config.settings import settings
from utils.logger import get_logger

logger = get_logger()

class DBConnectionFactory:
    """
    Singleton factory for database connections.
    Manages both:
    1. ADBC Connection (High Performance, Arrow/Polars)
    2. SQLAlchemy Engine (ORM, Transactional, pgvector)
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBConnectionFactory, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._adbc_conn = None
        self._sqlalchemy_engine = None
        self._initialized = True
        logger.info("[DB] DBConnectionFactory initialized in Config.")

    def get_adbc_connection(self):
        """Get or create the shared ADBC connection."""
        if self._adbc_conn is None:
            try:
                # ADBC connection for high-performance reads
                # Ensure we use the latest URL from settings
                db_url = settings.database_url
                if not db_url:
                    logger.error("[DB] database_url is empty in settings!")
                    raise ValueError("database_url is empty")
                
                self._adbc_conn = adbc_dbapi.connect(db_url)
                logger.info("[DB] ADBC Connection established.")
            except Exception as e:
                logger.error(f"[DB] Failed to connect ADBC: {e}")
                raise
        return self._adbc_conn

    def get_sqlalchemy_engine(self):
        """Get or create the shared SQLAlchemy engine."""
        if self._sqlalchemy_engine is None:
            try:
                db_url = settings.database_url
                if not db_url:
                     logger.error("[DB] database_url is empty in settings!")
                     raise ValueError("database_url is empty")
                     
                # Remove pgbouncer params for SQLAlchemy compatibility
                clean_url = self._clean_url_for_sqlalchemy(db_url)
                self._sqlalchemy_engine = create_engine(
                    clean_url,
                    pool_size=10, 
                    max_overflow=20,
                    pool_timeout=30,
                    pool_recycle=1800
                )
                logger.info("[DB] SQLAlchemy Engine established.")
            except Exception as e:
                logger.error(f"[DB] Failed to create SQLAlchemy engine: {e}")
                raise
        return self._sqlalchemy_engine

    def _clean_url_for_sqlalchemy(self, url: str) -> str:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        # Remove params that break psycopg2
        for param in ['pgbouncer', 'statement_cache_capacity', 'connection_limit']:
             query_params.pop(param, None)
        
        new_query = urlencode({k: v[0] for k, v in query_params.items()}, doseq=False)
        return urlunparse(parsed._replace(query=new_query))

# Global accessor
def get_db_factory():
    return DBConnectionFactory()
