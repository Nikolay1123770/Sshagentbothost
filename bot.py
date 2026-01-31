import os
import json
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import paramiko
import io
import asyncio

# ============ КОНФИГУРАЦИЯ ============
BOT_TOKEN = "8360387336:AAGKU0Jv3CeJ-WubZH6VCPsL4-NDlrcbxp4"  # Токен бота от @BotFather
WEBHOOK_URL = "https://sshagen.bothost.ru"
PORT = int(os.environ.get("PORT", 8080))
SECRET_KEY = secrets.token_urlsafe(32)  # 43-символьный URL-безопасный

# ============ ХРАНИЛИЩЕ ДАННЫХ ============
user_sessions = {}  # {user_id: {'servers': [], 'current_connection': None}}

# ============ FLASK WEB APPLICATION ============
app = Flask(__name__)
app.secret_key = SECRET_KEY

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SSH Agent - Удалённое управление серверами</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }
        
        .header h1 {
            font-size: 3em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
        .main-content {
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        
        .servers-list {
            max-height: 600px;
            overflow-y: auto;
        }
        
        .server-item {
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .server-item:hover {
            border-color: #667eea;
            background: #f5f7ff;
            transform: translateX(5px);
        }
        
        .server-item.active {
            border-color: #667eea;
            background: #667eea;
            color: white;
        }
        
        .terminal {
            background: #1e1e1e;
            color: #00ff00;
            font-family: 'Courier New', monospace;
            padding: 20px;
            border-radius: 10px;
            height: 400px;
            overflow-y: auto;
            margin-bottom: 15px;
        }
        
        .terminal-output {
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .input-group {
            margin-bottom: 15px;
        }
        
        .input-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #333;
        }
        
        .input-group input, .input-group textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border 0.3s;
        }
        
        .input-group input:focus, .input-group textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
            font-weight: 600;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        .btn-danger {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        .btn-success {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        
        .command-input-group {
            display: flex;
            gap: 10px;
        }
        
        .command-input-group input {
            flex: 1;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 20px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-card h3 {
            font-size: 2em;
            margin-bottom: 5px;
        }
        
        .stat-card p {
            opacity: 0.9;
        }
        
        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            
            .stats {
                grid-template-columns: 1fr;
            }
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 15px;
            max-width: 500px;
            width: 90%;
        }
        
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-online {
            background: #00ff00;
            box-shadow: 0 0 5px #00ff00;
        }
        
        .status-offline {
            background: #ff0000;
            box-shadow: 0 0 5px #ff0000;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ SSH Agent</h1>
            <p>Профессиональное управление SSH серверами</p>
        </div>
        
        <div class="main-content">
            <div class="card servers-list">
                <h2>📋 Серверы</h2>
                <button onclick="openAddServerModal()" style="width: 100%; margin: 15px 0;">+ Добавить сервер</button>
                <div id="serversList"></div>
            </div>
            
            <div class="card">
                <h2>💻 Терминал</h2>
                <div id="connectionStatus" style="margin-bottom: 15px;">
                    <span class="status-indicator status-offline"></span>
                    <span>Не подключено</span>
                </div>
                <div class="terminal" id="terminal">
                    <div class="terminal-output" id="terminalOutput">
SSH Agent v1.0
Выберите сервер для подключения...
                    </div>
                </div>
                <div class="command-input-group">
                    <input type="text" id="commandInput" placeholder="Введите команду..." disabled>
                    <button onclick="executeCommand()" class="btn-success" id="execBtn" disabled>Выполнить</button>
                </div>
            </div>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <h3 id="serversCount">0</h3>
                <p>Серверов</p>
            </div>
            <div class="stat-card">
                <h3 id="activeConnections">0</h3>
                <p>Активных подключений</p>
            </div>
            <div class="stat-card">
                <h3 id="commandsCount">0</h3>
                <p>Выполнено команд</p>
            </div>
        </div>
    </div>
    
    <!-- Модальное окно добавления сервера -->
    <div class="modal" id="addServerModal">
        <div class="modal-content">
            <h2>Добавить SSH сервер</h2>
            <div class="input-group">
                <label>Название</label>
                <input type="text" id="serverName" placeholder="Мой сервер">
            </div>
            <div class="input-group">
                <label>Хост</label>
                <input type="text" id="serverHost" placeholder="192.168.1.100">
            </div>
            <div class="input-group">
                <label>Порт</label>
                <input type="number" id="serverPort" value="22">
            </div>
            <div class="input-group">
                <label>Пользователь</label>
                <input type="text" id="serverUser" placeholder="root">
            </div>
            <div class="input-group">
                <label>Пароль</label>
                <input type="password" id="serverPassword">
            </div>
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <button onclick="addServer()" class="btn-success">Добавить</button>
                <button onclick="closeAddServerModal()" class="btn-danger">Отмена</button>
            </div>
        </div>
    </div>

    <script>
        let currentServer = null;
        let servers = [];
        let commandsExecuted = 0;
        
        // Загрузка серверов
        function loadServers() {
            fetch('/api/servers')
                .then(r => r.json())
                .then(data => {
                    servers = data.servers || [];
                    renderServers();
                    updateStats();
                });
        }
        
        // Отрисовка списка серверов
        function renderServers() {
            const container = document.getElementById('serversList');
            if (servers.length === 0) {
                container.innerHTML = '<p style="text-align: center; color: #999; margin-top: 20px;">Нет серверов</p>';
                return;
            }
            
            container.innerHTML = servers.map((s, i) => `
                <div class="server-item ${currentServer === i ? 'active' : ''}" onclick="connectToServer(${i})">
                    <div style="font-weight: 600; margin-bottom: 5px;">${s.name}</div>
                    <div style="font-size: 0.9em; opacity: 0.7;">${s.user}@${s.host}:${s.port}</div>
                </div>
            `).join('');
        }
        
        // Подключение к серверу
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
                    document.getElementById('connectionStatus').innerHTML = `
                        <span class="status-indicator status-online"></span>
                        <span>Подключено к ${server.name}</span>
                    `;
                    document.getElementById('commandInput').disabled = false;
                    document.getElementById('execBtn').disabled = false;
                    updateStats();
                } else {
                    addToTerminal(`❌ Ошибка: ${data.error}\\n`);
                }
                renderServers();
            });
        }
        
        // Выполнение команды
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
                } else {
                    addToTerminal(`❌ Ошибка: ${data.error}`);
                }
            });
        }
        
        // Добавление в терминал
        function addToTerminal(text) {
            const output = document.getElementById('terminalOutput');
            output.textContent += '\\n' + text;
            document.getElementById('terminal').scrollTop = document.getElementById('terminal').scrollHeight;
        }
        
        // Модальное окно
        function openAddServerModal() {
            document.getElementById('addServerModal').classList.add('active');
        }
        
        function closeAddServerModal() {
            document.getElementById('addServerModal').classList.remove('active');
        }
        
        // Добавление сервера
        function addServer() {
            const server = {
                name: document.getElementById('serverName').value,
                host: document.getElementById('serverHost').value,
                port: document.getElementById('serverPort').value,
                user: document.getElementById('serverUser').value,
                password: document.getElementById('serverPassword').value
            };
            
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
                    addToTerminal(`\\n✅ Сервер "${server.name}" добавлен`);
                }
            });
        }
        
        // Обновление статистики
        function updateStats() {
            document.getElementById('serversCount').textContent = servers.length;
            document.getElementById('activeConnections').textContent = currentServer !== null ? 1 : 0;
            document.getElementById('commandsCount').textContent = commandsExecuted;
        }
        
        // Enter для выполнения команды
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('commandInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') executeCommand();
            });
            loadServers();
        });
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
        user_sessions[session_id] = {'servers': [], 'current_connection': None}
    
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
    
    server = user_sessions[session_id]['servers'][server_id]
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=server['host'],
            port=int(server['port']),
            username=server['user'],
            password=server['password'],
            timeout=10
        )
        user_sessions[session_id]['current_connection'] = ssh
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

@app.before_request
def before_request():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()

# ============ TELEGRAM BOT ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Добавить сервер", callback_data='add_server')],
        [InlineKeyboardButton("📋 Список серверов", callback_data='list_servers')],
        [InlineKeyboardButton("🌐 Открыть Web версию", url=WEBHOOK_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🖥️ *SSH Agent Bot*\n\n"
        "Управляйте своими SSH серверами через Telegram!\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'add_server':
        await query.message.reply_text(
            "Отправьте данные сервера в формате:\n\n"
            "`имя|хост|порт|пользователь|пароль`\n\n"
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
        keyboard = []
        for i, srv in enumerate(servers):
            keyboard.append([InlineKeyboardButton(
                f"🖥️ {srv['name']}", 
                callback_data=f'connect_{i}'
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Выберите сервер:", reply_markup=reply_markup)
    
    elif query.data.startswith('connect_'):
        server_id = int(query.data.split('_')[1])
        server = user_sessions[user_id]['servers'][server_id]
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=server['host'],
                port=int(server['port']),
                username=server['user'],
                password=server['password'],
                timeout=10
            )
            
            if user_id not in user_sessions:
                user_sessions[user_id] = {}
            user_sessions[user_id]['current_connection'] = ssh
            user_sessions[user_id]['current_server'] = server_id
            
            await query.message.reply_text(
                f"✅ Подключено к *{server['name']}*\n\n"
                f"Теперь отправляйте команды для выполнения",
                parse_mode='Markdown'
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Ошибка подключения: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    # Добавление сервера
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
    
    # Выполнение команды
    elif user_id in user_sessions and user_sessions[user_id].get('current_connection'):
        try:
            ssh = user_sessions[user_id]['current_connection']
            stdin, stdout, stderr = ssh.exec_command(text)
            output = stdout.read().decode() + stderr.read().decode()
            
            if output:
                await update.message.reply_text(f"```\n{output}\n```", parse_mode='Markdown')
            else:
                await update.message.reply_text("✅ Команда выполнена (без вывода)")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    else:
        await update.message.reply_text("Используйте /start для начала работы")

# ============ ЗАПУСК ============
def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Для webhook режима
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == '__main__':
    # Запуск Flask и Telegram бота
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, debug=False)).start()
    run_bot()
