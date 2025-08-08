#!/usr/bin/env python3
"""
Simple test server to diagnose connection issues
"""
import http.server
import socketserver
import socket

def test_simple_server():
    PORT = 8090
    
    try:
        with socketserver.TCPServer(("", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
            print(f"SUCCESS: Simple server started successfully on port {PORT}")
            print(f"URL: Try accessing: http://127.0.0.1:{PORT}")
            print(f"URL: Or try: http://localhost:{PORT}")
            print("NOTE: This will serve files from the current directory")
            print("STOP: Press Ctrl+C to stop")
            
            # Test if we can bind to the port
            httpd.serve_forever()
            
    except OSError as e:
        print(f"ERROR: Error starting server: {e}")
        if "Address already in use" in str(e):
            print("CAUSE: Port is already in use by another process")
        elif "Permission denied" in str(e):
            print("CAUSE: Permission denied - may need admin rights or firewall exception")
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")

if __name__ == "__main__":
    print("TESTING: Testing simple HTTP server...")
    test_simple_server()