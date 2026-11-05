const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  isElectron: true,
  exportJson: () => ipcRenderer.invoke("dialog-export-json"),
  importJson: (mode = "merge") => ipcRenderer.invoke("dialog-import-json", mode),
});
