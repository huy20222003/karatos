import asyncio
import os
import sys
import subprocess
import time
import json

# Add parent directory to sys.path to import tools
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.webmcp_bridge import WebMCPBridge
from utils.logger import get_logger

logger = get_logger()

async def run_test():
    # 1. Start the test server in a background process
    logger.info("Starting WebMCP test server...")
    server_process = subprocess.Popen([sys.executable, "tests/webmcp_test_server.py"])
    time.sleep(2) # Wait for server to start
    
    try:
        bridge = WebMCPBridge()
        test_url = "http://127.0.0.1:8081"
        
        # 2. Navigate to test page
        logger.info(f"Navigating to {test_url}...")
        await bridge.navigate(test_url)
        await asyncio.sleep(5) # Give it extra time for JS to run
        
        # 3. List tools
        logger.info("Discovering WebMCP tools...")
        tools_res = await bridge.list_web_tools()
        logger.info(f"Scan Result: {json.dumps(tools_res, indent=2)}")
        
        if tools_res.get("status") == "success" and tools_res.get("count", 0) >= 1:
            logger.info("✅ Discovery successful!")
        else:
            logger.error(f"❌ Discovery failed. Tools found: {tools_res.get('count')}")
            # Try once more with a different strategy or direct JS probe
            logger.info("Probing window.navigator directly...")
            probe = await bridge.mcp.execute("chrome-devtools:evaluate_script", {"function": "() => JSON.stringify(Object.keys(window.navigator))"})
            logger.info(f"Navigator Keys: {probe}")
            
            logger.info("Dumping Page Source...")
            source = await bridge.mcp.execute("chrome-devtools:evaluate_script", {"function": "() => document.documentElement.outerHTML"})
            logger.info(f"Source: {source}")
            return

        # 4. Call Imperative Tool
        logger.info("Testing Imperative Tool: calculate_shipping...")
        call_res = await bridge.call_web_tool("calculate_shipping", {"zipcode": "70000"})
        logger.info(f"Call result: {call_res}")
        
        if call_res and call_res.get("cost") == 50000:
            logger.info("✅ Imperative tool execution successful!")
        else:
            logger.error("❌ Imperative tool execution failed.")

        # 5. Call Declarative Tool (Form)
        logger.info("Testing Declarative Tool: product_search...")
        form_res = await bridge.call_web_tool("product_search", {"query": "Niva Alpha"})
        logger.info(f"Form submission result: {form_res}")
        
        if form_res and form_res.get("status") == "submitted":
            logger.info("✅ Declarative tool submission successful!")
        else:
            logger.error("❌ Declarative tool submission failed.")

    finally:
        logger.info("Stopping test server...")
        server_process.terminate()

if __name__ == "__main__":
    asyncio.run(run_test())
