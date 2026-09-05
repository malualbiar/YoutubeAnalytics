/**
 * YT Quid Electron Preload Script
 * Secure context bridge between Electron main process and renderer.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopApp', {
    platform: process.platform,
    version: '1.0.0',
    isDesktop: true
});
