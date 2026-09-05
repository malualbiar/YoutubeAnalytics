/**
 * YT Quid - Electron Main Process
 * Manages native window lifecycle and embedded Python/Django WSGI server.
 */

const { app, BrowserWindow, shell, dialog } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const http = require('http');

let mainWindow = null;
let pythonProcess = null;
let serverUrl = null;
let isQuitting = false;

// 1. Enforce Single Instance
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.focus();
        }
    });
}

/**
 * Determine the appropriate Python executable path.
 */
function getPythonExecutable() {
    // Check if packaged with bundled backend
    if (app.isPackaged) {
        const bundledBackend = path.join(process.resourcesPath, 'backend', 'server.exe');
        if (require('fs').existsSync(bundledBackend)) {
            return { cmd: bundledBackend, args: [], cwd: path.dirname(bundledBackend) };
        }
        throw new Error(`Bundled backend executable not found at: ${bundledBackend}`);
    }

    // Check local virtual environments in project directory
    const venvWindows = path.join(__dirname, 'venv', 'Scripts', 'python.exe');
    const dotVenvWindows = path.join(__dirname, '.venv', 'Scripts', 'python.exe');
    const venvUnix = path.join(__dirname, 'venv', 'bin', 'python');

    if (require('fs').existsSync(venvWindows)) {
        return { cmd: venvWindows, args: [path.join(__dirname, 'server.py')], cwd: __dirname };
    }
    if (require('fs').existsSync(dotVenvWindows)) {
        return { cmd: dotVenvWindows, args: [path.join(__dirname, 'server.py')], cwd: __dirname };
    }
    if (require('fs').existsSync(venvUnix)) {
        return { cmd: venvUnix, args: [path.join(__dirname, 'server.py')], cwd: __dirname };
    }

    // System Python fallback
    return { cmd: 'python', args: [path.join(__dirname, 'server.py')], cwd: __dirname };
}

/**
 * Launch embedded Python server and wait for readiness.
 */
function startPythonServer() {
    return new Promise((resolve, reject) => {
        let py;
        try {
            py = getPythonExecutable();
        } catch (err) {
            return reject(err);
        }
        console.log(`[YT Quid] Launching backend: ${py.cmd} ${py.args.join(' ')}`);

        pythonProcess = spawn(py.cmd, py.args, {
            cwd: py.cwd,
            env: { ...process.env, PYTHONUNBUFFERED: '1', YT_QUID_DESKTOP: '1' }
        });

        let serverReady = false;

        pythonProcess.stdout.on('data', (data) => {
            const text = data.toString();
            console.log(`[Backend stdout] ${text.trim()}`);

            const readyMatch = text.match(/SERVER_READY:(http:\/\/[^\s\r\n]+)/);
            if (readyMatch && !serverReady) {
                serverReady = true;
                serverUrl = readyMatch[1];
                resolve(serverUrl);
            }
        });

        pythonProcess.stderr.on('data', (data) => {
            console.error(`[Backend stderr] ${data.toString().trim()}`);
        });

        pythonProcess.on('error', (err) => {
            console.error('[YT Quid] Failed to start Python backend:', err);
            if (!serverReady) reject(err);
        });

        pythonProcess.on('close', (code) => {
            console.log(`[YT Quid] Python backend process exited with code ${code}`);
            if (!serverReady) {
                reject(new Error(`Backend exited prematurely with code ${code}`));
            }
        });

        // 15-second startup timeout safety
        setTimeout(() => {
            if (!serverReady) {
                reject(new Error('Timed out waiting for Python backend to start.'));
            }
        }, 15000);
    });
}

/**
 * Create the main desktop application window.
 */
function createMainWindow(url) {
    mainWindow = new BrowserWindow({
        width: 1340,
        height: 880,
        minWidth: 1050,
        minHeight: 700,
        backgroundColor: '#09090b',
        darkTheme: true,
        show: false,
        title: 'YT Quid - Artist Analytics',
        autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: false
        }
    });

    mainWindow.loadURL(url);

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // Handle external links (e.g. YouTube video pages or channel links)
    mainWindow.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
        if (!targetUrl.startsWith(serverUrl)) {
            shell.openExternal(targetUrl);
            return { action: 'deny' };
        }
        return { action: 'allow' };
    });

    mainWindow.webContents.on('will-navigate', (event, targetUrl) => {
        if (!targetUrl.startsWith(serverUrl)) {
            event.preventDefault();
            shell.openExternal(targetUrl);
        }
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

/**
 * Cleanly terminate the Python subprocess tree on exit.
 */
function killPythonProcess() {
    if (pythonProcess && pythonProcess.pid) {
        console.log(`[YT Quid] Terminating Python process (PID ${pythonProcess.pid})...`);
        try {
            if (process.platform === 'win32') {
                exec(`taskkill /pid ${pythonProcess.pid} /T /F`, (err) => {
                    if (err) console.log('[YT Quid] Taskkill notice:', err.message);
                });
            } else {
                pythonProcess.kill('SIGTERM');
            }
        } catch (e) {
            console.error('[YT Quid] Error during process cleanup:', e);
        }
        pythonProcess = null;
    }
}

// App Lifecycle Handlers
app.on('ready', async () => {
    try {
        const url = await startPythonServer();
        createMainWindow(url);
    } catch (err) {
        dialog.showErrorBox(
            'YT Quid Startup Error',
            `Could not start the backend server:\n${err.message}\n\nPlease verify that Python dependencies are installed.`
        );
        app.quit();
    }
});

app.on('before-quit', () => {
    isQuitting = true;
    killPythonProcess();
});

app.on('window-all-closed', () => {
    killPythonProcess();
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (mainWindow === null && serverUrl) {
        createMainWindow(serverUrl);
    }
});

process.on('exit', () => {
    killPythonProcess();
});
