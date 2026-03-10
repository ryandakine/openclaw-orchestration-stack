#!/usr/bin/env node
/**
 * Project Dashboard Server
 * Serves the dashboard HTML and provides API endpoints for task data
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3456;
const TASKS_FILE = path.join(__dirname, '.taskmaster', 'tasks', 'tasks.json');

const MIME_TYPES = {
    '.html': 'text/html',
    '.js': 'text/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon'
};

function serveFile(res, filePath, contentType) {
    fs.readFile(filePath, (err, content) => {
        if (err) {
            res.writeHead(404);
            res.end('File not found');
            return;
        }
        res.writeHead(200, { 'Content-Type': contentType });
        res.end(content);
    });
}

const server = http.createServer((req, res) => {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    const url = req.url === '/' ? '/dashboard.html' : req.url;
    const parsedUrl = new URL(url, `http://localhost:${PORT}`);
    const pathname = parsedUrl.pathname;

    // API endpoint for tasks
    if (pathname === '/api/tasks') {
        fs.readFile(TASKS_FILE, 'utf8', (err, data) => {
            if (err) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Failed to load tasks', message: err.message }));
                return;
            }
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(data);
        });
        return;
    }

    // API endpoint for summary stats
    if (pathname === '/api/stats') {
        fs.readFile(TASKS_FILE, 'utf8', (err, data) => {
            if (err) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Failed to load stats', message: err.message }));
                return;
            }
            
            try {
                const tasksData = JSON.parse(data);
                const tasks = tasksData.master?.tasks || [];
                const stats = {
                    total: tasks.length,
                    done: tasks.filter(t => t.status === 'done').length,
                    inProgress: tasks.filter(t => t.status === 'in-progress').length,
                    pending: tasks.filter(t => t.status === 'pending').length,
                    percentComplete: tasks.length > 0 
                        ? Math.round((tasks.filter(t => t.status === 'done').length / tasks.length) * 100)
                        : 0,
                    lastUpdated: new Date().toISOString()
                };
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(stats, null, 2));
            } catch (e) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Failed to parse tasks', message: e.message }));
            }
        });
        return;
    }

    // Serve static files
    const filePath = path.join(__dirname, pathname);
    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    // Security: prevent directory traversal
    if (!filePath.startsWith(__dirname)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }

    fs.access(filePath, fs.constants.F_OK, (err) => {
        if (err) {
            res.writeHead(404);
            res.end('Not found');
            return;
        }
        serveFile(res, filePath, contentType);
    });
});

server.listen(PORT, () => {
    console.log(`
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   📊 Project Dashboard Server                                ║
║                                                              ║
║   Dashboard: http://localhost:${PORT}/                        ║
║   API Tasks: http://localhost:${PORT}/api/tasks               ║
║   API Stats: http://localhost:${PORT}/api/stats               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
`);
});

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log('\n👋 Shutting down server...');
    server.close(() => {
        process.exit(0);
    });
});
