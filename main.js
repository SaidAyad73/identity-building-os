const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require("electron");
const path = require("path");
const http = require("http");
const fs = require("fs");
const { spawn } = require("child_process");

const SERVER_HOST = process.env.IDENTITY_OS_HOST || "127.0.0.1";
const SERVER_PORT = process.env.PORT || 8765;
const SERVER_URL = `http://${SERVER_HOST}:${SERVER_PORT}`;

let mainWindow = null;
let pythonProcess = null;
let isQuitting = false;

function checkServerHealthy() {
  return new Promise((resolve) => {
    const req = http.get(`${SERVER_URL}/api/state`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureBackendRunning() {
  const isHealthy = await checkServerHealthy();
  if (isHealthy) {
    return;
  }

  const pythonCmd = process.platform === "win32" ? "python" : "python3";
  const appPath = path.join(__dirname, "app.py");

  pythonProcess = spawn(pythonCmd, [appPath], {
    cwd: __dirname,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PORT: String(SERVER_PORT), IDENTITY_OS_HOST: SERVER_HOST },
  });

  pythonProcess.stdout.on("data", (data) => {
    process.stdout.write(`[Python]: ${data}`);
  });

  pythonProcess.stderr.on("data", (data) => {
    process.stderr.write(`[Python error]: ${data}`);
  });

  pythonProcess.on("exit", (code, signal) => {
    if (!isQuitting && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox(
        "Backend Terminated",
        `The Identity OS Python process unexpectedly stopped (code ${code}).`
      );
    }
  });

  const start = Date.now();
  while (Date.now() - start < 15000) {
    await new Promise((r) => setTimeout(r, 400));
    const healthy = await checkServerHealthy();
    if (healthy) {
      return;
    }
  }

  throw new Error("Timeout waiting for Identity OS Python backend to start.");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 920,
    minHeight: 620,
    title: "Identity Building OS",
    backgroundColor: "#0f172a",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  mainWindow.loadURL(SERVER_URL);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  setupAppMenu();
}

function setupAppMenu() {
  const template = [
    {
      label: "File",
      submenu: [
        {
          label: "Export JSON Backup...",
          accelerator: "CmdOrCtrl+E",
          click: async () => {
            if (mainWindow) {
              mainWindow.webContents.executeJavaScript("exportJsonData()");
            }
          },
        },
        {
          label: "Import JSON Backup...",
          accelerator: "CmdOrCtrl+I",
          click: async () => {
            if (mainWindow) {
              mainWindow.webContents.executeJavaScript("triggerImportJson('replace')");
            }
          },
        },
        { type: "separator" },
        {
          label: "Open Data Directory",
          click: () => {
            const dataDir = path.join(__dirname, "data");
            if (!fs.existsSync(dataDir)) {
              fs.mkdirSync(dataDir, { recursive: true });
            }
            shell.openPath(dataDir);
          },
        },
        { type: "separator" },
        {
          label: "Quit",
          accelerator: "CmdOrCtrl+Q",
          click: () => {
            app.quit();
          },
        },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { type: "separator" },
        {
          label: "Toggle 2-Minute Mode",
          accelerator: "CmdOrCtrl+M",
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.executeJavaScript(
                'document.getElementById("twoMinModeBtn").click()'
              );
            }
          },
        },
        {
          label: "Toggle Dark / Light Theme",
          accelerator: "CmdOrCtrl+T",
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.executeJavaScript(
                'document.getElementById("themeToggleBtn").click()'
              );
            }
          },
        },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
        { role: "toggleDevTools" },
      ],
    },
    {
      label: "Help",
      submenu: [
        {
          label: "Atomic Habits Playbook",
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.executeJavaScript("switchView('guidance')");
            }
          },
        },
        {
          label: "About Identity Building OS",
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: "info",
              title: "About Identity Building OS",
              message: "Identity Building OS",
              detail:
                "A calm, visual personal system for becoming who you want to be.\nInspired by Atomic Habits by James Clear.",
            });
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

ipcMain.handle("dialog-export-json", async () => {
  if (!mainWindow) return { canceled: true };
  const dateStr = new Date().toISOString().slice(0, 10);
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: "Export Identity OS Data (JSON)",
    defaultPath: `identity_os_backup_${dateStr}.json`,
    filters: [{ name: "JSON Files", extensions: ["json"] }],
  });

  if (canceled || !filePath) return { canceled: true };

  try {
    const rawData = await fetchJsonFromLocalServer("/api/export");
    fs.writeFileSync(filePath, JSON.stringify(rawData, null, 2), "utf-8");
    return { saved: true, filePath };
  } catch (err) {
    dialog.showErrorBox("Export Error", `Failed to save JSON export: ${err.message}`);
    throw err;
  }
});

ipcMain.handle("dialog-import-json", async (event, mode = "replace") => {
  if (!mainWindow) return { canceled: true };
  const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
    title: `Import Identity OS Data (${mode === "merge" ? "Merge" : "Restore"} mode)`,
    filters: [{ name: "JSON Files", extensions: ["json"] }],
    properties: ["openFile"],
  });

  if (canceled || !filePaths || filePaths.length === 0) return { canceled: true };

  try {
    const content = fs.readFileSync(filePaths[0], "utf-8");
    const parsed = JSON.parse(content);
    const result = await postJsonToLocalServer("/api/import", {
      mode,
      data: parsed.data || parsed,
    });
    return { imported: true, mode, result };
  } catch (err) {
    dialog.showErrorBox("Import Error", `Failed to import JSON: ${err.message}`);
    throw err;
  }
});

function fetchJsonFromLocalServer(endpoint) {
  return new Promise((resolve, reject) => {
    http.get(`${SERVER_URL}${endpoint}`, (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(e);
        }
      });
    }).on("error", reject);
  });
}

function postJsonToLocalServer(endpoint, payload) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const req = http.request(
      `${SERVER_URL}${endpoint}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(data),
        },
      },
      (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }
    );
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

app.whenReady().then(async () => {
  try {
    await ensureBackendRunning();
    createWindow();
  } catch (err) {
    dialog.showErrorBox("Startup Error", err.message);
    app.quit();
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  isQuitting = true;
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
