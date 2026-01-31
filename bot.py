import os
import json
import secrets
import asyncio
import threading
import logging
import base64
import mimetypes
from datetime import datetime
from io import StringIO, BytesIO
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, session, send_file
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

# Bothost автоматически устанавливает PORT
PORT = int(os.environ.get("PORT", 3000))

# Определяем домен - используем internal domain от Bothost
HOSTNAME = os.environ.get("HOSTNAME", os.environ.get("INTERNAL_DOMAIN", "f94c91e2287e"))
WEBHOOK_URL = f"https://{HOSTNAME}"

# Используем polling на Bothost
USE_WEBHOOK = False

logger.info(f"=== SSH Agent Pro ===")
logger.info(f"Hostname: {HOSTNAME}")
logger.info(f"Webhook URL: {WEBHOOK_URL}")
logger.info(f"Port: {PORT}")

# ============ ХРАНИЛИЩЕ ДАННЫХ ============
user_sessions = {}  # {user_id: {'servers': [], 'current_connection': None, 'sftp': None}}

# ============ FLASK WEB APPLICATION ============
app = Flask(__name__)
app.secret_key = SECRET_KEY

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
        }
        
        .app-container {
            display: flex;
            min-height: 100vh;
        }
        
        /* Сайдбар */
        .sidebar {
            width: 260px;
            background: var(--sidebar-bg);
            color: white;
            padding: 20px 0;
            box-shadow: 4px 0 10px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
        }
        
        .sidebar-header {
            padding: 0 20px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            text-align: center;
        }
        
        .sidebar-header h1 {
            font-size: 1.5rem;
            margin-bottom: 5px;
            color: var(--primary);
        }
        
        .sidebar-header p {
            font-size: 0.8rem;
            opacity: 0.7;
        }
        
        .nav-section {
            padding: 20px;
        }
        
        .nav-section h3 {
            font-size: 0.9rem;
            text-transform: uppercase;
            color: var(--gray);
            margin-bottom: 15px;
            letter-spacing: 1px;
        }
        
        .nav-item {
            display: flex;
            align-items: center;
            padding: 12px 15px;
            margin-bottom: 8px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            color: var(--gray-light);
        }
        
        .nav-item:hover {
            background: rgba(255,255,255,0.1);
            color: white;
            transform: translateX(5px);
        }
        
        .nav-item.active {
            background: var(--primary);
            color: white;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
        }
        
        .nav-item i {
            margin-right: 10px;
            width: 20px;
            text-align: center;
        }
        
        .server-status {
            margin-top: auto;
            padding: 20px;
            background: rgba(0,0,0,0.2);
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        
        .status-indicator {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 10px;
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
        
        /* Основной контент */
        .main-content {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }
        
        .content-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            background: var(--card-bg);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }
        
        .content-header h2 {
            color: var(--dark);
            font-size: 1.8rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: var(--card-bg);
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        }
        
        .stat-card i {
            font-size: 2rem;
            margin-bottom: 15px;
            color: var(--primary);
        }
        
        .stat-card h3 {
            font-size: 2rem;
            margin-bottom: 5px;
            color: var(--dark);
        }
        
        .stat-card p {
            color: var(--gray);
            font-size: 0.9rem;
        }
        
        /* Терминал */
        .terminal-container {
            background: var(--terminal-bg);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 20px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
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
        
        .terminal-title {
            margin-left: 20px;
            color: var(--gray-light);
            font-family: 'Courier New', monospace;
        }
        
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
        }
        
        .terminal-input-field {
            flex: 1;
            background: transparent;
            border: none;
            color: white;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            outline: none;
        }
        
        /* Файловый менеджер */
        .file-manager {
            background: var(--card-bg);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }
        
        .fm-header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .fm-path {
            font-family: 'Courier New', monospace;
            background: rgba(0,0,0,0.2);
            padding: 8px 15px;
            border-radius: 6px;
            font-size: 14px;
        }
        
        .fm-toolbar {
            display: flex;
            gap: 10px;
            padding: 15px 20px;
            background: var(--light);
            border-bottom: 1px solid var(--gray-light);
        }
        
        .fm-content {
            padding: 20px;
            min-height: 400px;
            max-height: 500px;
            overflow-y: auto;
        }
        
        .file-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 15px;
        }
        
        .file-item {
            background: var(--light);
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
            margin-bottom: 10px;
            color: var(--primary);
        }
        
        .file-name {
            font-size: 0.9rem;
            font-weight: 600;
            margin-bottom: 5px;
            word-break: break-all;
        }
        
        .file-size {
            font-size: 0.8rem;
            color: var(--gray);
        }
        
        /* Кнопки */
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
            background: linear-gradient(135deg, var(--success) 0%, #059669 100%);
            color: white;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #dc2626 100%);
            color: white;
        }
        
        .btn-outline {
            background: transparent;
            border: 2px solid var(--primary);
            color: var(--primary);
        }
        
        /* Модальные окна */
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
            backdrop-filter: blur(5px);
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
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: modalAppear 0.3s ease-out;
        }
        
        @keyframes modalAppear {
            from {
                opacity: 0;
                transform: translateY(-30px) scale(0.9);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--gray-light);
        }
        
        .modal-header h2 {
            color: var(--dark);
        }
        
        .modal-close {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: var(--gray);
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
        
        /* Вкладки */
        .tabs {
            display: flex;
            border-bottom: 2px solid var(--gray-light);
            margin-bottom: 20px;
        }
        
        .tab {
            padding: 12px 24px;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.3s;
            font-weight: 600;
            color: var(--gray);
        }
        
        .tab:hover {
            color: var(--primary);
        }
        
        .tab.active {
            color: var(--primary);
            border-bottom-color: var(--primary);
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        /* Адаптивность */
        @media (max-width: 1024px) {
            .app-container {
                flex-direction: column;
            }
            
            .sidebar {
                width: 100%;
                height: auto;
            }
            
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        
        @media (max-width: 768px) {
            .stats-grid {
                grid-template-columns: 1fr;
            }
            
            .content-header {
                flex-direction: column;
                gap: 15px;
                text-align: center;
            }
            
            .file-list {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        
        /* Утилиты */
        .text-success { color: var(--success); }
        .text-danger { color: var(--danger); }
        .text-warning { color: var(--warning); }
        .text-muted { color: var(--gray); }
        
        .mb-3 { margin-bottom: 15px; }
        .mt-3 { margin-top: 15px; }
        .text-center { text-align: center; }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Сайдбар -->
        <div class="sidebar">
            <div class="sidebar-header">
                <h1><i class="fas fa-terminal"></i> SSH Agent Pro</h1>
                <p>Расширенное управление серверами</p>
            </div>
            
            <div class="nav-section">
                <h3>Основное</h3>
                <div class="nav-item active" onclick="showTab('dashboard')">
                    <i class="fas fa-tachometer-alt"></i> Дашборд
                </div>
                <div class="nav-item" onclick="showTab('servers')">
                    <i class="fas fa-server"></i> Серверы
                </div>
                <div class="nav-item" onclick="showTab('terminal')">
                    <i class="fas fa-terminal"></i> Терминал
                </div>
                <div class="nav-item" onclick="showTab('filemanager')">
                    <i class="fas fa-folder-open"></i> Файловый менеджер
                </div>
            </div>
            
            <div class="nav-section">
                <h3>Инструменты</h3>
                <div class="nav-item" onclick="showTab('monitoring')">
                    <i class="fas fa-chart-line"></i> Мониторинг
                </div>
                <div class="nav-item" onclick="showTab('backup')">
                    <i class="fas fa-database"></i> Бэкапы
                </div>
                <div class="nav-item" onclick="showTab('settings')">
                    <i class="fas fa-cog"></i> Настройки
                </div>
            </div>
            
            <div class="server-status">
                <div class="status-indicator">
                    <span class="status-dot status-offline"></span>
                    <span>Сервер не подключен</span>
                </div>
                <div id="currentServerInfo"></div>
            </div>
        </div>
        
        <!-- Основной контент -->
        <div class="main-content">
            <!-- Дашборд -->
            <div id="dashboard" class="tab-content active">
                <div class="content-header">
                    <h2><i class="fas fa-tachometer-alt"></i> Дашборд</h2>
                    <button class="btn btn-primary" onclick="openAddServerModal()">
                        <i class="fas fa-plus"></i> Добавить сервер
                    </button>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <i class="fas fa-server"></i>
                        <h3 id="serversCount">0</h3>
                        <p>Серверов</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-plug"></i>
                        <h3 id="activeConnections">0</h3>
                        <p>Активных подключений</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-code"></i>
                        <h3 id="commandsCount">0</h3>
                        <p>Выполнено команд</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-hdd"></i>
                        <h3 id="filesCount">0</h3>
                        <p>Обработано файлов</p>
                    </div>
                </div>
                
                <div class="terminal-container mb-3">
                    <div class="terminal-header">
                        <div class="terminal-dots">
                            <div class="terminal-dot red"></div>
                            <div class="terminal-dot yellow"></div>
                            <div class="terminal-dot green"></div>
                        </div>
                        <div class="terminal-title">Быстрый терминал</div>
                    </div>
                    <div class="terminal-body">
                        <div class="terminal-output" id="quickTerminal">
SSH Agent Pro v2.0
Добро пожаловать в расширенную систему управления серверами!

Для начала работы:
1. Добавьте сервер через меню "Серверы"
2. Подключитесь к серверу
3. Используйте терминал или файловый менеджер

Доступные функции:
✓ Управление серверами через SSH
✓ Файловый менеджер с предпросмотром
✓ Мониторинг ресурсов
✓ Создание бэкапов
✓ Управление процессами
                        </div>
                    </div>
                    <div class="terminal-input">
                        <span class="terminal-prompt">$</span>
                        <input type="text" class="terminal-input-field" id="quickCommand" 
                               placeholder="Быстрая команда..." onkeypress="if(event.key=='Enter') executeQuickCommand()">
                    </div>
                </div>
                
                <div class="file-manager">
                    <div class="fm-header">
                        <h3><i class="fas fa-history"></i> Последние действия</h3>
                    </div>
                    <div class="fm-content">
                        <div id="recentActivities"></div>
                    </div>
                </div>
            </div>
            
            <!-- Серверы -->
            <div id="servers" class="tab-content">
                <div class="content-header">
                    <h2><i class="fas fa-server"></i> Управление серверами</h2>
                    <button class="btn btn-primary" onclick="openAddServerModal()">
                        <i class="fas fa-plus"></i> Добавить сервер
                    </button>
                </div>
                
                <div class="file-manager">
                    <div class="fm-toolbar">
                        <button class="btn btn-outline" onclick="testAllServers()">
                            <i class="fas fa-play"></i> Тестировать все
                        </button>
                        <button class="btn btn-danger" onclick="removeAllServers()">
                            <i class="fas fa-trash"></i> Удалить все
                        </button>
                    </div>
                    <div class="fm-content">
                        <div id="serversList"></div>
                    </div>
                </div>
            </div>
            
            <!-- Терминал -->
            <div id="terminal" class="tab-content">
                <div class="content-header">
                    <h2><i class="fas fa-terminal"></i> Расширенный терминал</h2>
                    <div>
                        <button class="btn btn-success" onclick="clearTerminal()">
                            <i class="fas fa-broom"></i> Очистить
                        </button>
                        <button class="btn btn-primary" onclick="saveTerminalLog()">
                            <i class="fas fa-save"></i> Сохранить лог
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
                        <div class="terminal-title" id="terminalTitle">Терминал (не подключено)</div>
                    </div>
                    <div class="terminal-body">
                        <div class="terminal-output" id="terminalOutput"></div>
                    </div>
                    <div class="terminal-input">
                        <span class="terminal-prompt" id="terminalPrompt">$</span>
                        <input type="text" class="terminal-input-field" id="commandInput" 
                               placeholder="Введите команду..." disabled
                               onkeypress="if(event.key=='Enter') executeCommand()">
                        <button class="btn btn-success" onclick="executeCommand()" id="execBtn" disabled>
                            <i class="fas fa-play"></i>
                        </button>
                    </div>
                </div>
                
                <div class="tabs mt-3">
                    <div class="tab active" onclick="showCommandTab('common')">Частые команды</div>
                    <div class="tab" onclick="showCommandTab('system')">Системные</div>
                    <div class="tab" onclick="showCommandTab('network')">Сеть</div>
                    <div class="tab" onclick="showCommandTab('custom')">Мои команды</div>
                </div>
                
                <div id="commonCommands" class="tab-content active mt-3">
                    <div class="command-buttons">
                        <button class="btn btn-outline" onclick="insertCommand('pwd')">pwd</button>
                        <button class="btn btn-outline" onclick="insertCommand('ls -la')">ls -la</button>
                        <button class="btn btn-outline" onclick="insertCommand('df -h')">df -h</button>
                        <button class="btn btn-outline" onclick="insertCommand('free -m')">free -m</button>
                        <button class="btn btn-outline" onclick="insertCommand('top -n 1')">top</button>
                        <button class="btn btn-outline" onclick="insertCommand('whoami')">whoami</button>
                    </div>
                </div>
            </div>
            
            <!-- Файловый менеджер -->
            <div id="filemanager" class="tab-content">
                <div class="content-header">
                    <h2><i class="fas fa-folder-open"></i> Файловый менеджер</h2>
                    <div>
                        <button class="btn btn-primary" onclick="refreshFileManager()">
                            <i class="fas fa-sync"></i> Обновить
                        </button>
                        <button class="btn btn-success" onclick="openUploadModal()">
                            <i class="fas fa-upload"></i> Загрузить
                        </button>
                    </div>
                </div>
                
                <div class="file-manager">
                    <div class="fm-header">
                        <div>
                            <h3><i class="fas fa-folder"></i> <span id="currentPath">/</span></h3>
                            <div class="fm-path" id="breadcrumbs">/</div>
                        </div>
                        <div class="fm-toolbar">
                            <button class="btn btn-outline" onclick="goUp()">
                                <i class="fas fa-level-up-alt"></i> Наверх
                            </button>
                            <button class="btn btn-outline" onclick="createFolder()">
                                <i class="fas fa-folder-plus"></i> Создать папку
                            </button>
                            <button class="btn btn-danger" onclick="deleteSelected()">
                                <i class="fas fa-trash"></i> Удалить
                            </button>
                        </div>
                    </div>
                    
                    <div class="fm-content">
                        <div id="fileManagerLoading" class="text-center">
                            <p>Загрузка файлов...</p>
                        </div>
                        <div id="fileList" class="file-list"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Модальное окно добавления сервера -->
    <div class="modal" id="addServerModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2><i class="fas fa-plus"></i> Добавить SSH сервер</h2>
                <button class="modal-close" onclick="closeAddServerModal()">&times;</button>
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
                <button class="btn btn-danger" onclick="closeAddServerModal()">
                    <i class="fas fa-times"></i> Отмена
                </button>
            </div>
        </div>
    </div>
    
    <!-- Модальное окно редактирования файла -->
    <div class="modal" id="editFileModal">
        <div class="modal-content" style="max-width: 800px;">
            <div class="modal-header">
                <h2><i class="fas fa-edit"></i> Редактирование файла</h2>
                <button class="modal-close" onclick="closeEditFileModal()">&times;</button>
            </div>
            <div class="form-group">
                <label class="form-label">Путь к файлу</label>
                <input type="text" class="form-input" id="editFilePath" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Содержимое</label>
                <textarea class="form-input" id="editFileContent" rows="15" style="font-family: 'Courier New', monospace;"></textarea>
            </div>
            <div class="form-actions">
                <button class="btn btn-success" onclick="saveFile()">
                    <i class="fas fa-save"></i> Сохранить
                </button>
                <button class="btn btn-primary" onclick="downloadFile()">
                    <i class="fas fa-download"></i> Скачать
                </button>
                <button class="btn btn-danger" onclick="closeEditFileModal()">
                    <i class="fas fa-times"></i> Отмена
                </button>
            </div>
        </div>
    </div>
    
    <!-- Модальное окно загрузки файла -->
    <div class="modal" id="uploadModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2><i class="fas fa-upload"></i> Загрузка файла на сервер</h2>
                <button class="modal-close" onclick="closeUploadModal()">&times;</button>
            </div>
            <div class="form-group">
                <label class="form-label">Путь для загрузки</label>
                <input type="text" class="form-input" id="uploadPath" value="/tmp">
            </div>
            <div class="form-group">
                <label class="form-label">Выберите файл</label>
                <input type="file" class="form-input" id="fileUpload" multiple>
            </div>
            <div class="form-actions">
                <button class="btn btn-success" onclick="uploadFiles()">
                    <i class="fas fa-upload"></i> Загрузить
                </button>
                <button class="btn btn-danger" onclick="closeUploadModal()">
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
            loadRecentActivities();
            
            // Автофокус на поле команды
            document.getElementById('commandInput').addEventListener('keydown', function(e) {
                if (e.key === 'Tab') {
                    e.preventDefault();
                    this.value += '    ';
                }
            });
        });
        
        // Навигация по вкладкам
        function showTab(tabName) {
            // Скрыть все вкладки
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Скрыть активный элемент в сайдбаре
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.remove('active');
            });
            
            // Показать выбранную вкладку
            document.getElementById(tabName).classList.add('active');
            
            // Активировать соответствующий элемент в сайдбаре
            document.querySelector(`.nav-item[onclick*="${tabName}"]`).classList.add('active');
            
            // При показе файлового менеджера обновить список файлов
            if (tabName === 'filemanager' && currentServer !== null) {
                loadFileList(currentPath);
            }
        }
        
        function showCommandTab(tabName) {
            // Скрыть все вкладки команд
            document.querySelectorAll('#terminal .tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Убрать active у всех табов
            document.querySelectorAll('#terminal .tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Показать выбранную вкладку
            document.getElementById(tabName + 'Commands').classList.add('active');
            
            // Активировать соответствующий таб
            document.querySelector(`#terminal .tab[onclick*="${tabName}"]`).classList.add('active');
        }
        
        // Серверы
        function loadServers() {
            fetch('/api/servers')
                .then(r => r.json())
                .then(data => {
                    servers = data.servers || [];
                    renderServers();
                    updateStats();
                });
        }
        
        function renderServers() {
            const container = document.getElementById('serversList');
            if (servers.length === 0) {
                container.innerHTML = `
                    <div class="text-center" style="padding: 40px;">
                        <i class="fas fa-server fa-4x text-muted mb-3"></i>
                        <h3>Серверы не добавлены</h3>
                        <p class="text-muted">Добавьте свой первый сервер для начала работы</p>
                        <button class="btn btn-primary" onclick="openAddServerModal()">
                            <i class="fas fa-plus"></i> Добавить сервер
                        </button>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = servers.map((s, i) => `
                <div class="server-item" style="border: 2px solid ${currentServer === i ? '#667eea' : '#e5e7eb'}; background: ${currentServer === i ? '#f0f5ff' : 'white'};">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <div style="font-weight: 600; margin-bottom: 5px; font-size: 1.1rem;">${s.name}</div>
                            <div style="font-size: 0.9em; opacity: 0.7;">
                                <i class="fas fa-user"></i> ${s.user}@
                                <i class="fas fa-globe"></i> ${s.host}:
                                <i class="fas fa-network-wired"></i> ${s.port}
                            </div>
                        </div>
                        <div>
                            <span class="status-dot ${currentServer === i ? 'status-online' : 'status-offline'}"></span>
                        </div>
                    </div>
                    <div style="display: flex; gap: 10px; margin-top: 15px;">
                        <button class="btn btn-success" style="flex: 1;" onclick="connectToServer(${i})">
                            <i class="fas fa-plug"></i> ${currentServer === i ? 'Подключено' : 'Подключиться'}
                        </button>
                        <button class="btn btn-outline" onclick="testServer(${i})">
                            <i class="fas fa-play"></i>
                        </button>
                        <button class="btn btn-danger" onclick="removeServer(${i})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `).join('');
        }
        
        function connectToServer(index) {
            currentServer = index;
            const server = servers[index];
            
            addToTerminal(`\\n🔌 Подключение к ${server.name}...`);
            
            fetch('/api/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({server_id: index})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    addToTerminal(`✅ Подключено к ${server.name}\\n`);
                    document.querySelector('.server-status .status-dot').className = 'status-dot status-online';
                    document.querySelector('.server-status .status-indicator span:last-child').textContent = `Подключено к ${server.name}`;
                    document.getElementById('terminalTitle').textContent = `Терминал (${server.name})`;
                    document.getElementById('commandInput').disabled = false;
                    document.getElementById('execBtn').disabled = false;
                    
                    // Обновить информацию о сервере
                    updateServerInfo(server);
                    renderServers();
                    updateStats();
                    
                    // Загрузить список файлов если открыт файловый менеджер
                    if (document.getElementById('filemanager').classList.contains('active')) {
                        loadFileList('/');
                    }
                    
                    addRecentActivity('Подключение к серверу', `Подключен к ${server.name}`, 'success');
                } else {
                    addToTerminal(`❌ Ошибка: ${data.error}\\n`);
                    addRecentActivity('Ошибка подключения', data.error, 'danger');
                }
            });
        }
        
        function updateServerInfo(server) {
            document.getElementById('currentServerInfo').innerHTML = `
                <div style="margin-top: 10px;">
                    <div><i class="fas fa-server"></i> ${server.name}</div>
                    <div><i class="fas fa-user"></i> ${server.user}</div>
                    <div><i class="fas fa-globe"></i> ${server.host}:${server.port}</div>
                </div>
            `;
        }
        
        function testServer(index) {
            const server = servers[index];
            fetch('/api/test_server', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({server_id: index})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert(`✅ Сервер "${server.name}" доступен!\\nВремя отклика: ${data.ping}ms`);
                } else {
                    alert(`❌ Ошибка: ${data.error}`);
                }
            });
        }
        
        function testAllServers() {
            servers.forEach((server, index) => {
                testServer(index);
            });
        }
        
        function removeServer(index) {
            if (confirm(`Удалить сервер "${servers[index].name}"?`)) {
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
                        document.querySelector('.server-status .status-dot').className = 'status-dot status-offline';
                        document.querySelector('.server-status .status-indicator span:last-child').textContent = 'Сервер не подключен';
                        document.getElementById('commandInput').disabled = true;
                        document.getElementById('execBtn').disabled = true;
                    }
                    renderServers();
                    updateStats();
                    addRecentActivity('Удаление сервера', `Сервер "${data.name}" удален`, 'warning');
                }
            });
            }
        }
        
        function removeAllServers() {
            if (servers.length === 0) return;
            if (confirm(`Удалить все серверы (${servers.length})?`)) {
                fetch('/api/remove_all_servers', {method: 'POST'})
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            servers = [];
                            currentServer = null;
                            renderServers();
                            updateStats();
                            addRecentActivity('Очистка серверов', 'Все серверы удалены', 'danger');
                        }
                    });
            }
        }
        
        // Модальные окна
        function openAddServerModal() {
            document.getElementById('addServerModal').classList.add('active');
        }
        
        function closeAddServerModal() {
            document.getElementById('addServerModal').classList.remove('active');
            // Очистить форму
            document.getElementById('serverName').value = '';
            document.getElementById('serverHost').value = '';
            document.getElementById('serverPort').value = '22';
            document.getElementById('serverUser').value = '';
            document.getElementById('serverPassword').value = '';
        }
        
        function addServer() {
            const server = {
                name: document.getElementById('serverName').value,
                host: document.getElementById('serverHost').value,
                port: document.getElementById('serverPort').value,
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
                    closeAddServerModal();
                    loadServers();
                    addRecentActivity('Добавление сервера', `Сервер "${server.name}" добавлен`, 'success');
                }
            });
        }
        
        // Терминал
        function addToTerminal(text) {
            const output = document.getElementById('terminalOutput');
            output.textContent += '\\n' + text;
            const terminal = document.querySelector('#terminal .terminal-body');
            terminal.scrollTop = terminal.scrollHeight;
        }
        
        function executeCommand() {
            const input = document.getElementById('commandInput');
            const command = input.value.trim();
            
            if (!command) return;
            
            addToTerminal(`\\n$ ${command}`);
            input.value = '';
            
            fetch('/api/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({command})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    addToTerminal(data.output || '(пусто)');
                    commandsExecuted++;
                    updateStats();
                    addRecentActivity('Выполнение команды', command, 'primary');
                } else {
                    addToTerminal(`❌ Ошибка: ${data.error}`);
                }
            });
        }
        
        function executeQuickCommand() {
            const input = document.getElementById('quickCommand');
            const command = input.value.trim();
            
            if (!command) return;
            
            if (currentServer === null) {
                alert('Сначала подключитесь к серверу');
                return;
            }
            
            fetch('/api/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({command})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    addToTerminal(`\\n$ ${command}\\n${data.output || '(пусто)'}`);
                    commandsExecuted++;
                    updateStats();
                }
            });
            
            input.value = '';
        }
        
        function insertCommand(command) {
            document.getElementById('commandInput').value = command;
            document.getElementById('commandInput').focus();
        }
        
        function clearTerminal() {
            document.getElementById('terminalOutput').textContent = '';
        }
        
        function saveTerminalLog() {
            const content = document.getElementById('terminalOutput').textContent;
            const blob = new Blob([content], {type: 'text/plain'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `terminal_log_${new Date().toISOString().slice(0,10)}.txt`;
            a.click();
            URL.revokeObjectURL(url);
            addRecentActivity('Сохранение лога', 'Терминальный лог сохранен', 'success');
        }
        
        // Файловый менеджер
        function loadFileList(path) {
            if (currentServer === null) {
                document.getElementById('fileList').innerHTML = `
                    <div class="text-center" style="padding: 40px; width: 100%;">
                        <i class="fas fa-server fa-4x text-muted mb-3"></i>
                        <h3>Сервер не подключен</h3>
                        <p class="text-muted">Подключитесь к серверу для работы с файлами</p>
                    </div>
                `;
                return;
            }
            
            document.getElementById('fileManagerLoading').style.display = 'block';
            document.getElementById('fileList').innerHTML = '';
            
            fetch('/api/list_files', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path: path})
            })
            .then(r => r.json())
            .then(data => {
                document.getElementById('fileManagerLoading').style.display = 'none';
                
                if (data.success) {
                    currentPath = data.current_path;
                    document.getElementById('currentPath').textContent = currentPath;
                    updateBreadcrumbs();
                    
                    const files = data.files || [];
                    filesProcessed += files.length;
                    
                    if (files.length === 0) {
                        document.getElementById('fileList').innerHTML = `
                            <div class="text-center" style="padding: 40px; width: 100%;">
                                <i class="fas fa-folder-open fa-4x text-muted mb-3"></i>
                                <h3>Папка пуста</h3>
                                <p class="text-muted">Добавьте файлы или создайте новую папку</p>
                            </div>
                        `;
                        return;
                    }
                    
                    document.getElementById('fileList').innerHTML = files.map(file => `
                        <div class="file-item" onclick="handleFileClick('${file.name}', ${file.is_dir}, '${file.permissions}')">
                            <div class="file-icon">
                                ${file.is_dir ? '<i class="fas fa-folder"></i>' : getFileIcon(file.name)}
                            </div>
                            <div class="file-name">${file.name}</div>
                            ${!file.is_dir ? `<div class="file-size">${formatFileSize(file.size)}</div>` : ''}
                            <div style="font-size: 0.8rem; color: #6b7280; margin-top: 5px;">
                                ${file.permissions}
                            </div>
                        </div>
                    `).join('');
                    
                    updateStats();
                } else {
                    document.getElementById('fileList').innerHTML = `
                        <div class="text-center text-danger" style="padding: 40px;">
                            <i class="fas fa-exclamation-triangle fa-3x mb-3"></i>
                            <h3>Ошибка</h3>
                            <p>${data.error}</p>
                        </div>
                    `;
                }
            });
        }
        
        function getFileIcon(filename) {
            const ext = filename.split('.').pop().toLowerCase();
            const icons = {
                'txt': 'fa-file-alt',
                'pdf': 'fa-file-pdf',
                'jpg': 'fa-file-image',
                'jpeg': 'fa-file-image',
                'png': 'fa-file-image',
                'gif': 'fa-file-image',
                'zip': 'fa-file-archive',
                'rar': 'fa-file-archive',
                'tar': 'fa-file-archive',
                'gz': 'fa-file-archive',
                'py': 'fa-file-code',
                'js': 'fa-file-code',
                'html': 'fa-file-code',
                'css': 'fa-file-code',
                'json': 'fa-file-code',
                'xml': 'fa-file-code',
                'sql': 'fa-file-code',
                'sh': 'fa-file-code',
                'mp3': 'fa-file-audio',
                'mp4': 'fa-file-video',
                'avi': 'fa-file-video',
                'mkv': 'fa-file-video'
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
        
        function updateBreadcrumbs() {
            const parts = currentPath.split('/').filter(p => p);
            let breadcrumbs = '<span onclick="loadFileList(\'/\')">/</span>';
            let current = '';
            
            parts.forEach((part, index) => {
                current += '/' + part;
                breadcrumbs += ` / <span onclick="loadFileList('${current}')">${part}</span>`;
            });
            
            document.getElementById('breadcrumbs').innerHTML = breadcrumbs;
        }
        
        function handleFileClick(filename, isDir, permissions) {
            const fullPath = currentPath.endsWith('/') ? currentPath + filename : currentPath + '/' + filename;
            
            if (isDir) {
                loadFileList(fullPath);
            } else {
                // Показать меню для файла
                const actions = [
                    {icon: 'fa-edit', text: 'Редактировать', action: `editFile('${fullPath}')`},
                    {icon: 'fa-download', text: 'Скачать', action: `downloadFileDirect('${fullPath}')`},
                    {icon: 'fa-trash', text: 'Удалить', action: `deleteFile('${fullPath}')`},
                    {icon: 'fa-copy', text: 'Копировать путь', action: `copyToClipboard('${fullPath}')`}
                ];
                
                const menuHtml = actions.map(a => `
                    <div class="nav-item" onclick="${a.action}">
                        <i class="fas ${a.icon}"></i> ${a.text}
                    </div>
                `).join('');
                
                // Создать временное модальное окно
                const modal = document.createElement('div');
                modal.className = 'modal active';
                modal.innerHTML = `
                    <div class="modal-content">
                        <div class="modal-header">
                            <h2><i class="fas fa-file"></i> ${filename}</h2>
                            <button class="modal-close" onclick="this.parentElement.parentElement.remove()">&times;</button>
                        </div>
                        <div class="mb-3">
                            <p><strong>Путь:</strong> ${fullPath}</p>
                            <p><strong>Права:</strong> ${permissions}</p>
                        </div>
                        <div class="nav-section">
                            ${menuHtml}
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
            }
        }
        
        function editFile(path) {
            fetch('/api/get_file', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path: path})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('editFilePath').value = path;
                    document.getElementById('editFileContent').value = data.content;
                    document.getElementById('editFileModal').classList.add('active');
                    // Закрыть предыдущее модальное окно
                    document.querySelectorAll('.modal').forEach(m => {
                        if (m.id !== 'editFileModal') m.remove();
                    });
                } else {
                    alert(`Ошибка: ${data.error}`);
                }
            });
        }
        
        function closeEditFileModal() {
            document.getElementById('editFileModal').classList.remove('active');
        }
        
        function saveFile() {
            const path = document.getElementById('editFilePath').value;
            const content = document.getElementById('editFileContent').value;
            
            fetch('/api/save_file', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path: path, content: content})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert('Файл успешно сохранен');
                    closeEditFileModal();
                    addRecentActivity('Сохранение файла', path, 'success');
                } else {
                    alert(`Ошибка: ${data.error}`);
                }
            });
        }
        
        function downloadFileDirect(path) {
            window.open(`/api/download_file?path=${encodeURIComponent(path)}`, '_blank');
            addRecentActivity('Скачивание файла', path, 'primary');
        }
        
        function deleteFile(path) {
            if (confirm(`Удалить файл "${path.split('/').pop()}"?`)) {
                fetch('/api/delete_file', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({path: path})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        loadFileList(currentPath);
                        addRecentActivity('Удаление файла', path, 'danger');
                    } else {
                        alert(`Ошибка: ${data.error}`);
                    }
                });
            }
        }
        
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                alert('Путь скопирован в буфер обмена');
            });
        }
        
        function goUp() {
            if (currentPath === '/') return;
            const parts = currentPath.split('/').filter(p => p);
            parts.pop();
            const newPath = '/' + parts.join('/');
            loadFileList(newPath || '/');
        }
        
        function createFolder() {
            const name = prompt('Введите имя новой папки:');
            if (name) {
                const path = currentPath.endsWith('/') ? currentPath + name : currentPath + '/' + name;
                fetch('/api/create_folder', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({path: path})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        loadFileList(currentPath);
                        addRecentActivity('Создание папки', path, 'success');
                    } else {
                        alert(`Ошибка: ${data.error}`);
                    }
                });
            }
        }
        
        function refreshFileManager() {
            loadFileList(currentPath);
        }
        
        function openUploadModal() {
            document.getElementById('uploadPath').value = currentPath;
            document.getElementById('uploadModal').classList.add('active');
        }
        
        function closeUploadModal() {
            document.getElementById('uploadModal').classList.remove('active');
            document.getElementById('fileUpload').value = '';
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
                    closeUploadModal();
                    loadFileList(currentPath);
                    addRecentActivity('Загрузка файлов', `Загружено ${data.uploaded} файлов в ${path}`, 'success');
                } else {
                    alert(`Ошибка: ${data.error}`);
                }
            });
        }
        
        function deleteSelected() {
            // Реализация выбора файлов (упрощенная)
            alert('Для удаления файлов используйте меню файла (клик по файлу)');
        }
        
        // Статистика
        function updateStats() {
            document.getElementById('serversCount').textContent = servers.length;
            document.getElementById('activeConnections').textContent = currentServer !== null ? 1 : 0;
            document.getElementById('commandsCount').textContent = commandsExecuted;
            document.getElementById('filesCount').textContent = filesProcessed;
        }
        
        // Последние действия
        function loadRecentActivities() {
            const activities = JSON.parse(localStorage.getItem('ssh_agent_activities') || '[]');
            const container = document.getElementById('recentActivities');
            
            if (activities.length === 0) {
                container.innerHTML = '<p class="text-muted text-center">Нет последних действий</p>';
                return;
            }
            
            container.innerHTML = activities.slice(0, 10).map(act => `
                <div style="padding: 10px; border-bottom: 1px solid #e5e7eb;">
                    <div style="display: flex; justify-content: space-between;">
                        <strong>${act.title}</strong>
                        <span style="color: ${getStatusColor(act.status)};">
                            <i class="fas fa-circle" style="font-size: 8px;"></i>
                        </span>
                    </div>
                    <div style="color: #6b7280; font-size: 0.9rem;">${act.description}</div>
                    <div style="color: #9ca3af; font-size: 0.8rem;">${new Date(act.timestamp).toLocaleString()}</div>
                </div>
            `).join('');
        }
        
        function addRecentActivity(title, description, status) {
            const activities = JSON.parse(localStorage.getItem('ssh_agent_activities') || '[]');
            activities.unshift({
                title,
                description,
                status,
                timestamp: new Date().toISOString()
            });
            
            // Храним только последние 50 действий
            if (activities.length > 50) {
                activities.pop();
            }
            
            localStorage.setItem('ssh_agent_activities', JSON.stringify(activities));
            loadRecentActivities();
        }
        
        function getStatusColor(status) {
            const colors = {
                'success': '#10b981',
                'danger': '#ef4444',
                'warning': '#f59e0b',
                'primary': '#667eea',
                'info': '#3b82f6'
            };
            return colors[status] || '#6b7280';
        }
    </script>
</body>
</html>
"""

# ============ FLASK ROUTES ============
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/servers', methods=['GET', 'POST'])
def servers_api():
    session_id = session.get('session_id', 'default')
    
    if session_id not in user_sessions:
        user_sessions[session_id] = {'servers': [], 'current_connection': None, 'sftp': None}
    
    if request.method == 'POST':
        server = request.json
        user_sessions[session_id]['servers'].append(server)
        return jsonify({'success': True})
    
    return jsonify({'servers': user_sessions[session_id]['servers']})

@app.route('/api/connect', methods=['POST'])
def connect_api():
    session_id = session.get('session_id', 'default')
    server_id = request.json.get('server_id')
    
    if session_id not in user_sessions:
        return jsonify({'success': False, 'error': 'Session not found'})
    
    if server_id >= len(user_sessions[session_id]['servers']):
        return jsonify({'success': False, 'error': 'Server not found'})
    
    server = user_sessions[session_id]['servers'][server_id]
    
    try:
        # Закрываем предыдущее соединение если есть
        if user_sessions[session_id]['current_connection']:
            try:
                user_sessions[session_id]['current_connection'].close()
            except:
                pass
        
        if user_sessions[session_id].get('sftp'):
            try:
                user_sessions[session_id]['sftp'].close()
            except:
                pass
        
        # SSH соединение
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=server['host'],
            port=int(server['port']),
            username=server['user'],
            password=server['password'],
            timeout=10
        )
        
        # SFTP соединение
        sftp = ssh.open_sftp()
        
        user_sessions[session_id]['current_connection'] = ssh
        user_sessions[session_id]['sftp'] = sftp
        user_sessions[session_id]['current_server'] = server_id
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/execute', methods=['POST'])
def execute_api():
    session_id = session.get('session_id', 'default')
    command = request.json.get('command')
    
    if session_id not in user_sessions or not user_sessions[session_id]['current_connection']:
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        ssh = user_sessions[session_id]['current_connection']
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode() + stderr.read().decode()
        return jsonify({'success': True, 'output': output})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test_server', methods=['POST'])
def test_server_api():
    session_id = session.get('session_id', 'default')
    server_id = request.json.get('server_id')
    
    if session_id not in user_sessions:
        return jsonify({'success': False, 'error': 'Session not found'})
    
    if server_id >= len(user_sessions[session_id]['servers']):
        return jsonify({'success': False, 'error': 'Server not found'})
    
    server = user_sessions[session_id]['servers'][server_id]
    
    try:
        import time
        start_time = time.time()
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=server['host'],
            port=int(server['port']),
            username=server['user'],
            password=server['password'],
            timeout=5
        )
        ssh.close()
        
        ping_time = int((time.time() - start_time) * 1000)
        return jsonify({'success': True, 'ping': ping_time})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove_server', methods=['POST'])
def remove_server_api():
    session_id = session.get('session_id', 'default')
    server_id = request.json.get('server_id')
    
    if session_id not in user_sessions:
        return jsonify({'success': False, 'error': 'Session not found'})
    
    if server_id >= len(user_sessions[session_id]['servers']):
        return jsonify({'success': False, 'error': 'Server not found'})
    
    server = user_sessions[session_id]['servers'][server_id]
    del user_sessions[session_id]['servers'][server_id]
    
    # Если удаляем текущий сервер
    if user_sessions[session_id].get('current_server') == server_id:
        if user_sessions[session_id].get('sftp'):
            try:
                user_sessions[session_id]['sftp'].close()
            except:
                pass
        if user_sessions[session_id].get('current_connection'):
            try:
                user_sessions[session_id]['current_connection'].close()
            except:
                pass
        user_sessions[session_id]['current_connection'] = None
        user_sessions[session_id]['sftp'] = None
        user_sessions[session_id]['current_server'] = None
    
    return jsonify({'success': True, 'name': server['name']})

@app.route('/api/remove_all_servers', methods=['POST'])
def remove_all_servers_api():
    session_id = session.get('session_id', 'default')
    
    if session_id not in user_sessions:
        return jsonify({'success': False, 'error': 'Session not found'})
    
    # Закрываем соединения
    if user_sessions[session_id].get('sftp'):
        try:
            user_sessions[session_id]['sftp'].close()
        except:
            pass
    if user_sessions[session_id].get('current_connection'):
        try:
            user_sessions[session_id]['current_connection'].close()
        except:
            pass
    
    # Очищаем серверы
    user_sessions[session_id]['servers'] = []
    user_sessions[session_id]['current_connection'] = None
    user_sessions[session_id]['sftp'] = None
    user_sessions[session_id]['current_server'] = None
    
    return jsonify({'success': True})

# ============ ФАЙЛОВЫЙ МЕНЕДЖЕР API ============
@app.route('/api/list_files', methods=['POST'])
def list_files_api():
    session_id = session.get('session_id', 'default')
    path = request.json.get('path', '/')
    
    if session_id not in user_sessions or not user_sessions[session_id].get('sftp'):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        sftp = user_sessions[session_id]['sftp']
        
        # Нормализуем путь
        if not path.startswith('/'):
            path = '/' + path
        
        files = []
        for item in sftp.listdir_attr(path):
            files.append({
                'name': item.filename,
                'size': item.st_size,
                'permissions': paramiko.sftp_client.SFTPAttributes._from_dict({'st_mode': item.st_mode}).__str__(),
                'is_dir': paramiko.sftp_client.SFTPAttributes._from_dict({'st_mode': item.st_mode}).__str__().startswith('d')
            })
        
        # Сортируем: сначала папки, потом файлы
        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return jsonify({
            'success': True,
            'files': files,
            'current_path': path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get_file', methods=['POST'])
def get_file_api():
    session_id = session.get('session_id', 'default')
    path = request.json.get('path')
    
    if session_id not in user_sessions or not user_sessions[session_id].get('sftp'):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        sftp = user_sessions[session_id]['sftp']
        
        # Проверяем размер файла (не более 5MB)
        file_attr = sftp.stat(path)
        if file_attr.st_size > 5 * 1024 * 1024:
            return jsonify({'success': False, 'error': 'File too large (max 5MB)'})
        
        # Читаем файл
        with sftp.open(path, 'r') as f:
            content = f.read().decode('utf-8', errors='ignore')
        
        return jsonify({'success': True, 'content': content})
    except UnicodeDecodeError:
        return jsonify({'success': False, 'error': 'File is not text (binary)'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/save_file', methods=['POST'])
def save_file_api():
    session_id = session.get('session_id', 'default')
    path = request.json.get('path')
    content = request.json.get('content')
    
    if session_id not in user_sessions or not user_sessions[session_id].get('sftp'):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        sftp = user_sessions[session_id]['sftp']
        
        # Создаем бекап
        backup_path = path + '.bak'
        try:
            sftp.rename(path, backup_path)
        except:
            pass
        
        # Сохраняем файл
        with sftp.open(path, 'w') as f:
            f.write(content)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download_file', methods=['GET'])
def download_file_api():
    session_id = session.get('session_id', 'default')
    path = request.args.get('path')
    
    if session_id not in user_sessions or not user_sessions[session_id].get('sftp'):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        sftp = user_sessions[session_id]['sftp']
        
        # Читаем файл
        with sftp.open(path, 'rb') as f:
            file_data = f.read()
        
        # Определяем MIME тип
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        filename = path.split('/')[-1]
        
        return send_file(
            BytesIO(file_data),
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete_file', methods=['POST'])
def delete_file_api():
    session_id = session.get('session_id', 'default')
    path = request.json.get('path')
    
    if session_id not in user_sessions or not user_sessions[session_id].get('sftp'):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        sftp = user_sessions[session_id]['sftp']
        
        # Проверяем, это папка или файл
        file_attr = sftp.stat(path)
        if paramiko.sftp_client.SFTPAttributes._from_dict({'st_mode': file_attr.st_mode}).__str__().startswith('d'):
            sftp.rmdir(path)
        else:
            sftp.remove(path)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/create_folder', methods=['POST'])
def create_folder_api():
    session_id = session.get('session_id', 'default')
    path = request.json.get('path')
    
    if session_id not in user_sessions or not user_sessions[session_id].get('sftp'):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        sftp = user_sessions[session_id]['sftp']
        sftp.mkdir(path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/upload_files', methods=['POST'])
def upload_files_api():
    session_id = session.get('session_id', 'default')
    
    if session_id not in user_sessions or not user_sessions[session_id].get('sftp'):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    try:
        path = request.form.get('path', '/')
        files = request.files.getlist('files')
        sftp = user_sessions[session_id]['sftp']
        
        uploaded = 0
        for file in files:
            if file.filename:
                file_path = path.rstrip('/') + '/' + file.filename
                with sftp.open(file_path, 'wb') as f:
                    f.write(file.read())
                uploaded += 1
        
        return jsonify({'success': True, 'uploaded': uploaded})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.before_request
def before_request():
    if 'session_id' not in session:
        session['session_id'] = secrets.token_hex(16)

# ============ TELEGRAM BOT (упрощенная версия) ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Добавить сервер", callback_data='add_server')],
        [InlineKeyboardButton("📋 Список серверов", callback_data='list_servers')],
        [InlineKeyboardButton("🌐 Открыть Web версию", url="https://sshagen.bothost.ru")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🚀 *SSH Agent Pro*\n\n"
        "Расширенное управление серверами через SSH!\n\n"
        "Функции:\n"
        "✓ Терминал\n"
        "✓ Файловый менеджер\n"
        "✓ Мониторинг\n"
        "✓ Управление процессами\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == 'add_server':
        await query.message.reply_text(
            "Отправьте данные сервера в формате:\n\n"
            "`название|хост|порт|пользователь|пароль`\n\n"
            "Пример:\n"
            "`Мой сервер|192.168.1.100|22|root|password123`",
            parse_mode='Markdown'
        )
        context.user_data['awaiting'] = 'server_data'
    
    elif query.data == 'list_servers':
        if user_id not in user_sessions or not user_sessions[user_id].get('servers'):
            await query.message.reply_text("📋 У вас пока нет серверов")
            return
        
        servers = user_sessions[user_id]['servers']
        text = "*Ваши серверы:*\n\n"
        for i, srv in enumerate(servers):
            status = "🟢" if user_sessions[user_id].get('current_server') == i else "⚪"
            text += f"{status} *{srv['name']}*\n"
            text += f"  `{srv['user']}@{srv['host']}:{srv['port']}`\n\n"
        
        await query.message.reply_text(text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text
    
    if context.user_data.get('awaiting') == 'server_data':
        try:
            parts = text.split('|')
            if len(parts) != 5:
                await update.message.reply_text("❌ Неверный формат. Попробуйте снова.")
                return
            
            server = {
                'name': parts[0].strip(),
                'host': parts[1].strip(),
                'port': parts[2].strip(),
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
    
    elif user_id in user_sessions and user_sessions[user_id].get('current_connection'):
        try:
            ssh = user_sessions[user_id]['current_connection']
            stdin, stdout, stderr = ssh.exec_command(text)
            output = stdout.read().decode() + stderr.read().decode()
            
            if len(output) > 3000:
                output = output[:3000] + "\n... (вывод обрезан)"
            
            if output:
                await update.message.reply_text(f"```\n{output}\n```", parse_mode='Markdown')
            else:
                await update.message.reply_text("✅ Команда выполнена")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    else:
        await update.message.reply_text("Используйте /start для начала работы")

# ============ ЗАПУСК ТЕЛЕГРАМ БОТА ============
telegram_app = None

async def start_telegram_bot():
    global telegram_app
    try:
        logger.info("Запуск Telegram бота...")
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CallbackQueryHandler(button_callback))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        
        logger.info("Telegram бот запущен")
        
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")

def run_telegram_bot_thread():
    asyncio.run(start_telegram_bot())

# ============ ОСНОВНОЙ ЗАПУСК ============
def main():
    logger.info("=== SSH Agent Pro запущен ===")
    
    # Запускаем Telegram бот в отдельном потоке
    bot_thread = threading.Thread(target=run_telegram_bot_thread, daemon=True)
    bot_thread.start()
    
    logger.info(f"Flask приложение готово на порту {PORT}")

if __name__ == '__main__':
    main()
    # Flask запускается через gunicorn
