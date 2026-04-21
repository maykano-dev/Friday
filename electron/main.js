const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, shell, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

let mainWindow;
let tray;
let zaraProcess; // Python backend process

// ── Backend Process ────────────────────────────────────────────────
function startZaraBackend() {
  const backendPath = isDev
    ? path.join(__dirname, '../../main.py')
    : path.join(process.resourcesPath, 'zara_backend', 'main.py');

  const python = process.platform === 'win32' ? 'python' : 'python3';

  zaraProcess = spawn(python, [backendPath], {
    cwd: path.dirname(backendPath),
    windowsHide: true, // No console window popup
  });

  zaraProcess.stdout.on('data', (data) => {
    if (mainWindow) mainWindow.webContents.send('backend:log', data.toString());
  });

  zaraProcess.stderr.on('data', (data) => {
    if (mainWindow) mainWindow.webContents.send('backend:error', data.toString());
  });

  zaraProcess.on('close', (code) => {
    console.log(`Zara backend exited with code ${code}`);
  });
}

// ── Main Window ─────────────────────────────────────────────────────
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    frame: false,            // Frameless - custom titlebar
    transparent: false,
    backgroundColor: '#060810',
    titleBarStyle: 'hidden',
    titleBarOverlay: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    icon: path.join(__dirname, '../public/icon.png'),
    show: false,             // Don't show until ready
  });

  // Always on top option (configurable)
  mainWindow.setAlwaysOnTop(false);

  const url = isDev
    ? 'http://localhost:3000'
    : `file://${path.join(__dirname, '../build/index.html')}`;

  mainWindow.loadURL(url);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (isDev) mainWindow.webContents.openDevTools();
  });

  mainWindow.on('closed', () => { mainWindow = null; });

  // Prevent window close - minimize to tray instead
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

// ── System Tray ─────────────────────────────────────────────────────
function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, '../public/icon.png'));
  tray = new Tray(icon.resize({ width: 16, height: 16 }));

  const menu = Menu.buildFromTemplate([
    { label: 'Show Zara', click: () => mainWindow?.show() },
    { label: 'Hide', click: () => mainWindow?.hide() },
    { type: 'separator' },
    {
      label: 'Always on Top',
      type: 'checkbox',
      checked: false,
      click: (item) => mainWindow?.setAlwaysOnTop(item.checked),
    },
    { type: 'separator' },
    { label: 'Quit Zara', click: () => { app.isQuitting = true; app.quit(); } },
  ]);

  tray.setContextMenu(menu);
  tray.setToolTip('Zara Neural AI');
  tray.on('double-click', () => mainWindow?.show());
}

// ── IPC Handlers ─────────────────────────────────────────────────────
ipcMain.handle('window:minimize', () => mainWindow?.minimize());
ipcMain.handle('window:maximize', () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.handle('window:close', () => mainWindow?.hide());
ipcMain.handle('window:alwaysOnTop', (_, val) => mainWindow?.setAlwaysOnTop(val));
ipcMain.handle('app:quit', () => { app.isQuitting = true; app.quit(); });
ipcMain.handle('shell:openExternal', (_, url) => shell.openExternal(url));

// Send command to Zara backend via stdin
ipcMain.handle('zara:command', (_, text) => {
  if (zaraProcess?.stdin) {
    zaraProcess.stdin.write(JSON.stringify({ type: 'command', text }) + '\n');
  }
});

// ── App Lifecycle ─────────────────────────────────────────────────────
app.whenReady().then(() => {
  // ── Content Security Policy ──────────────────────────────────────────
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          [
            "default-src 'self'",
            "script-src 'self'" + (isDev ? " 'unsafe-eval'" : ""),
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "connect-src 'self' ws://localhost:8765 http://localhost:3000 ws://localhost:3000",
            "img-src 'self' data: https:",
          ].join('; '),
        ],
      },
    });
  });

  createMainWindow();
  createTray();
  // Start backend only in production (dev runs its own backend)
  if (!isDev) startZaraBackend();

  app.on('activate', () => {
    if (!mainWindow) createMainWindow();
    else mainWindow.show();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (zaraProcess) {
    zaraProcess.kill();
  }
});
