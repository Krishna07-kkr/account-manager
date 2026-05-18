# 🚀 Advanced Roblox Account Manager (RAM)
## Enterprise-Grade Production & Release Manual

A highly optimized, thread-isolated desktop administration suite for Roblox multi-instance account management, secure local data encryption, and remote-control Discord integration. Engineered with low-level Win32 hooks, memory cache controllers, and decoupled async websocket communication pipelines to bypass OS throttling, optimize CPU/RAM allocation, and enable zero-latency status tracking.

---

## 📑 Feature Index & System Architectures

### 1. Thread-Isolated UI Architecture & Responsive UX
Heavy operations—such as multi-instance game client launches, Selenium cookie injection, local DB encryption/decryption, and socket networking—are offloaded to isolated background execution thread queues. This decoupled structure keeps the main Python Tkinter application loop running uninterrupted, preventing typical desktop freeze conditions or "Not Responding" system hangs.

### 2. Single-Fetch In-Memory Caching Registry
To achieve a completely flicker-free and ultra-fast UI rendering sequence, the manager decouples heavy file-system reads and cryptographic decryption operations from drawing loops. 
* Account records and status parameters are fetched exactly once from the secure DPAPI-encrypted local vault on startup and populated into an in-memory runtime cache array (`self.accounts_cache`).
* UI updates pull directly and synchronously from this memory registry.
* Data mutation and file saving processes write immediately to the in-memory array first, then dispatch asynchronous background threads to encrypt and persist the updated database to the disk without stalling the UI rendering engine.

### 3. Native Win32 Memory Trim & Working Set Flush
The RAM optimization engine circumnavigates the system footprint limitations of running multiple concurrent client sessions:
* **Working Set Compaction**: Opens active Roblox client processes with `PROCESS_SET_QUOTA` and `PROCESS_QUERY_INFORMATION` rights, and programmatically invokes the native Win32 API `SetProcessWorkingSetSize(handle, -1, -1)` (EmptyWorkingSet).
* **Heap Recovery**: This forces the Windows Memory Manager to immediately trim the active physical working set of the target processes, flushing idle heap pages into system standby/paging storage, reducing RAM consumption per client by up to 80% with zero instability or client crashes.

### 4. Off-Screen Window Relocation & Throttling Circumvention
Windows operating systems aggressively throttle CPU cycles and rendering priority for background, hidden, or minimized application windows.
* To bypass these performance caps, the process watcher monitors window states using Win32 API calls (`GetWindowThreadProcessId`, `ShowWindow`, `SetWindowPos`).
* Minimized Roblox clients are immediately intercepted, restored, and repositioned to a coordinate offset outside the visible desktop screen grid (`X = -32000, Y = -32000`) before being placed back into a non-active background state.
* This tricks the OS scheduler into prioritizing the processes as fully visible and active, allowing automated rejoined loops and background automation routines to run at peak capacity.

### 5. Decoupled Discord WebSocket Gateway & Webhook Log Mirroring
* Implements a custom low-overhead async websocket handler to manage direct connections to the Discord Gateway API.
* Runs a persistent async heartbeat loop with custom debounce algorithms to protect the gateway socket and prevent rate limits.
* Mirrors standard console streams (`sys.stdout`, `sys.stderr`) programmatically into Discord channels using a custom log redirector payload, categorizing messages by type (SUCCESS, INFO, WARNING, ERROR) and dispatching them instantly via secure webhook pools.

---

## 🤖 Master Slash Command Reference

All slash interactions automatically issue a non-blocking `interaction.response.defer()` execution call on frame entry to prevent Discord gateway timeouts (404/10062 errors) during long-running launcher sequences or remote processes.

| Slash Command | Argument | Type | Requirement | Bound / Description |
| :--- | :--- | :--- | :--- | :--- |
| `/summary` | *None* | N/A | Optional | Queries the background status engine to compile detailed uptimes, connection stats, and cached Roblox headshot thumbnails. |
| `/admin_abuse` | `fps_cap` <br> `place_id` <br> `launch_delay` | Integer <br> String <br> Integer | **Required** <br> **Required** <br> **Required** | Closes running clients, updates `ClientAppSettings.json` with the requested FPS limit, and stagger-launches all account profiles. |
| `/free_memory` | *None* | N/A | Optional | Executes low-level native Win32 memory page trims against all active Roblox processes to reclaim physical system RAM. |
| `/kill_all` | *None* | N/A | Optional | Instantly terminates all active Roblox processes using high-speed background process tasks. |
| `/kill` | `target` | String | **Required** | Specify `'all'` or `'ram'` to close all clients, or enter a specific Roblox username to terminate only that process. |
| `/active_accounts` | *None* | N/A | Optional | Lists all active Roblox sessions, displaying their system PID identifiers and active game places. |
| `/validity_check` | *None* | N/A | Optional | Spawns a pool of background worker threads to authenticate and verify the health of all saved session cookies. |
| `/resource` | *None* | N/A | Optional | Monitors the host PC and returns real-time metrics of CPU load percentage, active RAM usage, and available memory. |
| `/join_all` | `place_id` | String | **Required** | Initiates a staggered batch launch for all registered accounts into the specified experience Place ID. |
| `/join` | `target` <br> `place_id` | String <br> String | **Required** <br> **Required** | Launches a designated Roblox username profile or `'all'` profiles into the requested experience Place ID. |
| `/addaccount` | `method` <br> `cookie` <br> `username` <br> `password` | String <br> String <br> String <br> String | **Required** <br> Optional <br> Optional <br> Optional | Remotely imports a profile into the local encrypted vault via a `.ROBLOSECURITY` cookie string or credentials. |
| `/list` | *None* | N/A | Optional | Compiles a scannable directories catalog containing all accounts loaded in RAM. |
| `/antiafk` | `status` | String | **Required** | Toggles the active status of the anti-afk keypress and mouse simulation engine (`enable` / `disable`). |
| `/settings` | `setting` <br> `value` | String <br> String | **Required** <br> **Required** | Remotely updates host configurations (Anti-AFK timer, Discord bot triggers, launch delay offsets, etc.). |
| `/activity_log` | `status` | String | **Required** | Toggles mirroring of console output streams directly to your Discord server webhook channel (`enable` / `disable`). |
| `/grab_place_id` | *None* | N/A | Optional | Compiles and displays a directory of all configured Roblox places and private server join paths. |
| `/help` | *None* | N/A | Optional | Displays a beautifully formatted diagnostic manual and slash command index directory. |

---

## 🛠️ Deployment & Setup Walkthrough

### 1. Environment Preparation
Ensure that your host system runs Windows 10/11 (64-bit) with Python 3.7+ installed.
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/evanovar/RobloxAccountManager
   cd RobloxAccountManager
   ```
2. **Install Locked Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Launch the Application**:
   - Standard Mode:
     ```bash
     python main.py
     ```
   - Synchronized Discord Command Mode (Required on first Discord Bot setup to map command tree):
     ```bash
     python main.py --sync
     ```

### 2. Discord Remote Integration Setup
To command your desktop launcher remotely, you must register a bot application:
1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and create a **New Application**.
2. Navigate to the **Bot** tab, generate a secure token, and enable the following **Privileged Gateway Intents**:
   * `PRESENCE INTENT`
   * `SERVER MEMBERS INTENT`
   * `MESSAGE CONTENT INTENT`
3. Navigate to the **OAuth2 > URL Generator** tab:
   * Under **Scopes**, check `bot` and `applications.commands`.
   * Under **Bot Permissions**, check `Administrator` (or appropriate Read/Write/Manage channel rights).
   * Copy the generated invitation link and open it in a browser to join the bot to your Discord server.
4. Paste your **Bot Token** and your personal **Discord User ID** (Authorized ID) inside the Roblox Account Manager **Settings > Integrations** tab, and toggle the bot interface on.

### 3. Windows Power State & Anti-Throttling System Tuning
To ensure uninterrupted background multi-instance automation, apply these system configurations:
1. **Configure Power Plan Optimization**:
   * Open Windows PowerShell as Administrator and run this command to unlock the Ultimate Performance power profile:
     ```powershell
     powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61
     ```
   * Open **Power Options** in Control Panel and select the new **Ultimate Performance** plan.
2. **Disable Windows Registry CPU Throttling**:
   * Open the Registry Editor (`regedit`) and navigate to:
     `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Power\PowerThrottling`
   * Create a new DWORD (32-bit) Value named `PowerThrottlingOff`.
   * Double-click it and set its value data to `1`.
   * Restart your system to apply these settings.

---

## 📄 License

This program is open-source software and is licensed under the [GPL 3.0 License](LICENSE).
