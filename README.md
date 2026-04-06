# Claude Cowork Session Manager

A lightweight desktop tool for viewing and deleting your Claude Cowork chat sessions — no installation required beyond Python 3.

## What it does

Runs a local web server and opens your browser to a clean dark-themed UI that lists all your Cowork sessions. You can select one or many sessions and permanently delete them, with a confirmation step before anything is removed.

![UI: dark table listing Cowork sessions with checkboxes and a Delete Selected button]

## Why it exists

Claude Cowork stores session files in `%APPDATA%\Claude\local-agent-mode-sessions` but provides no built-in way to delete them. Deleting a session requires removing both a `.json` metadata file **and** a matching folder — this tool handles that safely.

> **Note:** An earlier version used tkinter, which has a known Windows bug where checkbox state disappears on mouse-up. This version uses a browser-based UI instead, so checkboxes work correctly.

## Requirements

- Windows (tested on Windows 10/11)
- Python 3.8 or newer (standard library only — no pip installs needed)
- Any modern browser

## How to run

```powershell
"C:\Users\<YourName>\AppData\Local\Programs\Python\Python3xx\python.exe" "C:\Software\cowork_session_manager.py"
```

Your browser will open automatically to `http://localhost:8765`. Press `Ctrl+C` in the terminal to stop the server when you're done.

## ⚠ Important

**Close the Claude desktop app before deleting sessions.** Deleting sessions while Claude is running can cause data corruption.

## Features

- Lists all sessions sorted newest-first
- Shows title, last active date, created date, active/archived status
- Select All / Deselect All
- Toggle to show or hide archived sessions
- Confirmation modal listing affected sessions before any deletion
- Permanently deletes both the `.json` file and session folder for each selected session
- Auto-refreshes the list after deletion

## How sessions are stored

```
%APPDATA%\Claude\local-agent-mode-sessions\
  <outer-guid>\
    <inner-guid>\
      local_<uuid>.json       ← metadata (title, dates, etc.)
      local_<uuid>\           ← session data folder
```

Both items are deleted when you remove a session.

## Credits

Built with Claude Cowork. Inspired by:  
https://ozer.gt/log/2026/03/20/how-to-delete-a-claude-cowork-session/

## License

MIT
