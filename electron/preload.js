const { contextBridge, ipcRenderer } = require('electron');

// Expose safe API to renderer (React app)
contextBridge.exposeInMainWorld('electron', {
  // Window controls
  minimize: () => ipcRenderer.invoke('window:minimize'),
  maximize: () => ipcRenderer.invoke('window:maximize'),
  close: () => ipcRenderer.invoke('window:close'),
  alwaysOnTop: (val) => ipcRenderer.invoke('window:alwaysOnTop', val),
  quit: () => ipcRenderer.invoke('app:quit'),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),

  // Zara backend
  sendCommand: (text) => ipcRenderer.invoke('zara:command', text),

  // Backend output listeners
  onBackendLog: (cb) => ipcRenderer.on('backend:log', (_, data) => cb(data)),
  onBackendError: (cb) => ipcRenderer.on('backend:error', (_, data) => cb(data)),
  removeAllListeners: (ch) => ipcRenderer.removeAllListeners(ch),

  // Platform detection
  isElectron: true,
  platform: process.platform,
});
