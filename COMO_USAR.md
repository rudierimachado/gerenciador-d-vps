# 🚀 Como Usar o VPS Manager Pro

## 🎯 Início Rápido

### **Método 1: Execução Direta**
```bash
python gerenciador_servicos.py
```
Acesse: `http://localhost:5002`

### **Método 2: Inicializador (Windows)**
```bash
start_vps_manager.bat
```
Ou duplo-clique no arquivo `.bat`

---

## ✨ Funcionalidades Principais

### **1. 📤 Upload de Projetos**
1. Clique no botão **"Upload"** (verde)
2. **Arraste** um arquivo `.zip`, `.tar.gz` ou `.rar` na área
3. Ou **clique** para selecionar arquivo
4. Preencha:
   - **Nome do projeto** (será a pasta no VPS)
   - **Diretório destino** (ex: `/root`)
   - **Arquivo principal** (ex: `app.py`)
   - **Porta** (opcional)
5. Marque **"Instalar dependências"** se tiver `requirements.txt`
6. Clique **"Fazer Upload"**
7. Acompanhe o **progresso** e **logs** em tempo real

### **2. 🔗 Git Clone**
1. Clique no botão **"Git Clone"** (azul)
2. Cole a **URL do repositório**
3. Configure:
   - **Nome do projeto** (opcional, usa nome do repo)
   - **Diretório destino** (ex: `/root`)
   - **Branch** (ex: `main`)
   - **Arquivo principal** (ex: `app.py`)
4. Se for repositório **privado**:
   - Marque **"Repositório privado"**
   - Informe **usuário/token** e **senha/token**
5. Clique **"Clonar Repositório"**
6. Acompanhe os **logs** do processo

### **3. ⚡ Comandos Rápidos**
**Cards pré-definidos:**
- 💾 **Espaço em Disco** → `df -h`
- 🧠 **Memória RAM** → `free -h`
- ⚡ **Processos CPU** → `top -bn1 | head -20`
- 🌐 **Nginx Status** → `systemctl status nginx`
- 📦 **Docker** → `docker ps`
- 📁 **Listar /root** → `ls -la /root`

**Comando personalizado:**
1. Digite no campo inferior
2. Pressione **Enter** ou clique **"Executar"**
3. Veja resultado formatado

### **4. 🖥️ Terminal SSH Completo**
1. Clique no botão **"Terminal"**
2. No modal, clique **"Conectar"**
3. Use como terminal normal:
   - `vim`, `nano`, `htop`
   - `cd`, `ls`, `mkdir`
   - Qualquer comando Linux
4. **Redimensiona** automaticamente
5. **Sessão persistente** via WebSocket

### **5. 🔧 Gerenciar Serviços Python**
**Serviços Rodando:**
- 🟢 **Status** em tempo real (CPU, RAM, tempo)
- 🔄 **Git Pull** (atualizar código)
- ⚠️ **Atualizar & Reiniciar** (pull + restart + pip)
- ℹ️ **Git Status** (verificar commits)
- 🛑 **Parar** serviço

**Serviços Parados:**
- ▶️ **Iniciar** serviço
- 📦 **Backup** da aplicação

### **6. 💾 Sistema de Backup**
1. Clique **"Backup"** (amarelo)
2. **Lado VPS:** navegue e selecione pasta origem
3. **Lado Windows:** navegue e selecione pasta destino
4. Clique **"Fazer Backup"**
5. Arquivo `.zip` será salvo localmente

---

## 🛠️ Configuração Inicial

### **1. Arquivo .env**
Crie um arquivo `.env` na pasta do projeto:
```env
SSH_HOST=76.13.234.166
SSH_USER=root
SSH_PASSWORD=sua-senha-aqui
SSH_PORT=22
```

### **2. Dependências**
```bash
pip install flask flask-socketio paramiko python-dotenv
```

---

## 🎨 Interface

### **Tema Escuro Profissional**
- 🎯 **Cards interativos** com hover effects
- 📱 **Responsivo** (desktop/tablet/mobile)
- ⚡ **Animações suaves**
- 🔔 **Notificações toast** para feedback
- 📊 **Barras de progresso** visuais

### **Organização Intuitiva**
- 📊 **Stats do servidor** (hostname, uptime, RAM, disco)
- 🐍 **Painel de Serviços Python** (principal)
- ⚡ **Comandos Rápidos** (novo)
- 🗃️ **PostgreSQL** (status e bancos)

---

## 🔒 Segurança

- ✅ **Conexões SSH criptografadas**
- ✅ **Validação de nomes** de projetos
- ✅ **Sanitização de comandos**
- ✅ **Filtros de extensões** de arquivo
- ✅ **Proteção contra path traversal**

---

## 🚨 Resolução de Problemas

### **Erro: Porta já em uso**
```bash
# Windows
netstat -ano | findstr :5002
taskkill /PID [número] /F

# Linux/Mac
lsof -ti:5002 | xargs kill -9
```

### **Erro: Dependências faltando**
```bash
pip install flask flask-socketio paramiko python-dotenv
```

### **Erro: Conexão SSH**
1. Verifique o arquivo `.env`
2. Teste conexão manual: `ssh root@seu-vps-ip`
3. Verifique firewall/porta 22

### **Upload não funciona**
1. Verifique formato do arquivo (`.zip`, `.tar.gz`, `.rar`)
2. Teste com arquivo menor
3. Verifique logs no modal

---

## 📞 Suporte

**Sistema funcionando em:**
- ✅ **Windows 10/11**
- ✅ **Python 3.8+**
- ✅ **Navegadores modernos** (Chrome, Firefox, Edge)

**Acesso:**
- 🌐 **Local:** `http://localhost:5002`
- 🌐 **Rede:** `http://seu-ip:5002`

---

**VPS Manager Pro** - Gerenciamento de VPS nunca foi tão fácil! 🎉