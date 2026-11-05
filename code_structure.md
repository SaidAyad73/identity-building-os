# Codebase Structure & Concerns

This document details the project file tree, responsibilities, and core concerns for Identity Building OS.

---

## File Tree

```
atmoic/
|-- assets/
|   |-- dashboard-preview.png
|   |-- habit-laws-preview.png
|   \-- weekly-review-preview.png
|-- data/
|   |-- identity_os.db
|   |-- service.err.log
|   \-- service.out.log
|-- guidance/
|   |-- anti-identities-and-balance.md
|   |-- four-laws.md
|   \-- identities-playbook.md
|-- static/
|   |-- app.js
|   |-- index.html
|   \-- styles.css
|-- tests/
|   \-- test_app.py
|-- .env
|-- .env.example
|-- .gitignore
|-- app.py
|-- code_structure.md
|-- LICENSE
|-- main.js
|-- package.json
|-- package-lock.json
|-- preload.js
|-- README.md
|-- service.bat
|-- service.ps1
\-- TODO.md
```

---

## File Responsibilities and Core Concerns

### 1. Application Core & Backend
- **[app.py](app.py)**
  - **Responsibilities:** Central backend web server, database access layer, business logic engine, and CLI utility.
  - **Core Concerns:**
    - SQLite schema management, migrations, and foreign key integrity.
    - Configuration management with strict environment loading via `.env` (no hardcoded credentials/ports/paths).
    - Identity, Habit, Action, and Weekly Review CRUD operations.
    - Fractional identity distribution computation for multi-identity habits (preventing double counting).
    - Weekly automated summary synthesis and review generation.
    - JSON Export and Import logic with merge/replace strategies.
    - REST API routing (`/api/state`, `/api/actions`, `/api/identities`, `/api/habits`, `/api/reviews`, `/api/export`, `/api/import`, etc.).
    - Static file serving and CLI arguments dispatch.

### 2. Desktop Environment (Electron)
- **[main.js](main.js)**
  - **Responsibilities:** Electron main process coordinator.
  - **Core Concerns:**
    - Spawns and supervises the local Python backend process.
    - Health-checks the local HTTP server prior to loading the main window.
    - Application lifecycle management (graceful process termination on quit).
    - Application menu definitions (keyboard shortcuts, navigation, data export/import triggers).
    - IPC handlers (`dialog-export-json`, `dialog-import-json`) interacting with native file dialogs.
- **[preload.js](preload.js)**
  - **Responsibilities:** Context bridge between Electron main process and renderer process.
  - **Core Concerns:**
    - Securely exposes `electronAPI` (`isElectron`, `exportJson`, `importJson`) to `window`.
    - Enforces context isolation and sandbox restrictions.

### 3. Frontend Web Interface
- **[static/index.html](static/index.html)**
  - **Responsibilities:** Single-page application UI structure and markup.
  - **Core Concerns:**
    - Topbar branding, view navigation tabs, theme toggle, 2-minute mode switch.
    - Pinned weekly focus banner.
    - Dashboard view (quick-capture form, identity distribution chart, calendar, identity cards, guardrails, activity feed).
    - Weekly Review view (automated summary generation and reflective review forms).
    - Atomic Habits Playbook view (Markdown viewer and in-app editor).
    - Extend & Configure management view (identity/habit creation, reordering, import/export controls).
    - Modals for creating/editing identities, habits, and actions.
- **[static/app.js](static/app.js)**
  - **Responsibilities:** Client-side application state, UI rendering, event handling, and API integration.
  - **Core Concerns:**
    - State synchronization with backend via REST API.
    - Dynamic SVG rendering: interactive identity distribution donut chart and activity calendar.
    - Four Laws habit configuration and hover metadata popovers.
    - 2-Minute Mode UI transformations.
    - Native file import/export triggering via `electronAPI` with web file fallback.
- **[static/styles.css](static/styles.css)**
  - **Responsibilities:** Application styling, responsive layout, and theme tokens.
  - **Core Concerns:**
    - CSS custom properties for light and dark color schemes.
    - Modern typographic scaling, grid layouts, card designs, and modal styles.
    - Professional, accessible visual hierarchy without extraneous decorative animations.

### 4. Behavioral Guidance Playbooks
- **[guidance/four-laws.md](guidance/four-laws.md)**: Playbook covering the Four Laws of Behavior Change (Make It Obvious, Attractive, Easy, Satisfying) with concrete habit templates.
- **[guidance/anti-identities-and-balance.md](guidance/anti-identities-and-balance.md)**: Playbook detailing inversion principles, boundary guardrails, obstacle logging, and guilt-free balance.
- **[guidance/identities-playbook.md](guidance/identities-playbook.md)**: Step-by-step guidance on identity selection, evidence collection, and two-minute starters.

### 5. Automation, Services & Packaging
- **[service.ps1](service.ps1)** / **[service.bat](service.bat)**
  - **Responsibilities:** Windows background service runner and startup manager.
  - **Core Concerns:** Managing background execution via `pythonw`, querying port usage, installing/removing Windows startup shortcuts or registry entries.
- **[scripts/setup_python_runtime.ps1](scripts/setup_python_runtime.ps1)**
  - **Responsibilities:** Automated setup script for downloading and unpacking the official Python embeddable runtime.
  - **Core Concerns:** Bundling an offline, self-contained Python runtime into the Electron installer package.
- **[requirements.txt](requirements.txt)**
  - **Responsibilities:** Documents Python runtime version requirements and standard-library-only architecture.
- **[package.json](package.json)** / **[package-lock.json](package-lock.json)**
  - **Responsibilities:** Node.js package manifests for Electron dependencies, packaging configuration, and build scripts.
- **[.env.example](.env.example)** / **[.env](.env)**
  - **Responsibilities:** Explicit configuration declarations (`PORT`, `IDENTITY_OS_HOST`, `IDENTITY_OS_DB_PATH`, `IDENTITY_OS_STATIC_DIR`, `IDENTITY_OS_GUIDANCE_DIR`).

### 6. Testing & Quality Assurance
- **[tests/test_app.py](tests/test_app.py)**
  - **Responsibilities:** Comprehensive automated test suite for backend functionality.
  - **Core Concerns:**
    - Verifying empty bootstrap without invented fallbacks.
    - Verifying fractional identity distribution calculations (no double counting).
    - Testing identity, habit, and action CRUD operations.
    - Timestamp handling, devote, and soft/hard delete integrity.
    - Weekly review generation and HTTP API contract checks.
    - JSON export and import validation (schema integrity, merge vs replace).
    - Fail-loudly enforcement and error handling.
- **[TODO.md](TODO.md)**
  - **Responsibilities:** Centralized register of open code review findings, architectural improvements, and pending maintenance tasks.
