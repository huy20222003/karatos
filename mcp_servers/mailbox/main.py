from src.api.mcp_server import mcp
from src.core.utils import kill_process_on_port
from src.config import settings
import uvicorn

if __name__ == "__main__":
    # Ensure port is free before starting
    kill_process_on_port(settings.PORT)
    
    print(f"\n--- NivaSound Professional {settings.SERVER_NAME} Service (SSE) ---")
    print(f"Transport: HTTP/SSE on {settings.HOST}:{settings.PORT}")
    print("Status: Powering A2A communication.")
    print("----------------------------------------------------\n")
    
    # FastMCP doesn't support host/port in run(), so we use uvicorn directly
    uvicorn.run(mcp.sse_app, host=settings.HOST, port=settings.PORT, log_level="info")
