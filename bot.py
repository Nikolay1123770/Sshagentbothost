import os
import json
import secrets
import asyncio
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from io import BytesIO
from typing import Dict, List, Optional

from fastapi import FastAPI, Request, Response, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import paramiko
from paramiko import SFTPClient, SSHClient

# ============ НАСТРОЙКА ЛОГГИНГА ============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ КОНФИГУРАЦИЯ ============
BOT_TOKEN = "8360387336:AAGKU0Jv3CeJ-WubZH6VCPsL4-NDlrcbxp4"
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))

logger.info(f"=== SSH Agent Pro ===")
logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")

# ============ ХРАНИЛИЩЕ ДАННЫХ ============
user_sessions: Dict[str, Dict] = {}  # {user_id: {'servers': [], 'current_connection': None, 'sftp': None}}
web_sessions: Dict[str, Dict] = {}   # {session_id: {'servers': [], 'current_connection': None, 'sftp': None}}

# ============ FASTAPI APPLICATION ============
app = FastAPI(title="SSH Agent Pro", version="2.0")
templates = Jinja2Templates(directory="templates")

# Модели данных
class Server(BaseModel):
    name: str
    host: str
    port: int = 22
    user: str
    password: str

class CommandRequest(BaseModel):
    command: str

class PathRequest(BaseModel):
    path: str = "/"

# ============ HTML ШАБЛОН ============
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 SSH Agent Pro - Расширенное управление серверами</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --primary: #667eea;
            --primary-dark: #5a67d8;
            --secondary: #764ba2;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --dark: #1f2937;
            --light: #f9fafb;
            --gray: #9ca3af;
            --gray-light: #e5e7eb;
            --terminal-bg: #0f172a;
            --terminal-text: #22c55e;
            --sidebar-bg: #1e293b;
            --card-bg: white;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            min-height: 100vh;
            color: var(--dark);
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: var(--card-bg);
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .app-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 30px 40px;
            text-align: center;
        }
        
        .app-header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .app-header p {
            opacity: 0.9;
            font-size: 1.1rem;
        }
        
        .app-nav {
            background: var(--sidebar-bg);
            padding: 20px;
            display: flex;
            gap: 10px;
            overflow-x: auto;
        }
        
        .nav-btn {
            padding: 12px 24px;
            background: rgba(255,255,255,0.1);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
            white-space: nowrap;
        }
        
        .nav-btn:hover {
            background: rgba(255,255,255,0.2);
            transform: translateY(-2px);
        }
        
        .nav-btn.active {
            background: var(--primary);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        
        .content-area {
            padding: 30px;
            min-height: 600px;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
            animation: fadeIn 0.3s ease-in;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Dashboard */
        .dashboard-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: var(--light);
            padding: 25px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        }
        
        .stat-card i {
            font-size: 2.5rem;
            color: var(--primary);
            margin-bottom: 15px;
        }
        
        .stat-card h3 {
            font-size: 2.2rem;
            margin-bottom: 5px;
            color: var(--dark);
        }
        
        .stat-card p {
            color: var(--gray);
            font-size: 0.9rem;
        }
        
        /* Terminal */
        .terminal-container {
            background: var(--terminal-bg);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 20px;
        }
        
        .terminal-header {
            background: #1e293b;
            padding: 15px 20px;
            display: flex;
            align-items: center;
            border-bottom: 1px solid #334155;
        }
        
        .terminal-dots {
            display: flex;
            gap: 8px;
        }
        
        .terminal-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        
        .terminal-dot.red { background: #ef4444; }
        .terminal-dot.yellow { background: #f59e0b; }
        .terminal-dot.green { background: #10b981; }
        
        .terminal-body {
            padding: 20px;
            min-height: 400px;
            max-height: 500px;
            overflow-y: auto;
        }
        
        .terminal-output {
            color: var(--terminal-text);
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .terminal-input {
            display: flex;
            background: #1e293b;
            padding: 15px;
            border-top: 1px solid #334155;
        }
        
        .terminal-prompt {
            color: var(--terminal-text);
            margin-right: 10px;
            font-family: 'Courier New', monospace;
            padding: 8px 0;
        }
        
        .terminal-input-field {
            flex: 1;
            background: transparent;
            border: none;
            color: white;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            outline: none;
            padding: 8px;
        }
        
        /* Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
            gap: 8px;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .btn-success {
            background: var(--success);
            color: white;
        }
        
        .btn-danger {
            background: var(--danger);
            color: white;
        }
        
        .btn-outline {
            background: transparent;
            border: 2px solid var(--primary);
            color: var(--primary);
        }
        
        /* Server List */
        .servers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .server-card {
            background: var(--light);
            border-radius: 12px;
            padding: 20px;
            border: 2px solid var(--gray-light);
            transition: all 0.3s;
        }
        
        .server-card.active {
            border-color: var(--primary);
            background: #f0f5ff;
        }
        
        .server-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }
        
        .server-name {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 10px;
            color: var(--dark);
        }
        
        .server-details {
            color: var(--gray);
            font-size: 0.9rem;
            margin-bottom: 15px;
        }
        
        .server-actions {
            display: flex;
            gap: 10px;
        }
        
        /* File Manager */
        .file-manager {
            background: var(--light);
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }
        
        .fm-toolbar {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .file-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 15px;
        }
        
        .file-item {
            background: white;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            border: 2px solid transparent;
        }
        
        .file-item:hover {
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            border-color: var(--primary);
        }
        
        .file-icon {
            font-size: 2rem;
            color: var(--primary);
            margin-bottom: 10px;
        }
        
        .file-name {
            font-size: 0.9rem;
            font-weight: 600;
            margin-bottom: 5px;
            word-break: break-all;
        }
        
        /* Modals */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 16px;
            max-width: 500px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        
        .modal-header {
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--gray-light);
        }
        
        .modal-header h2 {
            color: var(--dark);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--dark);
        }
        
        .form-input {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid var(--gray-light);
            border-radius: 8px;
            font-size: 14px;
            transition: border 0.3s;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--primary);
        }
        
        .form-actions {
            display: flex;
            gap: 10px;
            margin-top: 30px;
        }
        
        /* Connection Status */
        .connection-status {
            padding: 20px;
            background: var(--light);
            border-radius: 12px;
            margin-bottom: 20px;
        }
        
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        .status-online {
            background: var(--success);
            box-shadow: 0 0 10px var(--success);
        }
        
        .status-offline {
            background: var(--danger);
            box-shadow: 0 0 10px var(--danger);
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .dashboard-stats {
                grid-template-columns: 1fr;
            }
            
            .servers-grid {
                grid-template-columns: 1fr;
            }
            
            .app-nav {
                flex-wrap: wrap;
            }
            
            .nav-btn {
                flex: 1;
                min-width: 120px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="app-header">
            <h1><i class="fas fa-terminal"></i> SSH Agent Pro</h1>
            <p>Расширенное управление SSH серверами</p>
        </div>
        
        <div class="app-nav">
            <button class="nav-btn active" onclick="showTab('dashboard')">
                <i class="fas fa-tachometer-alt"></i> Дашборд
            </button>
            <button class="nav-btn" onclick="showTab('servers')">
                <i class="fas fa-server"></i> Серверы
            </button>
            <button class="nav-btn" onclick="showTab('terminal')">
                <i class="fas fa-terminal"></i> Терминал
            </button>
            <button class="nav-btn" onclick="showTab('filemanager')">
                <i class="fas fa-folder-open"></i> Файлы
            </button>
            <button class="nav-btn" onclick="showTab('monitoring')">
                <i class="fas fa-chart-line"></i> Мониторинг
            </button>
        </div>
        
        <div class="content-area">
            <!-- Dashboard -->
            <div id="dashboard" class="tab-content active">
                <div class="connection-status">
                    <div class="status-indicator">
                        <span class="status-dot status-offline"></span>
                        <span id="statusText">Сервер не подключен</span>
                    </div>
                </div>
                
                <div class="dashboard-stats">
                    <div class="stat-card">
                        <i class="fas fa-server"></i>
                        <h3 id="serversCount">0</h3>
                        <p>Серверов</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-plug"></i>
                        <h3 id="activeConnections">0</h3>
                        <p>Подключений</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-code"></i>
                        <h3 id="commandsCount">0</h3>
                        <p>Команд</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-file"></i>
                        <h3 id="filesCount">0</h3>
                        <p>Файлов</p>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 40px 0;">
                    <button class="btn btn-primary" style="padding: 15px 30px; font-size: 16px;" onclick="showTab('servers')">
                        <i class="fas fa-plus"></i> Добавить первый сервер
                    </button>
                </div>
            </div>
            
            <!-- Servers -->
            <div id="servers" class="tab-content">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h2 style="color: var(--dark);">Управление серверами</h2>
                    <button class="btn btn-primary" onclick="openAddServerModal()">
                        <i class="fas fa-plus"></i> Добавить сервер
                    </button>
                </div>
                
                <div id="serversList">
                    <!-- Серверы будут загружены здесь -->
                </div>
            </div>
            
            <!-- Terminal -->
            <div id="terminal" class="tab-content">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h2 style="color: var(--dark);">SSH Терминал</h2>
                    <div>
                        <button class="btn btn-outline" onclick="clearTerminal()">
                            <i class="fas fa-broom"></i> Очистить
                        </button>
                        <button class="btn btn-success" id="execBtn" disabled onclick="executeCommand()">
                            <i class="fas fa-play"></i> Выполнить
                        </button>
                    </div>
                </div>
                
                <div class="terminal-container">
                    <div class="terminal-header">
                        <div class="terminal-dots">
                            <div class="terminal-dot red"></div>
                            <div class="terminal-dot yellow"></div>
                            <div class="terminal-dot green"></div>
                        </div>
                    </div>
                    <div class="terminal-body">
                        <div class="terminal-output" id="terminalOutput">
Добро пожаловать в SSH Agent Pro!
Для начала работы:
1. Добавьте сервер на вкладке "Серверы"
2. Подключитесь к серверу
3. Используйте терминал для управления
                        </div>
                    </div>
                    <div class="terminal-input">
                        <span class="terminal-prompt">$</span>
                        <input type="text" class="terminal-input-field" id="commandInput" 
                               placeholder="Введите команду..." disabled
                               onkeypress="if(event.key === 'Enter') executeCommand()">
                    </div>
                </div>
                
                <div style="margin-top: 20px;">
                    <h3 style="color: var(--dark); margin-bottom: 10px;">Быстрые команды:</h3>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button class="btn btn-outline" onclick="insertCommand('pwd')">pwd</button>
                        <button class="btn btn-outline" onclick="insertCommand('ls -la')">ls -la</button>
                        <button class="btn btn-outline" onclick="insertCommand('df -h')">df -h</button>
                        <button class="btn btn-outline" onclick="insertCommand('free -m')">free -m</button>
                        <button class="btn btn-outline" onclick="insertCommand('top -n 1')">top</button>
                        <button class="btn btn-outline" onclick="insertCommand('whoami')">whoami</button>
                    </div>
                </div>
            </div>
            
            <!-- File Manager -->
            <div id="filemanager" class="tab-content">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h2 style="color: var(--dark);">Файловый менеджер</h2>
                    <div>
                        <button class="btn btn-outline" onclick="refreshFiles()">
                            <i class="fas fa-sync"></i> Обновить
                        </button>
                        <button class="btn btn-primary" onclick="openUploadModal()">
                            <i class="fas fa-upload"></i> Загрузить
                        </button>
                    </div>
                </div>
                
                <div class="file-manager">
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: var(--dark); margin-bottom: 10px;">Текущий путь:</h3>
                        <div style="background: white; padding: 10px 15px; border-radius: 8px; font-family: monospace;" id="currentPath">/</div>
                    </div>
                    
                    <div class="fm-toolbar">
                        <button class="btn btn-outline" onclick="goUp()">
                            <i class="fas fa-level-up-alt"></i> Наверх
                        </button>
                        <button class="btn btn-outline" onclick="createFolder()">
                            <i class="fas fa-folder-plus"></i> Новая папка
                        </button>
                        <button class="btn btn-danger" onclick="deleteSelected()" id="deleteBtn" disabled>
                            <i class="fas fa-trash"></i> Удалить выбранное
                        </button>
                    </div>
                    
                    <div id="fileList">
                        <!-- Файлы будут загружены здесь -->
                    </div>
                </div>
            </div>
            
            <!-- Monitoring -->
            <div id="monitoring" class="tab-content">
                <h2 style="color: var(--dark); margin-bottom: 20px;">Мониторинг серверов</h2>
                <div id="monitoringContent">
                    <p>Для просмотра мониторинга подключитесь к серверу.</p>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Modal: Add Server -->
    <div class="modal" id="addServerModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2><i class="fas fa-plus"></i> Добавить SSH сервер</h2>
            </div>
            <div class="form-group">
                <label class="form-label">Название сервера</label>
                <input type="text" class="form-input" id="serverName" placeholder="Мой Production сервер">
            </div>
            <div class="form-group">
                <label class="form-label">Хост/IP адрес</label>
                <input type="text" class="form-input" id="serverHost" placeholder="192.168.1.100 или domain.com">
            </div>
            <div class="form-group">
                <label class="form-label">Порт SSH</label>
                <input type="number" class="form-input" id="serverPort" value="22">
            </div>
            <div class="form-group">
                <label class="form-label">Имя пользователя</label>
                <input type="text" class="form-input" id="serverUser" placeholder="root">
            </div>
            <div class="form-group">
                <label class="form-label">Пароль</label>
                <input type="password" class="form-input" id="serverPassword" placeholder="Введите пароль">
            </div>
            <div class="form-actions">
                <button class="btn btn-primary" onclick="addServer()">
                    <i class="fas fa-check"></i> Добавить
                </button>
                <button class="btn btn-danger" onclick="closeModal('addServerModal')">
                    <i class="fas fa-times"></i> Отмена
                </button>
            </div>
        </div>
    </div>
    
    <!-- Modal: Upload Files -->
    <div class="modal" id="uploadModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2><i class="fas fa-upload"></i> Загрузка файлов</h2>
            </div>
            <div class="form-group">
                <label class="form-label">Путь для загрузки</label>
                <input type="text" class="form-input" id="uploadPath" value="/tmp">
            </div>
            <div class="form-group">
                <label class="form-label">Выберите файлы</label>
                <input type="file" class="form-input" id="fileUpload" multiple>
            </div>
            <div class="form-actions">
                <button class="btn btn-success" onclick="uploadFiles()">
                    <i class="fas fa-upload"></i> Загрузить
                </button>
                <button class="btn btn-danger" onclick="closeModal('uploadModal')">
                    <i class="fas fa-times"></i> Отмена
                </button>
            </div>
        </div>
    </div>

    <script>
        // Глобальные переменные
        let currentServer = null;
        let servers = [];
        let commandsExecuted = 0;
        let filesProcessed = 0;
        let currentPath = '/';
        let selectedFiles = new Set();
        
        // Инициализация
        document.addEventListener('DOMContentLoaded', function() {
            loadServers();
            updateStats();
            
            // Загрузить сессию из localStorage
            const savedSession = localStorage.getItem('ssh_agent_session');
            if (savedSession) {
                try {
                    const sessionData = JSON.parse(savedSession);
                    servers = sessionData.servers || [];
                    currentServer = sessionData.currentServer;
                    commandsExecuted = sessionData.commandsExecuted || 0;
                    filesProcessed = sessionData.filesProcessed || 0;
                    
                    if (currentServer !== null) {
                        updateConnectionStatus(true);
                    }
                    renderServers();
                    updateStats();
                } catch (e) {
                    console.error('Ошибка загрузки сессии:', e);
                }
            }
        });
        
        // Навигация
        function showTab(tabName) {
            // Скрыть все вкладки
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Убрать active у всех кнопок
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Показать выбранную вкладку
            document.getElementById(tabName).classList.add('active');
            
            // Активировать кнопку
            document.querySelector(`.nav-btn[onclick*="${tabName}"]`).classList.add('active');
            
            // При показе файлового менеджера загрузить файлы
            if (tabName === 'filemanager' && currentServer !== null) {
                loadFiles(currentPath);
            }
        }
        
        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }
        
        function openModal(modalId) {
            document.getElementById(modalId).classList.add('active');
        }
        
        // Серверы
        function openAddServerModal() {
            openModal('addServerModal');
        }
        
        function addServer() {
            const server = {
                name: document.getElementById('serverName').value,
                host: document.getElementById('serverHost').value,
                port: parseInt(document.getElementById('serverPort').value),
                user: document.getElementById('serverUser').value,
                password: document.getElementById('serverPassword').value
            };
            
            if (!server.name || !server.host || !server.user) {
                alert('Заполните обязательные поля');
                return;
            }
            
            fetch('/api/servers', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(server)
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    closeModal('addServerModal');
                    
                    // Добавить сервер в локальный список
                    servers.push(server);
                    renderServers();
                    updateStats();
                    saveSession();
                    
                    // Очистить форму
                    document.getElementById('serverName').value = '';
                    document.getElementById('serverHost').value = '';
                    document.getElementById('serverPort').value = '22';
                    document.getElementById('serverUser').value = '';
                    document.getElementById('serverPassword').value = '';
                    
                    alert('✅ Сервер добавлен!');
                } else {
                    alert('❌ Ошибка: ' + data.error);
                }
            });
        }
        
        function loadServers() {
            fetch('/api/servers')
                .then(r => r.json())
                .then(data => {
                    if (data.servers) {
                        servers = data.servers;
                        renderServers();
                        updateStats();
                    }
                });
        }
        
        function renderServers() {
            const container = document.getElementById('serversList');
            
            if (servers.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 40px;">
                        <i class="fas fa-server fa-4x" style="color: #9ca3af; margin-bottom: 20px;"></i>
                        <h3 style="color: #6b7280; margin-bottom: 10px;">Серверы не добавлены</h3>
                        <p style="color: #9ca3af;">Добавьте свой первый сервер для начала работы</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = `
                <div class="servers-grid">
                    ${servers.map((server, index) => `
                        <div class="server-card ${currentServer === index ? 'active' : ''}">
                            <div class="server-name">
                                <i class="fas fa-server"></i> ${server.name}
                                ${currentServer === index ? '<span style="color: var(--success); margin-left: 10px;"><i class="fas fa-plug"></i> Подключен</span>' : ''}
                            </div>
                            <div class="server-details">
                                <div><i class="fas fa-user"></i> ${server.user}</div>
                                <div><i class="fas fa-globe"></i> ${server.host}:${server.port}</div>
                            </div>
                            <div class="server-actions">
                                <button class="btn ${currentServer === index ? 'btn-success' : 'btn-primary'}" onclick="connectToServer(${index})" style="flex: 1;">
                                    <i class="fas fa-plug"></i> ${currentServer === index ? 'Подключено' : 'Подключиться'}
                                </button>
                                <button class="btn btn-danger" onclick="removeServer(${index})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        function connectToServer(index) {
            if (currentServer === index) {
                // Уже подключен, можно отключить
                if (confirm('Отключиться от сервера?')) {
                    disconnectFromServer();
                }
                return;
            }
            
            currentServer = index;
            const server = servers[index];
            
            addToTerminal(`\n🔌 Подключение к ${server.name}...`);
            
            fetch('/api/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({server_id: index})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    addToTerminal(`✅ Успешно подключено к ${server.name}\n`);
                    updateConnectionStatus(true);
                    document.getElementById('commandInput').disabled = false;
                    document.getElementById('execBtn').disabled = false;
                    renderServers();
                    saveSession();
                    
                    // Загрузить файлы если открыт файловый менеджер
                    if (document.getElementById('filemanager').classList.contains('active')) {
                        loadFiles('/');
                    }
                } else {
                    addToTerminal(`❌ Ошибка подключения: ${data.error}\n`);
                    currentServer = null;
                }
            });
        }
        
        function disconnectFromServer() {
            fetch('/api/disconnect', {
                method: 'POST'
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    addToTerminal('🔌 Отключено от сервера\n');
                    currentServer = null;
                    updateConnectionStatus(false);
                    document.getElementById('commandInput').disabled = true;
                    document.getElementById('execBtn').disabled = true;
                    renderServers();
                    saveSession();
                }
            });
        }
        
        function removeServer(index) {
            if (!confirm(`Удалить сервер "${servers[index].name}"?`)) {
                return;
            }
            
            if (currentServer === index) {
                disconnectFromServer();
            }
            
            fetch('/api/remove_server', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({server_id: index})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    servers.splice(index, 1);
                    if (currentServer === index) {
                        currentServer = null;
                        updateConnectionStatus(false);
                    }
                    renderServers();
                    updateStats();
                    saveSession();
                } else {
                    alert('Ошибка: ' + data.error);
                }
            });
        }
        
        // Терминал
        function addToTerminal(text) {
            const output = document.getElementById('terminalOutput');
            output.textContent += text;
            const terminal = document.querySelector('.terminal-body');
            terminal.scrollTop = terminal.scrollHeight;
        }
        
        function clearTerminal() {
            document.getElementById('terminalOutput').textContent = '';
        }
        
        function insertCommand(command) {
            document.getElementById('commandInput').value = command;
            document.getElementById('commandInput').focus();
        }
        
        function executeCommand() {
            const input = document.getElementById('commandInput');
            const command = input.value.trim();
            
            if (!command || currentServer === null) return;
            
            addToTerminal(`\n$ ${command}\n`);
            
            fetch('/api/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({command})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    addToTerminal(data.output + '\n');
                    commandsExecuted++;
                    updateStats();
                    saveSession();
                } else {
                    addToTerminal(`❌ Ошибка: ${data.error}\n`);
                }
                input.value = '';
            });
        }
        
        // Файловый менеджер
        function openUploadModal() {
            if (currentServer === null) {
                alert('Сначала подключитесь к серверу');
                return;
            }
            document.getElementById('uploadPath').value = currentPath;
            openModal('uploadModal');
        }
        
        function refreshFiles() {
            if (currentServer === null) {
                alert('Сначала подключитесь к серверу');
                return;
            }
            loadFiles(currentPath);
        }
        
        function loadFiles(path) {
            fetch('/api/list_files', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    currentPath = data.current_path;
                    document.getElementById('currentPath').textContent = currentPath;
                    
                    const files = data.files || [];
                    filesProcessed = files.length;
                    updateStats();
                    
                    const fileList = document.getElementById('fileList');
                    
                    if (files.length === 0) {
                        fileList.innerHTML = '<p style="text-align: center; color: #9ca3af; padding: 40px;">Папка пуста</p>';
                        return;
                    }
                    
                    fileList.innerHTML = `
                        <div class="file-list">
                            ${files.map(file => `
                                <div class="file-item" onclick="handleFileClick('${file.name}', ${file.is_dir})">
                                    <div class="file-icon">
                                        ${file.is_dir ? '<i class="fas fa-folder"></i>' : getFileIcon(file.name)}
                                    </div>
                                    <div class="file-name">${file.name}</div>
                                    ${!file.is_dir ? `<div style="font-size: 0.8rem; color: #6b7280;">${formatFileSize(file.size)}</div>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    `;
                } else {
                    alert('Ошибка: ' + data.error);
                }
            });
        }
        
        function getFileIcon(filename) {
            const ext = filename.split('.').pop().toLowerCase();
            const icons = {
                'txt': 'fa-file-alt',
                'pdf': 'fa-file-pdf',
                'jpg': 'fa-file-image', 'jpeg': 'fa-file-image', 'png': 'fa-file-image', 'gif': 'fa-file-image',
                'zip': 'fa-file-archive', 'rar': 'fa-file-archive', 'tar': 'fa-file-archive', 'gz': 'fa-file-archive',
                'py': 'fa-file-code', 'js': 'fa-file-code', 'html': 'fa-file-code', 'css': 'fa-file-code',
                'json': 'fa-file-code', 'xml': 'fa-file-code', 'sh': 'fa-file-code',
                'mp3': 'fa-file-audio', 'wav': 'fa-file-audio',
                'mp4': 'fa-file-video', 'avi': 'fa-file-video', 'mkv': 'fa-file-video'
            };
            return `<i class="fas ${icons[ext] || 'fa-file'}"></i>`;
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function handleFileClick(filename, isDir) {
            if (isDir) {
                const newPath = currentPath.endsWith('/') ? currentPath + filename : currentPath + '/' + filename;
                loadFiles(newPath);
            } else {
                // Для файла показываем меню действий
                const fullPath = currentPath.endsWith('/') ? currentPath + filename : currentPath + '/' + filename;
                const actions = `
                    <button class="btn btn-primary" onclick="downloadFile('${fullPath}')">
                        <i class="fas fa-download"></i> Скачать
                    </button>
                    <button class="btn btn-danger" onclick="deleteFile('${fullPath}')">
                        <i class="fas fa-trash"></i> Удалить
                    </button>
                `;
                
                alert(`Файл: ${filename}\n\nВыберите действие:\n\n${actions}`);
            }
        }
        
        function goUp() {
            if (currentPath === '/') return;
            const parts = currentPath.split('/').filter(p => p);
            parts.pop();
            const newPath = '/' + parts.join('/');
            loadFiles(newPath || '/');
        }
        
        function createFolder() {
            const name = prompt('Введите имя новой папки:');
            if (name) {
                const path = currentPath.endsWith('/') ? currentPath + name : currentPath + '/' + name;
                fetch('/api/create_folder', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({path})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        loadFiles(currentPath);
                    } else {
                        alert('Ошибка: ' + data.error);
                    }
                });
            }
        }
        
        function uploadFiles() {
            const path = document.getElementById('uploadPath').value;
            const files = document.getElementById('fileUpload').files;
            
            if (files.length === 0) {
                alert('Выберите файлы для загрузки');
                return;
            }
            
            const formData = new FormData();
            formData.append('path', path);
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
            
            fetch('/api/upload_files', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert(`Загружено ${data.uploaded} файлов`);
                    closeModal('uploadModal');
                    loadFiles(currentPath);
                } else {
                    alert('Ошибка: ' + data.error);
                }
            });
        }
        
        function downloadFile(path) {
            window.open(`/api/download_file?path=${encodeURIComponent(path)}`, '_blank');
        }
        
        function deleteFile(path) {
            if (!confirm(`Удалить файл "${path.split('/').pop()}"?`)) return;
            
            fetch('/api/delete_file', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    loadFiles(currentPath);
                } else {
                    alert('Ошибка: ' + data.error);
                }
            });
        }
        
        function deleteSelected() {
            if (selectedFiles.size === 0) return;
            // Реализация удаления выбранных файлов
        }
        
        // Вспомогательные функции
        function updateConnectionStatus(connected) {
            const statusDot = document.querySelector('.status-dot');
            const statusText = document.getElementById('statusText');
            
            if (connected) {
                statusDot.className = 'status-dot status-online';
                statusText.textContent = 'Подключено к серверу';
            } else {
                statusDot.className = 'status-dot status-offline';
                statusText.textContent = 'Сервер не подключен';
            }
        }
        
        function updateStats() {
            document.getElementById('serversCount').textContent = servers.length;
            document.getElementById('activeConnections').textContent = currentServer !== null ? 1 : 0;
            document.getElementById('commandsCount').textContent = commandsExecuted;
            document.getElementById('filesCount').textContent = filesProcessed;
        }
        
        function saveSession() {
            const sessionData = {
                servers: servers,
                currentServer: currentServer,
                commandsExecuted: commandsExecuted,
                filesProcessed: filesProcessed
            };
            localStorage.setItem('ssh_agent_session', JSON.stringify(sessionData));
        }
    </script>
</body>
</html>
"""

# ============ API ENDPOINTS ============
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_TEMPLATE

@app.get("/api/servers")
async def get_servers(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = secrets.token_hex(16)
    
    if session_id not in web_sessions:
        web_sessions[session_id] = {'servers': [], 'current_connection': None, 'sftp': None}
    
    response = JSONResponse(content={'servers': web_sessions[session_id]['servers']})
    response.set_cookie(key="session_id", value=session_id)
    return response

@app.post("/api/servers")
async def add_server(server: Server, request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = secrets.token_hex(16)
    
    if session_id not in web_sessions:
        web_sessions[session_id] = {'servers': [], 'current_connection': None, 'sftp': None}
    
    web_sessions[session_id]['servers'].append(server.dict())
    
    response = JSONResponse(content={'success': True})
    response.set_cookie(key="session_id", value=session_id)
    return response

@app.post("/api/connect")
async def connect_server(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    data = await request.json()
    server_id = data.get('server_id')
    
    if server_id >= len(web_sessions[session_id]['servers']):
        return JSONResponse(content={'success': False, 'error': 'Server not found'})
    
    server = web_sessions[session_id]['servers'][server_id]
    
    try:
        # Закрываем предыдущие соединения
        if web_sessions[session_id]['current_connection']:
            try:
                web_sessions[session_id]['current_connection'].close()
            except:
                pass
        
        if web_sessions[session_id].get('sftp'):
            try:
                web_sessions[session_id]['sftp'].close()
            except:
                pass
        
        # Создаем новое SSH соединение
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=server['host'],
            port=server['port'],
            username=server['user'],
            password=server['password'],
            timeout=10
        )
        
        # Создаем SFTP соединение
        sftp = ssh.open_sftp()
        
        web_sessions[session_id]['current_connection'] = ssh
        web_sessions[session_id]['sftp'] = sftp
        
        return JSONResponse(content={'success': True})
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

@app.post("/api/disconnect")
async def disconnect_server(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    try:
        if web_sessions[session_id].get('sftp'):
            web_sessions[session_id]['sftp'].close()
            web_sessions[session_id]['sftp'] = None
        
        if web_sessions[session_id].get('current_connection'):
            web_sessions[session_id]['current_connection'].close()
            web_sessions[session_id]['current_connection'] = None
        
        return JSONResponse(content={'success': True})
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

@app.post("/api/execute")
async def execute_command(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    data = await request.json()
    command = data.get('command')
    
    if not web_sessions[session_id].get('current_connection'):
        return JSONResponse(content={'success': False, 'error': 'Not connected'})
    
    try:
        ssh = web_sessions[session_id]['current_connection']
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode() + stderr.read().decode()
        return JSONResponse(content={'success': True, 'output': output})
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

@app.post("/api/remove_server")
async def remove_server_api(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    data = await request.json()
    server_id = data.get('server_id')
    
    if server_id >= len(web_sessions[session_id]['servers']):
        return JSONResponse(content={'success': False, 'error': 'Server not found'})
    
    # Если удаляем текущий сервер, закрываем соединения
    if web_sessions[session_id].get('current_connection'):
        try:
            web_sessions[session_id]['current_connection'].close()
        except:
            pass
        web_sessions[session_id]['current_connection'] = None
    
    if web_sessions[session_id].get('sftp'):
        try:
            web_sessions[session_id]['sftp'].close()
        except:
            pass
        web_sessions[session_id]['sftp'] = None
    
    # Удаляем сервер из списка
    web_sessions[session_id]['servers'].pop(server_id)
    
    return JSONResponse(content={'success': True})

# ============ ФАЙЛОВЫЙ МЕНЕДЖЕР API ============
@app.post("/api/list_files")
async def list_files(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    data = await request.json()
    path = data.get('path', '/')
    
    if not web_sessions[session_id].get('sftp'):
        return JSONResponse(content={'success': False, 'error': 'Not connected'})
    
    try:
        sftp = web_sessions[session_id]['sftp']
        
        # Нормализуем путь
        if not path.startswith('/'):
            path = '/' + path
        
        files = []
        for item in sftp.listdir_attr(path):
            is_dir = paramiko.sftp_client.SFTPAttributes._from_dict({'st_mode': item.st_mode}).__str__().startswith('d')
            files.append({
                'name': item.filename,
                'size': item.st_size,
                'is_dir': is_dir
            })
        
        # Сортируем: папки сначала
        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return JSONResponse(content={
            'success': True,
            'files': files,
            'current_path': path
        })
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

@app.post("/api/create_folder")
async def create_folder_api(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    data = await request.json()
    path = data.get('path')
    
    if not web_sessions[session_id].get('sftp'):
        return JSONResponse(content={'success': False, 'error': 'Not connected'})
    
    try:
        sftp = web_sessions[session_id]['sftp']
        sftp.mkdir(path)
        return JSONResponse(content={'success': True})
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

@app.post("/api/upload_files")
async def upload_files_api(
    request: Request,
    path: str = Form(...),
    files: List[UploadFile] = File(...)
):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    if not web_sessions[session_id].get('sftp'):
        return JSONResponse(content={'success': False, 'error': 'Not connected'})
    
    try:
        sftp = web_sessions[session_id]['sftp']
        uploaded = 0
        
        for file in files:
            if file.filename:
                file_path = path.rstrip('/') + '/' + file.filename
                contents = await file.read()
                with sftp.open(file_path, 'wb') as f:
                    f.write(contents)
                uploaded += 1
        
        return JSONResponse(content={'success': True, 'uploaded': uploaded})
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

@app.get("/api/download_file")
async def download_file_api(path: str, request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    if not web_sessions[session_id].get('sftp'):
        return JSONResponse(content={'success': False, 'error': 'Not connected'})
    
    try:
        sftp = web_sessions[session_id]['sftp']
        
        # Читаем файл
        with sftp.open(path, 'rb') as f:
            file_data = f.read()
        
        # Определяем MIME тип
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        filename = path.split('/')[-1]
        
        return StreamingResponse(
            BytesIO(file_data),
            media_type=mime_type,
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

@app.post("/api/delete_file")
async def delete_file_api(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in web_sessions:
        return JSONResponse(content={'success': False, 'error': 'Session not found'})
    
    data = await request.json()
    path = data.get('path')
    
    if not web_sessions[session_id].get('sftp'):
        return JSONResponse(content={'success': False, 'error': 'Not connected'})
    
    try:
        sftp = web_sessions[session_id]['sftp']
        
        # Проверяем, это папка или файл
        try:
            sftp.stat(path)
            # Это файл
            sftp.remove(path)
        except:
            # Это папка
            sftp.rmdir(path)
        
        return JSONResponse(content={'success': True})
    except Exception as e:
        return JSONResponse(content={'success': False, 'error': str(e)})

# ============ TELEGRAM BOT ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Добавить сервер", callback_data='add_server')],
        [InlineKeyboardButton("🌐 Web версия", url="https://sshagen.bothost.ru")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🚀 *SSH Agent Pro*\n\n"
        "Управляйте серверами через SSH!\n\n"
        "Используйте /add для добавления сервера\n"
        "Или откройте веб-версию для полного функционала.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def add_server_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправьте данные сервера в формате:\n\n"
        "`название|хост|порт|пользователь|пароль`\n\n"
        "Пример:\n"
        "`Мой сервер|192.168.1.100|22|root|password123`",
        parse_mode='Markdown'
    )
    context.user_data['awaiting'] = 'server_data'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text
    
    if context.user_data.get('awaiting') == 'server_data':
        try:
            parts = text.split('|')
            if len(parts) != 5:
                await update.message.reply_text("❌ Неверный формат. Используйте: название|хост|порт|пользователь|пароль")
                return
            
            server = {
                'name': parts[0].strip(),
                'host': parts[1].strip(),
                'port': int(parts[2].strip()),
                'user': parts[3].strip(),
                'password': parts[4].strip()
            }
            
            if user_id not in user_sessions:
                user_sessions[user_id] = {'servers': []}
            
            user_sessions[user_id]['servers'].append(server)
            await update.message.reply_text(f"✅ Сервер *{server['name']}* добавлен!", parse_mode='Markdown')
            context.user_data['awaiting'] = None
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    else:
        await update.message.reply_text("Используйте /start для начала работы")

# ============ ЗАПУСК ПРИЛОЖЕНИЯ ============
telegram_app = None

async def start_telegram_bot():
    global telegram_app
    try:
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("add", add_server_cmd))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        
        logger.info("Telegram бот запущен в режиме polling")
        
        # Бесконечный цикл
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"Ошибка запуска Telegram бота: {e}")

def run_telegram_bot():
    asyncio.run(start_telegram_bot())

# Запуск при старте
import threading
bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
