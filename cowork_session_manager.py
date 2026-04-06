#!/usr/bin/env python3
"""
Cowork Session Manager
A simple web-based tool for listing and deleting Claude Cowork sessions.
Runs a local HTTP server on port 8765 with a browser UI.
"""

import json
import os
import shutil
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys

# Catppuccin Mocha colors
COLORS = {
    "background": "#1e1e2e",
    "surface": "#2a2a3d",
    "border": "#313244",
    "text": "#cdd6f4",
    "dim_text": "#6c7086",
    "accent": "#89b4fa",
    "danger": "#f38ba8",
    "success": "#a6e3a1",
    "warn_bg": "#45475a",
}

# Session storage path
SESSIONS_ROOT = Path(os.environ.get("APPDATA", "")) / "Claude" / "local-agent-mode-sessions"

# Global state
sessions_cache = []


def discover_sessions():
    """Walk SESSIONS_ROOT two levels deep, find all local_*.json files, parse and sort."""
    global sessions_cache
    sessions = []
    
    if not SESSIONS_ROOT.exists():
        sessions_cache = []
        return
    
    try:
        for outer_guid_dir in SESSIONS_ROOT.iterdir():
            if not outer_guid_dir.is_dir():
                continue
            
            for inner_guid_dir in outer_guid_dir.iterdir():
                if not inner_guid_dir.is_dir():
                    continue
                
                # Look for local_*.json files
                for json_file in inner_guid_dir.glob("local_*.json"):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        # Extract session ID from filename
                        session_id = json_file.stem  # e.g., "local_abc123"
                        
                        # Parse timestamps
                        created_at = data.get("createdAt", 0)
                        last_activity = data.get("lastActivityAt", created_at)
                        
                        if isinstance(created_at, str):
                            try:
                                created_at = int(
                                    datetime.fromisoformat(
                                        created_at.replace("Z", "+00:00")
                                    ).timestamp() * 1000
                                )
                            except:
                                created_at = 0
                        
                        if isinstance(last_activity, str):
                            try:
                                last_activity = int(
                                    datetime.fromisoformat(
                                        last_activity.replace("Z", "+00:00")
                                    ).timestamp() * 1000
                                )
                            except:
                                last_activity = 0
                        
                        # Build session dict
                        session = {
                            "id": session_id,
                            "title": data.get("title", data.get("initialMessage", "Untitled")),
                            "createdAt": created_at,
                            "lastActivityAt": last_activity,
                            "isArchived": data.get("isArchived", False),
                            "_json_path": str(json_file),
                            "_folder_path": str(inner_guid_dir / session_id),
                        }
                        sessions.append(session)
                    except Exception as e:
                        print(f"Error reading {json_file}: {e}")
                        continue
    
    except Exception as e:
        print(f"Error discovering sessions: {e}")
    
    # Sort by lastActivityAt descending (newest first)
    sessions.sort(key=lambda s: s["lastActivityAt"], reverse=True)
    sessions_cache = sessions


def format_timestamp(ms_epoch):
    """Convert millisecond epoch to human-readable format."""
    if not ms_epoch:
        return "Unknown"
    try:
        dt = datetime.fromtimestamp(ms_epoch / 1000)
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return "Unknown"


def delete_session(session_id):
    """Delete both the .json file and folder for a session."""
    session = next((s for s in sessions_cache if s["id"] == session_id), None)
    if not session:
        return {"error": "Session not found"}
    
    try:
        json_path = Path(session["_json_path"])
        folder_path = Path(session["_folder_path"])
        
        # Delete JSON file
        if json_path.exists():
            json_path.unlink()
        
        # Delete folder
        if folder_path.exists():
            shutil.rmtree(folder_path)
        
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the session manager."""
    
    def log_message(self, format, *args):
        """Suppress logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == "/":
            self.serve_html()
        elif path == "/api/sessions":
            self.serve_sessions_json()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == "/api/delete":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            
            try:
                data = json.loads(body)
                ids = data.get("ids", [])
                
                results = {}
                for session_id in ids:
                    result = delete_session(session_id)
                    results[session_id] = result.get("status", "error")
                
                # Refresh cache after deletion
                discover_sessions()
                
                response = json.dumps(results)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-length", len(response))
                self.end_headers()
                self.wfile.write(response.encode("utf-8"))
            except Exception as e:
                error_response = json.dumps({"error": str(e)})
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-length", len(error_response))
                self.end_headers()
                self.wfile.write(error_response.encode("utf-8"))
        else:
            self.send_error(404)
    
    def serve_sessions_json(self):
        """Return JSON array of sessions (without internal paths)."""
        public_sessions = []
        for session in sessions_cache:
            public_sessions.append({
                "id": session["id"],
                "title": session["title"],
                "createdAt": session["createdAt"],
                "lastActivityAt": session["lastActivityAt"],
                "isArchived": session["isArchived"],
            })
        
        response = json.dumps(public_sessions)
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-length", len(response))
        self.end_headers()
        self.wfile.write(response.encode("utf-8"))
    
    def serve_html(self):
        """Serve the HTML page."""
        html = self.get_html()
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-length", len(html.encode("utf-8")))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
    
    def get_html(self):
        """Generate the complete HTML page."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cowork Session Manager</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: {COLORS['background']};
            color: {COLORS['text']};
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        
        header {{
            background-color: {COLORS['surface']};
            border-bottom: 1px solid {COLORS['border']};
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }}
        
        header h1 {{
            font-size: 1.75rem;
            margin-bottom: 0.25rem;
        }}
        
        .session-count {{
            color: {COLORS['dim_text']};
            font-size: 0.9rem;
        }}
        
        .warning-banner {{
            background-color: {COLORS['warn_bg']};
            color: {COLORS['text']};
            padding: 1rem 1.5rem;
            border-left: 4px solid {COLORS['danger']};
        }}
        
        .warning-banner strong {{
            color: {COLORS['danger']};
        }}
        
        .toolbar {{
            background-color: {COLORS['surface']};
            border-bottom: 1px solid {COLORS['border']};
            padding: 1rem 1.5rem;
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            align-items: center;
        }}
        
        .toolbar button {{
            background-color: {COLORS['accent']};
            color: {COLORS['background']};
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
            transition: background-color 0.2s;
        }}
        
        .toolbar button:hover {{
            background-color: #a3c4ff;
        }}
        
        .toolbar button:disabled {{
            background-color: {COLORS['dim_text']};
            opacity: 0.5;
            cursor: not-allowed;
        }}
        
        .toolbar button.danger {{
            background-color: {COLORS['danger']};
        }}
        
        .toolbar button.danger:hover {{
            background-color: #f4a5b9;
        }}
        
        .toolbar-spacer {{
            flex: 1;
        }}
        
        .toolbar-label {{
            color: {COLORS['dim_text']};
            font-size: 0.9rem;
        }}
        
        .checkbox-group {{
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }}
        
        .checkbox-group input[type="checkbox"] {{
            width: 1.2rem;
            height: 1.2rem;
            cursor: pointer;
        }}
        
        .checkbox-group label {{
            cursor: pointer;
            font-size: 0.9rem;
        }}
        
        .content {{
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
        }}
        
        .no-sessions {{
            text-align: center;
            padding: 3rem;
            color: {COLORS['dim_text']};
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: {COLORS['surface']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            overflow: hidden;
        }}
        
        th {{
            background-color: {COLORS['surface']};
            color: {COLORS['text']};
            padding: 1rem;
            text-align: left;
            font-weight: 600;
            border-bottom: 1px solid {COLORS['border']};
        }}
        
        td {{
            padding: 1rem;
            border-bottom: 1px solid {COLORS['border']};
        }}
        
        tr:nth-child(even) {{
            background-color: rgba(42, 42, 61, 0.5);
        }}
        
        tr:hover {{
            background-color: rgba(137, 180, 250, 0.1);
        }}
        
        tr.archived {{
            opacity: 0.7;
            background-color: rgba(108, 112, 134, 0.2);
        }}
        
        tr.archived:nth-child(even) {{
            background-color: rgba(108, 112, 134, 0.25);
        }}
        
        .checkbox-cell {{
            width: 2.5rem;
            text-align: center;
        }}
        
        .checkbox-cell input[type="checkbox"] {{
            width: 1.2rem;
            height: 1.2rem;
            cursor: pointer;
        }}
        
        .title-cell {{
            font-weight: 500;
            max-width: 300px;
            word-break: break-word;
        }}
        
        .session-id {{
            color: {COLORS['dim_text']};
            font-family: monospace;
            font-size: 0.8rem;
        }}
        
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .badge.active {{
            background-color: rgba(166, 227, 161, 0.2);
            color: {COLORS['success']};
        }}
        
        .badge.archived {{
            background-color: rgba(108, 112, 134, 0.3);
            color: {COLORS['dim_text']};
        }}
        
        footer {{
            background-color: {COLORS['surface']};
            border-top: 1px solid {COLORS['border']};
            padding: 1rem 1.5rem;
            text-align: center;
            color: {COLORS['dim_text']};
            font-size: 0.85rem;
        }}
        
        /* Modal */
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }}
        
        .modal.show {{
            display: flex;
        }}
        
        .modal-content {{
            background-color: {COLORS['surface']};
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
            padding: 2rem;
            max-width: 500px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
        }}
        
        .modal-content h2 {{
            margin-bottom: 1rem;
            color: {COLORS['text']};
        }}
        
        .modal-sessions-list {{
            background-color: {COLORS['background']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: 1rem;
            margin: 1rem 0;
            max-height: 200px;
            overflow-y: auto;
        }}
        
        .modal-sessions-list p {{
            margin: 0.5rem 0;
            color: {COLORS['dim_text']};
        }}
        
        .modal-sessions-list .title {{
            color: {COLORS['text']};
            font-weight: 500;
        }}
        
        .modal-buttons {{
            margin-top: 1.5rem;
            display: flex;
            gap: 1rem;
            justify-content: flex-end;
        }}
        
        .modal-buttons button {{
            padding: 0.6rem 1.5rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
        }}
        
        .modal-buttons .confirm {{
            background-color: {COLORS['danger']};
            color: {COLORS['background']};
        }}
        
        .modal-buttons .confirm:hover {{
            background-color: #f4a5b9;
        }}
        
        .modal-buttons .cancel {{
            background-color: {COLORS['dim_text']};
            color: {COLORS['background']};
        }}
        
        .modal-buttons .cancel:hover {{
            background-color: #7f8397;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Cowork Session Manager</h1>
        <div class="session-count">
            <span id="total-count">0</span> session(s) found
        </div>
    </header>
    
    <div class="warning-banner">
        <strong>Warning:</strong> Close the Claude desktop app before deleting sessions.
    </div>
    
    <div class="toolbar">
        <button onclick="refreshSessions()">Refresh</button>
        <button onclick="selectAll()">Select All</button>
        <button onclick="deselectAll()">Deselect All</button>
        
        <div class="checkbox-group">
            <input type="checkbox" id="show-archived" onchange="filterArchived()">
            <label for="show-archived">Show archived</label>
        </div>
        
        <div class="toolbar-spacer"></div>
        
        <div class="toolbar-label" id="selected-label">0 selected</div>
        <button class="danger" id="delete-btn" onclick="confirmDelete()" disabled>
            Delete Selected
        </button>
    </div>
    
    <div class="content">
        <div id="no-sessions" class="no-sessions" style="display: none;">
            No sessions found. Your Cowork history is clean!
        </div>
        
        <table id="sessions-table" style="display: none;">
            <thead>
                <tr>
                    <th class="checkbox-cell">
                        <input type="checkbox" id="header-checkbox" onchange="toggleAll()">
                    </th>
                    <th>Title</th>
                    <th>Last Active</th>
                    <th>Created</th>
                    <th>Status</th>
                    <th>Session ID</th>
                </tr>
            </thead>
            <tbody id="sessions-tbody"></tbody>
        </table>
    </div>
    
    <footer>
        Ready to delete sessions. All data will be permanently removed.
    </footer>
    
    <!-- Confirmation Modal -->
    <div id="confirm-modal" class="modal">
        <div class="modal-content">
            <h2>Confirm Deletion</h2>
            <p>You are about to permanently delete the following session(s):</p>
            <div class="modal-sessions-list" id="modal-sessions-list"></div>
            <div class="modal-buttons">
                <button class="cancel" onclick="cancelDelete()">Cancel</button>
                <button class="confirm" onclick="executeDelete()">Delete Permanently</button>
            </div>
        </div>
    </div>
    
    <script>
        let allSessions = [];
        let selectedIds = new Set();
        let showArchivedSessions = false;
        let sessionsToDelete = [];
        
        // Initialize
        window.addEventListener('DOMContentLoaded', function() {{
            refreshSessions();
        }});
        
        function refreshSessions() {{
            fetch('/api/sessions')
                .then(r => r.json())
                .then(data => {{
                    allSessions = data;
                    selectedIds.clear();
                    renderTable();
                    updateDeleteButton();
                }})
                .catch(e => console.error('Error fetching sessions:', e));
        }}
        
        function renderTable() {{
            const tbody = document.getElementById('sessions-tbody');
            tbody.innerHTML = '';
            
            let filteredSessions = allSessions;
            if (!showArchivedSessions) {{
                filteredSessions = allSessions.filter(s => !s.isArchived);
            }}
            
            if (filteredSessions.length === 0) {{
                document.getElementById('no-sessions').style.display = 'block';
                document.getElementById('sessions-table').style.display = 'none';
                document.getElementById('total-count').textContent = '0';
                return;
            }}
            
            document.getElementById('no-sessions').style.display = 'none';
            document.getElementById('sessions-table').style.display = 'table';
            document.getElementById('total-count').textContent = String(allSessions.length);
            
            filteredSessions.forEach(session => {{
                const row = document.createElement('tr');
                row.className = session.isArchived ? 'archived' : '';
                row.dataset.sessionId = session.id;
                
                const createdDate = new Date(session.createdAt).toLocaleString();
                const lastActivityDate = new Date(session.lastActivityAt).toLocaleString();
                const statusBadge = session.isArchived 
                    ? '<span class="badge archived">Archived</span>'
                    : '<span class="badge active">Active</span>';
                
                row.innerHTML = `
                    <td class="checkbox-cell">
                        <input type="checkbox" data-id="${{session.id}}" 
                               onchange="toggleSession(this)">
                    </td>
                    <td class="title-cell">${{escapeHtml(session.title)}}</td>
                    <td>${{lastActivityDate}}</td>
                    <td>${{createdDate}}</td>
                    <td>${{statusBadge}}</td>
                    <td><span class="session-id">${{session.id}}</span></td>
                `;
                tbody.appendChild(row);
            }});
            
            updateHeaderCheckbox();
        }}
        
        function toggleSession(checkbox) {{
            if (checkbox.checked) {{
                selectedIds.add(checkbox.dataset.id);
            }} else {{
                selectedIds.delete(checkbox.dataset.id);
            }}
            updateDeleteButton();
            updateHeaderCheckbox();
        }}
        
        function toggleAll() {{
            const headerCheckbox = document.getElementById('header-checkbox');
            const checkboxes = document.querySelectorAll('[data-id]');
            
            checkboxes.forEach(cb => {{
                cb.checked = headerCheckbox.checked;
                if (headerCheckbox.checked) {{
                    selectedIds.add(cb.dataset.id);
                }} else {{
                    selectedIds.delete(cb.dataset.id);
                }}
            }});
            
            updateDeleteButton();
        }}
        
        function selectAll() {{
            const checkboxes = document.querySelectorAll('[data-id]');
            checkboxes.forEach(cb => {{
                cb.checked = true;
                selectedIds.add(cb.dataset.id);
            }});
            document.getElementById('header-checkbox').checked = true;
            document.getElementById('header-checkbox').indeterminate = false;
            updateDeleteButton();
        }}
        
        function deselectAll() {{
            const checkboxes = document.querySelectorAll('[data-id]');
            checkboxes.forEach(cb => {{
                cb.checked = false;
                selectedIds.delete(cb.dataset.id);
            }});
            document.getElementById('header-checkbox').checked = false;
            document.getElementById('header-checkbox').indeterminate = false;
            updateDeleteButton();
        }}
        
        function filterArchived() {{
            showArchivedSessions = document.getElementById('show-archived').checked;
            selectedIds.clear();
            renderTable();
            updateDeleteButton();
        }}
        
        function updateHeaderCheckbox() {{
            const checkboxes = document.querySelectorAll('[data-id]');
            const checked = Array.from(checkboxes).filter(cb => cb.checked).length;
            const headerCheckbox = document.getElementById('header-checkbox');
            
            if (checked === 0) {{
                headerCheckbox.checked = false;
                headerCheckbox.indeterminate = false;
            }} else if (checked === checkboxes.length) {{
                headerCheckbox.checked = true;
                headerCheckbox.indeterminate = false;
            }} else {{
                headerCheckbox.indeterminate = true;
            }}
        }}
        
        function updateDeleteButton() {{
            const deleteBtn = document.getElementById('delete-btn');
            const label = document.getElementById('selected-label');
            const count = selectedIds.size;
            
            label.textContent = count + ' selected';
            deleteBtn.disabled = count === 0;
        }}
        
        function confirmDelete() {{
            if (selectedIds.size === 0) return;
            
            sessionsToDelete = Array.from(selectedIds);
            const modal = document.getElementById('confirm-modal');
            const listDiv = document.getElementById('modal-sessions-list');
            listDiv.innerHTML = '';
            
            let count = 0;
            sessionsToDelete.forEach(id => {{
                const session = allSessions.find(s => s.id === id);
                if (session) {{
                    const p = document.createElement('p');
                    p.innerHTML = '<span class="title">' + escapeHtml(session.title) + '</span>';
                    listDiv.appendChild(p);
                    count++;
                }}
            }});
            
            if (count > 6) {{
                const p = document.createElement('p');
                p.textContent = '… and ' + (count - 6) + ' more';
                listDiv.appendChild(p);
            }}
            
            modal.classList.add('show');
        }}
        
        function cancelDelete() {{
            document.getElementById('confirm-modal').classList.remove('show');
        }}
        
        function executeDelete() {{
            const ids = sessionsToDelete;
            fetch('/api/delete', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{ids: ids}})
            }})
            .then(r => r.json())
            .then(data => {{
                document.getElementById('confirm-modal').classList.remove('show');
                refreshSessions();
            }})
            .catch(e => {{
                alert('Error deleting sessions: ' + e.message);
                document.getElementById('confirm-modal').classList.remove('show');
            }});
        }}
        
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
    </script>
</body>
</html>
"""


def main():
    """Main entry point."""
    print("Starting Cowork Session Manager...")
    
    # Discover sessions on startup
    discover_sessions()
    print(f"Found {len(sessions_cache)} session(s)")
    
    # Start HTTP server
    server_address = ("127.0.0.1", 8765)
    httpd = HTTPServer(server_address, RequestHandler)
    
    url = "http://127.0.0.1:8765"
    print(f"\nServer running at {url}")
    print("Press Ctrl+C to stop.")
    
    # Open browser after a short delay
    def open_browser():
        webbrowser.open(url)
    
    timer = threading.Timer(0.6, open_browser)
    timer.daemon = True
    timer.start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        httpd.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
