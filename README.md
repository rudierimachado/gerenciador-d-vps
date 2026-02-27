# 🚀 VPS Manager Pro

Sistema completo de gerenciamento de VPS com interface web moderna e intuitiva.

## ✨ Funcionalidades Principais

### 🔧 **Serviços Python** (Mantido Original)
- Monitoramento em tempo real de processos Python
- Controle de start/stop de serviços
- Git pull automático e reinicialização
- Status detalhado com CPU, memória e uptime
- **Backup** de aplicações (Mantido Original)

### 🆕 **Novas Funcionalidades**

#### 📤 **Upload de Projetos**
- **Drag & Drop** de arquivos comprimidos (.zip, .tar.gz, .rar)
- Upload com barra de progresso visual
- Instalação automática de dependências
- Inicialização automática do serviço
- Logs em tempo real do processo

#### 🔗 **Git Clone Integrado**
- Clone direto de repositórios Git (público/privado)
- Suporte a autenticação HTTPS (token/senha)
- Seleção de branch específica
- Instalação automática de requirements.txt
- Inicialização automática após clone

#### ⚡ **Comandos Rápidos**
- **Cards interativos** para comandos comuns:
  - Verificar espaço em disco (`df -h`)
  - Status da memória (`free -h`)
  - Top processos (`top`)
  - Status Nginx
  - Containers Docker
  - Listar arquivos
- **Campo personalizado** para executar qualquer comando
- Resultados em tempo real com formatação de terminal

#### 🖥️ **Terminal SSH Completo**
- Terminal full-screen em modal
- Sessão SSH persistente via WebSocket
- Suporte completo a comandos interativos
- Redimensionamento automático
- Tema escuro otimizado

## 🎨 **Interface Melhorada**

### **Design Moderno**
- **Tema escuro** profissional
- **Animações suaves** e transições
- **Cards responsivos** com hover effects
- **Ícones Bootstrap** consistentes
- **Tipografia otimizada** (JetBrains Mono para código)

### **UX Intuitiva**
- **Drag & Drop** para uploads
- **Formulários inteligentes** com validação
- **Feedback visual** com toasts e progress bars
- **Modais organizados** por funcionalidade
- **Comandos rápidos** com um clique

## 🛠️ **Tecnologias**

### Backend
- **Flask** + **SocketIO** (Python)
- **Paramiko** para conexões SSH
- **SFTP** para transferência de arquivos
- **Threading** para operações assíncronas

### Frontend
- **HTML5** + **CSS3** moderno
- **JavaScript** vanilla (sem frameworks)
- **xterm.js** para terminal web
- **Bootstrap Icons** para ícones
- **WebSocket** para comunicação em tempo real

## 🚀 **Como Usar**

### **1. Instalação**
```bash
# Clone ou baixe o projeto
git clone <repo-url>
cd vps-manager-pro

# Instale as dependências
pip install -r requirements.txt
```

### **2. Configuração**
```bash
# Copie o arquivo de exemplo
copy .env.exemplo .env

# Edite o .env com suas credenciais SSH
SSH_HOST=76.13.234.166
SSH_USER=root
SSH_PASSWORD=sua-senha-aqui
SSH_PORT=22
```

### **3. Execução**

**Método Simples:**
```bash
python run.py
```

**Método Completo:**
```bash
python gerenciador_servicos.py
```

**Windows (Duplo-clique):**
```bash
start_vps_manager.bat
```

Acesse: `http://localhost:5002` (abre automaticamente)

### **3. Upload de Projeto**
1. Clique em **"Upload"**
2. Arraste um arquivo .zip ou clique para selecionar
3. Defina nome do projeto e configurações
4. Clique em **"Fazer Upload"**
5. Acompanhe o progresso e logs

### **4. Clone Git**
1. Clique em **"Git Clone"**
2. Cole a URL do repositório
3. Configure branch e autenticação (se necessário)
4. Clique em **"Clonar Repositório"**
5. Acompanhe os logs de clone e instalação

### **5. Comandos Rápidos**
- Use os **cards pré-definidos** para comandos comuns
- Digite comandos personalizados no **campo inferior**
- Pressione **Enter** ou clique em **"Executar"**
- Veja resultados formatados em tempo real

### **6. Terminal Completo**
1. Clique em **"Terminal"**
2. Clique em **"Conectar"** no modal
3. Use como um terminal SSH normal
4. Suporte completo a vim, nano, htop, etc.

## 🔒 **Segurança**

- ✅ Validação de nomes de projetos
- ✅ Sanitização de comandos
- ✅ Conexões SSH criptografadas
- ✅ Filtros de extensões de arquivo
- ✅ Proteção contra path traversal

## 📱 **Responsividade**

- ✅ **Desktop** otimizado (1200px+)
- ✅ **Tablet** adaptado (768px-1200px)
- ✅ **Mobile** funcional (< 768px)
- ✅ **Grid flexível** que se adapta ao conteúdo
- ✅ **Modais responsivos** com scroll automático

## 🎯 **Próximas Melhorias**

- [ ] **Autenticação de usuários**
- [ ] **Logs persistentes** com rotação
- [ ] **Monitoramento de recursos** em tempo real
- [ ] **Integração com Docker** Compose
- [ ] **Backup automático** agendado
- [ ] **Notificações** push/email
- [ ] **API REST** completa
- [ ] **Temas personalizáveis**

## 🤝 **Contribuição**

Este sistema foi desenvolvido para ser **intuitivo**, **funcional** e **profissional**. 

**Características mantidas:**
- ✅ Painel de Serviços Python completo
- ✅ Sistema de Backup original
- ✅ Todas as funcionalidades existentes

**Melhorias implementadas:**
- 🆕 Upload via drag & drop
- 🆕 Git clone integrado  
- 🆕 Comandos rápidos interativos
- 🆕 Terminal SSH completo
- 🆕 Interface moderna e responsiva
- 🆕 UX otimizada e intuitiva

---

**VPS Manager Pro** - Gerenciamento de VPS nunca foi tão simples! 🎉