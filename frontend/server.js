const http = require('http');
const httpProxy = require('http-proxy');
const fs = require('fs');
const path = require('path');

const PORT = 3001;
const API_TARGET = 'http://localhost:5000';

// Create proxy
const proxy = httpProxy.createProxyServer({});

// Create server
const server = http.createServer((req, res) => {
  // Proxy API requests
  if (req.url.startsWith('/api')) {
    proxy.web(req, res, { target: API_TARGET });
    return;
  }

  // Serve static files
  let filePath = path.join(__dirname, 'dist', req.url === '/' ? 'index.html' : req.url);
  
  // Fallback to index.html for React Router
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(__dirname, 'dist', 'index.html');
  }

  const ext = path.extname(filePath);
  const contentType = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpg',
    '.svg': 'image/svg+xml'
  }[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404);
      res.end('Not found');
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content);
    }
  });
});

server.listen(PORT, () => {
  console.log(`\n✓ Server running at http://localhost:${PORT}/`);
  console.log(`✓ Proxying /api to ${API_TARGET}\n`);
});

server.on('error', (err) => {
  console.error('Server error:', err);
  process.exit(1);
});

proxy.on('error', (err, req, res) => {
  console.error('Proxy error:', err.message);
  res.writeHead(500, { 'Content-Type': 'text/plain' });
  res.end('Proxy error');
});

process.on('uncaughtException', (err) => {
  console.error('Uncaught exception:', err);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled rejection at:', promise, 'reason:', reason);
});

// Keep alive
setInterval(() => {}, 1000);

