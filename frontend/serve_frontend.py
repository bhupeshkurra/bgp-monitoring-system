"""
Simple HTTP server with proxy to serve frontend and proxy API requests to backend
"""
import http.server
import socketserver
import urllib.request
import urllib.error
from pathlib import Path

PORT = 3000
API_BACKEND = "http://localhost:5000"

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Proxy API requests to backend
        if self.path.startswith('/api'):
            try:
                url = f"{API_BACKEND}{self.path}"
                with urllib.request.urlopen(url) as response:
                    self.send_response(response.status)
                    for header, value in response.headers.items():
                        if header.lower() not in ['server', 'date']:
                            self.send_header(header, value)
                    self.end_headers()
                    self.wfile.write(response.read())
            except urllib.error.HTTPError as e:
                self.send_error(e.code, str(e))
            except Exception as e:
                self.send_error(500, str(e))
            return
        
        # Serve static files from dist
        return super().do_GET()
    
    def translate_path(self, path):
        # Serve from dist folder
        path = super().translate_path(path)
        relpath = Path(path).relative_to(Path.cwd())
        
        # Prepend dist/ to the path
        dist_path = Path('dist') / relpath
        
        # If path doesn't exist or is directory, serve index.html (for React Router)
        if not dist_path.exists() or dist_path.is_dir():
            dist_path = Path('dist') / 'index.html'
        
        return str(dist_path)

if __name__ == '__main__':
    Handler = ProxyHTTPRequestHandler
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"\n✓ Frontend server running at http://localhost:{PORT}/")
        print(f"✓ Proxying /api requests to {API_BACKEND}")
        print(f"✓ Serving files from: dist/\n")
        print("Press Ctrl+C to stop\n")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nShutting down server...")
            httpd.shutdown()
