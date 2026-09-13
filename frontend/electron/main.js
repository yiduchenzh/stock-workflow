const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron')
const path = require('path')
const { spawn } = require('child_process')

let mainWindow = null
let tray = null
let backendProcess = null

const BACKEND_PORT = 7878
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const isDev = !app.isPackaged

function startBackend() {
  const projectRoot = path.resolve(__dirname, '..')
  const python = path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
  const backendScript = path.join(projectRoot, 'run_live.py')

  backendProcess = spawn(python, [backendScript], {
    cwd: projectRoot,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, AURORA_MODE: 'desktop' },
  })

  backendProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data}`)
  })
  backendProcess.stderr.on('data', (data) => {
    console.error(`[Backend] ${data}`)
  })
  backendProcess.on('close', (code) => {
    console.log(`[Backend] exited with code ${code}`)
  })
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Aurora AI 量化投资',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    backgroundColor: '#0A0E17',
    show: false,
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadURL(BACKEND_URL)
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault()
      mainWindow.hide()
    }
  })
}

function createTray() {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  
  const contextMenu = Menu.buildFromTemplate([
    { label: '显示窗口', click: () => { mainWindow?.show() } },
    { label: '退出', click: () => { app.isQuitting = true; app.quit() } },
  ])
  
  tray.setToolTip('Aurora AI 量化投资')
  tray.setContextMenu(contextMenu)
  tray.on('double-click', () => { mainWindow?.show() })
}

app.whenReady().then(() => {
  startBackend()
  createWindow()
  createTray()
})

app.on('window-all-closed', () => {
  // Don't quit on window close - keep running in tray
})

app.on('before-quit', () => {
  stopBackend()
})

app.on('activate', () => {
  if (mainWindow === null) createWindow()
  else mainWindow.show()
})
