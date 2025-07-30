#!/usr/bin/env python3
"""
Simple HTTP test server to diagnose connectivity issues
"""
import http.server
import socketserver
import webbrowser
from datetime import datetime

PORT = 8080

class TestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        print(f"🔗 Request received at {datetime.now()}: {self.path}")
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>🎉 Server Test Success!</title>
            <style>
                body {{ font-family: Arial; text-align: center; padding: 50px; background: #f0f8ff; }}
                .success {{ color: #28a745; font-size: 24px; }}
                .info {{ color: #17a2b8; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <h1 class="success">✅ SUCCESS!</h1>
            <p class="info">Your browser CAN connect to the server!</p>
            <p>Time: {datetime.now()}</p>
            <p>Path: {self.path}</p>
            <hr>
            <p><strong>This means:</strong></p>
            <ul style="text-align: left; max-width: 400px; margin: 0 auto;">
                <li>✅ Network connectivity works</li>
                <li>✅ Port 8080 is accessible</li>
                <li>✅ No firewall blocking</li>
                <li>⚠️ Issue is with Django configuration</li>
            </ul>
            <hr>
            <p><a href="http://127.0.0.1:8080/test">Test another path</a></p>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

if __name__ == "__main__":
    print("🧪 Starting Simple Test Server...")
    print(f"📡 Server: http://127.0.0.1:{PORT}")
    print("🔗 Opening browser automatically...")
    print("🛑 Press Ctrl+C to stop")
    print()
    
    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), TestHandler) as httpd:
            print(f"✅ Server listening on http://127.0.0.1:{PORT}")
            
            # Auto-open browser
            try:
                webbrowser.open(f'http://127.0.0.1:{PORT}')
            except:
                print("⚠️ Could not auto-open browser")
            
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except Exception as e:
        print(f"❌ Server error: {e}")