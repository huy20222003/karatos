from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head>
    <title>Karatos WebMCP Lab</title>
</head>
<body>
    <h1>Karatos WebMCP Lab</h1>
    <p>This page is used to verify the WebMCP Bridge tool.</p>
    
    <!-- Declarative Tool Example -->
    <div style="border: 1px solid #ccc; padding: 10px; margin: 10px;">
        <h3>Declarative Tool: Product Search</h3>
        <form toolname="product_search" tooldescription="Search products in the lab harbor" toolautosubmit="true">
            <input type="text" name="query" placeholder="Product name..." required>
            <button type="submit">Search</button>
        </form>
    </div>

    <!-- Imperative Tool Example -->
    <div style="border: 1px solid #ccc; padding: 10px; margin: 10px;">
        <h3>Imperative Tool: Shipping Calc</h3>
        <p id="calc-result">Result will appear here</p>
    </div>

    <script>
        // Mocking WebMCP API for testing purposes if browser doesn't have it yet
        // In a real environment like Chrome Canary, this should already exist
        if (!window.navigator.modelContext) {
            console.log("Mocking WebMCP navigator.modelContext for local testing...");
            window.navigator.modelContext = {
                _tools: [
                    {
                        name: "calculate_shipping",
                        description: "Calculate shipping cost to a specific zipcode",
                        inputSchema: {
                            type: "object",
                            properties: {
                                zipcode: { type: "string" }
                            }
                        }
                    }
                ],
                listTools: function() { return this._tools; },
                callTool: async function(name, args) {
                    if (name === "calculate_shipping") {
                        document.getElementById('calc-result').innerText = "Shipping cost to " + args.zipcode + " is 50.000 VND";
                        return { cost: 50000, currency: "VND", destination: args.zipcode };
                    }
                    throw new Error("Tool not found");
                }
            };
        }
    </script>
</body>
</html>
"""

class WebMCPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode('utf-8'))

def run_server(port=8081):
    server = HTTPServer(('127.0.0.1', port), WebMCPHandler)
    print(f"Test server running at http://127.0.0.1:{port}")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
