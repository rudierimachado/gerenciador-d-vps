from flask import Flask, render_template, jsonify, request, send_file, session
from flask_socketio import SocketIO, emit
import paramiko
import os
import threading
import logging
from dotenv import load_dotenv
import time
from datetime import datetime
import zipfile
import io
import tempfile
import stat as stat_module
import shutil
import re

load_dotenv()

app = Flask(__name__)
app.secret_key = 'vps_manager_secret_key_2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# ==================== CONFIGURAÇÃO DE LOGS ====================
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S'
)
logger = logging.getLogger('VPSManager')

# Reduz logs do paramiko e werkzeug pra não poluir
logging.getLogger('paramiko').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.INFO)

SSH_CONFIG = {
    'hostname': os.getenv('SSH_HOST'),
    'username': os.getenv('SSH_USER'),
    'password': os.getenv('SSH_PASSWORD'),
    'port': int(os.getenv('SSH_PORT', 22))
}

logger.info(f"SSH Config: host={SSH_CONFIG['hostname']}, user={SSH_CONFIG['username']}, port={SSH_CONFIG['port']}")

# Conexão SSH compartilhada
_ssh_lock = threading.Lock()
_ssh_client = None
_shell_sessions = {}

def conectar_ssh():
    global _ssh_client

    with _ssh_lock:
        if _ssh_client and _ssh_client.get_transport() and _ssh_client.get_transport().is_active():
            logger.debug("SSH: reutilizando conexão existente")
            return _ssh_client, None

        try:
            logger.info(f"SSH: abrindo nova conexão para {SSH_CONFIG['hostname']}:{SSH_CONFIG['port']}...")
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=SSH_CONFIG['hostname'],
                username=SSH_CONFIG['username'],
                password=SSH_CONFIG['password'],
                port=SSH_CONFIG['port'],
                timeout=15,
                banner_timeout=30,
                auth_timeout=30
            )
            _ssh_client = ssh
            logger.info("SSH: conexão estabelecida com sucesso!")
            return ssh, None
        except Exception as e:
            _ssh_client = None
            logger.error(f"SSH: erro ao conectar: {e}")
            return None, str(e)

def executar_comando(comando):
    global _ssh_client
    ssh, erro = conectar_ssh()
    if erro:
        logger.error(f"CMD FALHOU (sem conexão): {comando[:80]}...")
        return {'sucesso': False, 'erro': f'Erro de conexão: {erro}'}

    try:
        logger.debug(f"CMD executando: {comando[:120]}")
        inicio = time.time()

        stdin, stdout, stderr = ssh.exec_command(comando, timeout=15)
        resultado = stdout.read().decode('utf-8')
        erro_cmd = stderr.read().decode('utf-8')
        codigo_saida = stdout.channel.recv_exit_status()

        duracao = round(time.time() - inicio, 2)

        if codigo_saida == 0:
            logger.debug(f"CMD OK ({duracao}s): {comando[:80]} -> saída: {resultado[:100].strip()}")
        else:
            logger.warning(f"CMD ERRO ({duracao}s, código {codigo_saida}): {comando[:80]} -> erro: {erro_cmd[:100].strip()}")

        return {
            'sucesso': codigo_saida == 0,
            'resultado': resultado,
            'erro': erro_cmd if erro_cmd else None
        }
    except Exception as e:
        logger.error(f"CMD EXCEÇÃO: {comando[:80]} -> {e}")
        _ssh_client = None
        try:
            ssh.close()
        except:
            pass
        return {'sucesso': False, 'erro': str(e)}

def descobrir_diretorio_git(pid):
    """Descobre o diretório raiz do git a partir do cwd do processo"""
    logger.info(f"GIT: descobrindo diretório git para PID {pid}")

    cmd_dir = f"readlink -f /proc/{pid}/cwd"
    resultado_dir = executar_comando(cmd_dir)

    if not resultado_dir['sucesso']:
        logger.error(f"GIT: não foi possível ler cwd do PID {pid}")
        return None, 'Não foi possível encontrar o diretório do processo'

    diretorio = resultado_dir['resultado'].strip()
    logger.info(f"GIT: cwd do PID {pid} = {diretorio}")

    cmd_git_root = f"cd {diretorio} && git rev-parse --show-toplevel 2>/dev/null"
    resultado_git = executar_comando(cmd_git_root)

    if resultado_git['sucesso'] and resultado_git['resultado'].strip():
        git_root = resultado_git['resultado'].strip()
        logger.info(f"GIT: raiz do repositório = {git_root}")
        return git_root, None
    else:
        logger.warning(f"GIT: {diretorio} não é um repositório git")
        return diretorio, 'Diretório não é um repositório git'


@app.route('/')
def index():
    logger.info("Página principal acessada")
    return render_template('gerenciador_hostinger.html')

@app.route('/teste-terminal')
def teste_terminal():
    logger.info("Página de teste do terminal acessada")
    return send_file('teste_terminal.html')

@app.route('/api/teste-conexao')
def teste_conexao():
    logger.info("API: teste de conexão")
    resultado = executar_comando('echo "Conexão OK"')
    status = "OK" if resultado['sucesso'] else "FALHA"
    logger.info(f"API: teste de conexão = {status}")
    return jsonify(resultado)

@app.route('/api/servicos-python')
def listar_servicos_python():
    logger.info("API: listando serviços python")
    comando = "ps aux | grep python | grep -v grep | grep -v 'ps aux'"
    resultado = executar_comando(comando)

    if resultado['sucesso']:
        servicos = []
        linhas = resultado['resultado'].strip().split('\n')

        for linha in linhas:
            if linha:
                partes = linha.split(None, 10)
                if len(partes) >= 11:
                    pid = partes[1]
                    logger.debug(f"API: processando PID {pid}: {partes[10][:60]}")

                    cmd_dir = f"readlink -f /proc/{pid}/cwd 2>/dev/null || echo 'N/A'"
                    resultado_dir = executar_comando(cmd_dir)
                    diretorio = resultado_dir['resultado'].strip() if resultado_dir['sucesso'] else 'N/A'

                    cmd_git = f"cd {diretorio} && git rev-parse --short HEAD 2>/dev/null && git remote get-url origin 2>/dev/null || echo 'sem-git'"
                    resultado_git = executar_comando(cmd_git)
                    git_info = resultado_git['resultado'].strip() if resultado_git['sucesso'] else 'sem-git'

                    servicos.append({
                        'usuario': partes[0],
                        'pid': pid,
                        'cpu': partes[2],
                        'memoria': partes[3],
                        'vsz': partes[4],
                        'rss': partes[5],
                        'tty': partes[6],
                        'stat': partes[7],
                        'start': partes[8],
                        'time': partes[9],
                        'comando': partes[10],
                        'diretorio': diretorio,
                        'git_info': git_info
                    })

        logger.info(f"API: {len(servicos)} serviços python encontrados")
        return jsonify({'sucesso': True, 'servicos': servicos})
    else:
        logger.warning("API: nenhum serviço python rodando ou erro ao listar")
        return jsonify(resultado)

@app.route('/api/postgres/status')
def postgres_status():
    logger.info("API: verificando status PostgreSQL")
    comando = "systemctl status postgresql"
    resultado = executar_comando(comando)

    if resultado['sucesso'] or 'active' in resultado['resultado'].lower():
        logger.info("API: PostgreSQL está ativo")
        cmd_version = "psql --version"
        version_result = executar_comando(cmd_version)

        cmd_databases = "sudo -u postgres psql -c '\\l' 2>/dev/null || echo 'Acesso negado'"
        db_result = executar_comando(cmd_databases)

        return jsonify({
            'sucesso': True,
            'status': resultado['resultado'],
            'versao': version_result.get('resultado', 'N/A'),
            'databases': db_result.get('resultado', 'N/A')
        })
    else:
        logger.warning("API: PostgreSQL parece estar offline")
        return jsonify(resultado)

@app.route('/api/postgres/databases')
def postgres_databases():
    logger.info("API: listando bancos de dados PostgreSQL")
    comando = "sudo -u postgres psql -c '\\l' -t -A -F'|'"
    resultado = executar_comando(comando)

    if resultado['sucesso']:
        bancos = []
        linhas = resultado['resultado'].strip().split('\n')

        for linha in linhas:
            if linha and '|' in linha:
                partes = linha.split('|')
                if len(partes) >= 3:
                    bancos.append({
                        'nome': partes[0],
                        'dono': partes[1],
                        'encoding': partes[2] if len(partes) > 2 else 'N/A'
                    })

        logger.info(f"API: {len(bancos)} bancos encontrados")
        return jsonify({'sucesso': True, 'bancos': bancos})
    else:
        logger.error("API: erro ao listar bancos")
        return jsonify(resultado)

@app.route('/api/servicos/todos')
def listar_todos_servicos():
    """Lista todos os projetos Python no VPS: rodando e parados"""
    logger.info("API: listando todos os serviços python (rodando + parados)")

    # PIDs do sistema operacional que devem ser ignorados (não são serviços de usuário)
    PIDS_SISTEMA = {'899', '989'}

    # Prefixos de comando que indicam processo do sistema (não são serviços de usuário)
    CMDS_SISTEMA = [
        '/usr/bin/python',
        '/usr/lib/python',
        'python3 /usr/bin',
        'python3 /usr/lib',
        'python /usr/bin',
        'python /usr/lib',
    ]

    def _e_processo_sistema(pid, comando):
        if pid in PIDS_SISTEMA:
            return True
        for prefixo in CMDS_SISTEMA:
            if prefixo in comando:
                return True
        return False

    def _e_processo_temporario(stat, comando):
        """Filtra processos fantasma: processos de vida curta que aparecem e somem.
        São identificados por: stat 'Z' (zombie) ou 'T' (stopped), ou comandos
        que são apenas sh/bash chamando python (processos-filho do nohup)."""
        if stat and stat.startswith('Z'):
            return True
        # Processo que é filho direto de shell sem ser um .py persistente
        if not any(parte.endswith('.py') for parte in comando.split()):
            return True
        return False

    # 1. Descobre processos rodando
    cmd_ps = "ps aux | grep python | grep -v grep | grep -v 'ps aux'"
    resultado_ps = executar_comando(cmd_ps)

    processos_rodando = {}  # pid -> info do processo
    pids_por_dir = {}

    if resultado_ps['sucesso']:
        for linha in resultado_ps['resultado'].strip().split('\n'):
            if not linha:
                continue
            partes = linha.split(None, 10)
            if len(partes) >= 11:
                pid = partes[1]
                stat = partes[7]
                comando = partes[10]

                if _e_processo_sistema(pid, comando):
                    logger.debug(f"API: ignorando PID {pid} (sistema): {comando[:60]}")
                    continue

                if _e_processo_temporario(stat, comando):
                    logger.debug(f"API: ignorando PID {pid} (temporário/fantasma): {comando[:60]}")
                    continue

                cmd_dir = f"readlink -f /proc/{pid}/cwd 2>/dev/null || echo 'N/A'"
                resultado_dir = executar_comando(cmd_dir)
                diretorio = resultado_dir['resultado'].strip() if resultado_dir['sucesso'] else 'N/A'

                cmd_git = f"cd {diretorio} && git rev-parse --short HEAD 2>/dev/null && git remote get-url origin 2>/dev/null || echo 'sem-git'"
                resultado_git = executar_comando(cmd_git)
                git_info = resultado_git['resultado'].strip() if resultado_git['sucesso'] else 'sem-git'

                info = {
                    'usuario': partes[0],
                    'pid': pid,
                    'cpu': partes[2],
                    'memoria': partes[3],
                    'vsz': partes[4],
                    'rss': partes[5],
                    'tty': partes[6],
                    'stat': stat,
                    'start': partes[8],
                    'time': partes[9],
                    'comando': partes[10],
                    'diretorio': diretorio,
                    'git_info': git_info,
                    'status': 'rodando'
                }
                processos_rodando[pid] = info
                if diretorio != 'N/A':
                    if diretorio not in pids_por_dir:
                        pids_por_dir[diretorio] = []
                    pids_por_dir[diretorio].append(pid)

    # 2. Descobre projetos Python nos diretórios comuns
    cmd_projetos = (
        "find /root /home -maxdepth 4 -name 'run.py' -o -name 'app.py' -o -name 'main.py' 2>/dev/null "
        "| xargs -I{} dirname {} 2>/dev/null | sort -u"
    )
    resultado_projetos = executar_comando(cmd_projetos)

    diretorios_projetos = set()
    if resultado_projetos['sucesso']:
        for linha in resultado_projetos['resultado'].strip().split('\n'):
            d = linha.strip()
            if d:
                diretorios_projetos.add(d)

    # 3. Adiciona diretórios dos processos rodando também
    for d in pids_por_dir:
        diretorios_projetos.add(d)

    # 4. Para cada diretório, monta a info do serviço
    servicos = []

    # Primeiro adiciona os rodando
    for pid, info in processos_rodando.items():
        servicos.append(info)

    # Depois adiciona os parados (diretórios sem processo rodando)
    dirs_com_processo = set(pids_por_dir.keys())
    for diretorio in sorted(diretorios_projetos):
        if diretorio in dirs_com_processo:
            continue  # já está na lista como rodando

        # Descobre qual arquivo python usar
        cmd_arquivo = (
            f"ls {diretorio}/run.py {diretorio}/app.py {diretorio}/main.py 2>/dev/null | head -1"
        )
        resultado_arquivo = executar_comando(cmd_arquivo)
        arquivo_py = 'run.py'
        if resultado_arquivo['sucesso'] and resultado_arquivo['resultado'].strip():
            caminho = resultado_arquivo['resultado'].strip()
            arquivo_py = caminho.split('/')[-1]

        cmd_git = f"cd {diretorio} && git rev-parse --short HEAD 2>/dev/null && git remote get-url origin 2>/dev/null || echo 'sem-git'"
        resultado_git = executar_comando(cmd_git)
        git_info = resultado_git['resultado'].strip() if resultado_git['sucesso'] else 'sem-git'

        servicos.append({
            'pid': None,
            'diretorio': diretorio,
            'arquivo': arquivo_py,
            'git_info': git_info,
            'status': 'parado',
            'usuario': '',
            'cpu': '0',
            'memoria': '0',
            'vsz': '0',
            'rss': '0',
            'tty': '',
            'stat': '',
            'start': '',
            'time': '',
            'comando': f'python3 {arquivo_py}'
        })

    logger.info(f"API: {len([s for s in servicos if s['status']=='rodando'])} rodando, "
                f"{len([s for s in servicos if s['status']=='parado'])} parados")
    return jsonify({'sucesso': True, 'servicos': servicos})




@app.route('/api/servico/iniciar', methods=['POST'])
def iniciar_servico():
    data = request.json
    diretorio = data.get('diretorio', '')
    arquivo = data.get('arquivo', 'run.py')
    logger.info(f"API: iniciar serviço -> diretório={diretorio}, arquivo={arquivo}")

    if '..' in diretorio or diretorio.startswith('/etc') or diretorio.startswith('/usr'):
        logger.warning(f"API: diretório bloqueado: {diretorio}")
        return jsonify({'sucesso': False, 'erro': 'Diretório não permitido'})

    comando = f"cd {diretorio} && nohup python3 {arquivo} > app.log 2>&1 & echo $!"
    resultado = executar_comando(comando)

    if resultado['sucesso']:
        pid = resultado['resultado'].strip()
        logger.info(f"API: serviço iniciado com PID {pid}")
        return jsonify({
            'sucesso': True,
            'mensagem': f'Serviço iniciado com PID {pid}',
            'pid': pid
        })
    else:
        logger.error(f"API: erro ao iniciar serviço: {resultado.get('erro')}")
        return jsonify(resultado)

@app.route('/api/servico/parar/<pid>')
def parar_servico(pid):
    logger.info(f"API: parar serviço PID {pid}")
    if not pid.isdigit():
        return jsonify({'sucesso': False, 'erro': 'PID inválido'})

    comando = f"kill {pid}"
    resultado = executar_comando(comando)

    if resultado['sucesso'] or resultado['erro'] == '':
        logger.info(f"API: PID {pid} parado com sucesso")
        return jsonify({
            'sucesso': True,
            'mensagem': f'Serviço PID {pid} parado'
        })
    else:
        logger.warning(f"API: kill normal falhou para PID {pid}, tentando kill -9")
        comando_force = f"kill -9 {pid}"
        resultado_force = executar_comando(comando_force)

        if resultado_force['sucesso'] or resultado_force['erro'] == '':
            logger.info(f"API: PID {pid} forçado a parar com kill -9")
            return jsonify({
                'sucesso': True,
                'mensagem': f'Serviço PID {pid} forçado a parar'
            })
        else:
            logger.error(f"API: não foi possível parar PID {pid}: {resultado_force.get('erro')}")
            return jsonify(resultado_force)

def descobrir_diretorio_git(pid):
    """Descobre o diretório raiz do git, branch e remote"""
    logger.info(f"GIT: descobrindo diretório git para PID {pid}")

    cmd_dir = f"readlink -f /proc/{pid}/cwd"
    resultado_dir = executar_comando(cmd_dir)

    if not resultado_dir['sucesso']:
        logger.error(f"GIT: não foi possível ler cwd do PID {pid}")
        return None, None, None, 'Não foi possível encontrar o diretório do processo'

    diretorio = resultado_dir['resultado'].strip()
    logger.info(f"GIT: cwd do PID {pid} = {diretorio}")

    # Raiz do git
    cmd_git_root = f"cd {diretorio} && git rev-parse --show-toplevel 2>/dev/null"
    resultado_git = executar_comando(cmd_git_root)

    if not (resultado_git['sucesso'] and resultado_git['resultado'].strip()):
        logger.warning(f"GIT: {diretorio} não é um repositório git")
        return diretorio, None, None, 'Diretório não é um repositório git'

    git_root = resultado_git['resultado'].strip()
    logger.info(f"GIT: raiz do repositório = {git_root}")

    # Descobre branch atual
    cmd_branch = f"cd {git_root} && git branch --show-current 2>/dev/null"
    resultado_branch = executar_comando(cmd_branch)
    branch = resultado_branch['resultado'].strip() if resultado_branch['sucesso'] else 'main'
    if not branch:
        branch = 'main'
    logger.info(f"GIT: branch atual = {branch}")

    # Descobre remote
    cmd_remote = f"cd {git_root} && git remote 2>/dev/null | head -1"
    resultado_remote = executar_comando(cmd_remote)
    remote = resultado_remote['resultado'].strip() if resultado_remote['sucesso'] else 'origin'
    if not remote:
        remote = 'origin'
    logger.info(f"GIT: remote = {remote}")

    return git_root, branch, remote, None


@app.route('/api/servico/git-pull/<pid>')
def git_pull_servico(pid):
    logger.info(f"========== GIT PULL - PID {pid} ==========")
    if not pid.isdigit():
        return jsonify({'sucesso': False, 'erro': 'PID inválido'})

    diretorio, branch, remote, erro = descobrir_diretorio_git(pid)
    if erro and 'não é um repositório' in erro:
        logger.error(f"GIT PULL: abortado - {erro}")
        return jsonify({'sucesso': False, 'erro': erro})

    # Configura tracking se não tiver
    logger.info(f"GIT PULL: configurando tracking {remote}/{branch}...")
    cmd_tracking = f"cd {diretorio} && git branch --set-upstream-to={remote}/{branch} {branch} 2>&1"
    executar_comando(cmd_tracking)

    logger.info(f"GIT PULL: executando 'git pull {remote} {branch}' em {diretorio}")
    comando = f"cd {diretorio} && git pull {remote} {branch} 2>&1"
    resultado = executar_comando(comando)

    if resultado['sucesso']:
        logger.info(f"GIT PULL: sucesso!\n{resultado['resultado'].strip()}")
    else:
        logger.error(f"GIT PULL: falhou!\nSaída: {resultado['resultado']}\nErro: {resultado.get('erro')}")

    return jsonify({
        'sucesso': resultado['sucesso'],
        'diretorio': diretorio,
        'branch': branch,
        'remote': remote,
        'resultado': resultado['resultado'],
        'erro': resultado.get('erro')
    })


@app.route('/api/servico/atualizar-reiniciar/<pid>', methods=['POST'])
def atualizar_reiniciar(pid):
    logger.info(f"========== ATUALIZAR & REINICIAR - PID {pid} ==========")
    if not pid.isdigit():
        return jsonify({'sucesso': False, 'erro': 'PID inválido'})

    # 1. Descobre diretório git, branch e remote
    diretorio, branch, remote, erro = descobrir_diretorio_git(pid)
    if erro and 'não é um repositório' in erro:
        logger.error(f"UPDATE: abortado - {erro}")
        return jsonify({'sucesso': False, 'erro': erro})

    # 2. Descobre o comando original
    cmd_cmdline = f"cat /proc/{pid}/cmdline | tr '\\0' ' '"
    resultado_cmd = executar_comando(cmd_cmdline)
    comando_original = resultado_cmd['resultado'].strip() if resultado_cmd['sucesso'] else 'python3 run.py'
    logger.info(f"UPDATE: comando original do PID {pid}: {comando_original}")

    arquivo_py = 'run.py'
    for parte in comando_original.split():
        if parte.endswith('.py'):
            arquivo_py = parte
            break
    logger.info(f"UPDATE: arquivo python detectado: {arquivo_py}")

    # 3. Descobre cwd real do processo
    cmd_cwd = f"readlink -f /proc/{pid}/cwd"
    resultado_cwd = executar_comando(cmd_cwd)
    cwd_processo = resultado_cwd['resultado'].strip() if resultado_cwd['sucesso'] else diretorio
    logger.info(f"UPDATE: cwd do processo: {cwd_processo}")
    logger.info(f"UPDATE: raiz do git: {diretorio}")

    # 4. Configura tracking + git pull
    logger.info(f"UPDATE [1/4]: configurando tracking e executando git pull {remote} {branch} em {diretorio}...")
    cmd_tracking = f"cd {diretorio} && git branch --set-upstream-to={remote}/{branch} {branch} 2>&1"
    executar_comando(cmd_tracking)

    cmd_pull = f"cd {diretorio} && git pull {remote} {branch} 2>&1"
    resultado_pull = executar_comando(cmd_pull)
    git_output = resultado_pull['resultado']
    logger.info(f"UPDATE [1/4]: git pull resultado:\n{git_output.strip()}")

    # 5. Para o serviço
    logger.info(f"UPDATE [2/4]: parando PID {pid}...")
    cmd_kill = f"kill {pid}"
    executar_comando(cmd_kill)
    time.sleep(2)

    cmd_check = f"kill -0 {pid} 2>&1"
    check = executar_comando(cmd_check)
    if check['sucesso']:
        logger.warning(f"UPDATE [2/4]: PID {pid} ainda vivo, usando kill -9...")
        executar_comando(f"kill -9 {pid}")
        time.sleep(1)
    logger.info(f"UPDATE [2/4]: PID {pid} parado")

    # 6. Instala dependências se necessário
    pip_output = ''
    if 'requirements.txt' in git_output:
        logger.info(f"UPDATE [3/4]: requirements.txt mudou, instalando dependências...")
        cmd_pip = f"cd {diretorio} && pip3 install -r requirements.txt --break-system-packages 2>&1"
        resultado_pip = executar_comando(cmd_pip)
        pip_output = resultado_pip.get('resultado', '')
        logger.info(f"UPDATE [3/4]: pip resultado:\n{pip_output[:200]}")
    else:
        logger.info(f"UPDATE [3/4]: requirements.txt não mudou, pulando instalação")

    # 7. Reinicia no cwd original
    logger.info(f"UPDATE [4/4]: reiniciando '{arquivo_py}' em {cwd_processo}...")
    cmd_start = f"cd {cwd_processo} && nohup python3 {arquivo_py} > app.log 2>&1 & echo $!"
    resultado_start = executar_comando(cmd_start)

    novo_pid = resultado_start['resultado'].strip() if resultado_start['sucesso'] else 'N/A'

    if resultado_start['sucesso']:
        logger.info(f"UPDATE [4/4]: serviço reiniciado! Novo PID: {novo_pid}")
        logger.info(f"========== ATUALIZAÇÃO CONCLUÍDA COM SUCESSO ==========")
    else:
        logger.error(f"UPDATE [4/4]: FALHA ao reiniciar! Erro: {resultado_start.get('erro')}")
        logger.error(f"========== ATUALIZAÇÃO FALHOU ==========")

    return jsonify({
        'sucesso': resultado_start['sucesso'],
        'diretorio': diretorio,
        'cwd': cwd_processo,
        'branch': branch,
        'remote': remote,
        'arquivo': arquivo_py,
        'git_output': git_output,
        'pip_output': pip_output,
        'pid_antigo': pid,
        'pid_novo': novo_pid,
        'mensagem': f'Atualizado e reiniciado! Novo PID: {novo_pid}'
    })


@app.route('/api/servico/git-status/<pid>')
def git_status_servico(pid):
    logger.info(f"========== GIT STATUS - PID {pid} ==========")
    if not pid.isdigit():
        return jsonify({'sucesso': False, 'erro': 'PID inválido'})

    diretorio, branch, remote, erro = descobrir_diretorio_git(pid)
    if erro and 'não é um repositório' in erro:
        logger.error(f"GIT STATUS: abortado - {erro}")
        return jsonify({'sucesso': False, 'erro': erro})

    logger.info(f"GIT STATUS: fazendo fetch {remote} em {diretorio}...")
    executar_comando(f"cd {diretorio} && git fetch {remote} 2>/dev/null")

    comandos = {
        'branch': f"cd {diretorio} && git branch --show-current",
        'commit_local': f"cd {diretorio} && git log --oneline -1",
        'commit_remoto': f"cd {diretorio} && git log --oneline -1 {remote}/{branch} 2>/dev/null || echo 'N/A'",
        'atras': f"cd {diretorio} && git rev-list --count HEAD..{remote}/{branch} 2>/dev/null || echo '0'",
        'status': f"cd {diretorio} && git status --short",
        'ultimo_pull': f"cd {diretorio} && stat -c '%y' .git/FETCH_HEAD 2>/dev/null || echo 'N/A'"
    }

    info = {}
    for chave, cmd in comandos.items():
        resultado = executar_comando(cmd)
        info[chave] = resultado['resultado'].strip() if resultado['sucesso'] else 'N/A'
        logger.info(f"GIT STATUS: {chave} = {info[chave]}")

    atras = int(info.get('atras', '0') or '0')
    if atras > 0:
        logger.warning(f"GIT STATUS: repositório está {atras} commit(s) atrás do remoto!")
    else:
        logger.info(f"GIT STATUS: repositório está atualizado")

    return jsonify({
        'sucesso': True,
        'diretorio': diretorio,
        'branch': branch,
        'remote': remote,
        'git': info
    })

@app.route('/api/sistema/info')
def sistema_info():
    logger.info("API: coletando informações do sistema")
    comandos = {
        'hostname': 'hostname',
        'uptime': 'uptime',
        'memoria': 'free -h',
        'disco': 'df -h /',
        'cpu': 'lscpu | grep "Model name"'
    }

    info = {}
    for chave, comando in comandos.items():
        resultado = executar_comando(comando)
        if resultado['sucesso']:
            info[chave] = resultado['resultado'].strip()
        else:
            info[chave] = 'N/A'

    logger.info(f"API: sistema info coletado - hostname={info.get('hostname', 'N/A')}")
    return jsonify({'sucesso': True, 'info': info})

@app.route('/api/logs/<path:caminho>')
def ver_logs(caminho):
    logger.info(f"API: lendo logs de {caminho}")
    if '..' in caminho or caminho.startswith('/etc'):
        logger.warning(f"API: caminho bloqueado: {caminho}")
        return jsonify({'sucesso': False, 'erro': 'Caminho não permitido'})

    comando = f"tail -n 100 {caminho}"
    resultado = executar_comando(comando)
    return jsonify(resultado)


# ==================== BACKUP ====================

_BACKUP_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'backup_config.txt')

def _ler_pasta_backup():
    if os.path.exists(_BACKUP_CONFIG_FILE):
        with open(_BACKUP_CONFIG_FILE, 'r', encoding='utf-8') as f:
            pasta = f.read().strip()
            if pasta:
                return pasta
    return os.path.join(os.path.expanduser('~'), 'Desktop', 'VPS_Backups')

def _salvar_pasta_backup(pasta):
    with open(_BACKUP_CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(pasta)

@app.route('/api/backup/config', methods=['GET'])
def backup_config_get():
    return jsonify({'sucesso': True, 'pasta': _ler_pasta_backup()})

@app.route('/api/backup/config', methods=['POST'])
def backup_config_set():
    data = request.json
    pasta = data.get('pasta', '').strip()
    if not pasta:
        return jsonify({'sucesso': False, 'erro': 'Pasta não informada'})
    _salvar_pasta_backup(pasta)
    logger.info(f"BACKUP: pasta de destino configurada: {pasta}")
    return jsonify({'sucesso': True, 'pasta': pasta})

@app.route('/api/backup/listar-vps')
def backup_listar_vps():
    """Lista subpastas de um diretório no VPS via SSH."""
    caminho = request.args.get('caminho', '/').strip()
    if '..' in caminho:
        return jsonify({'sucesso': False, 'erro': 'Caminho inválido'})

    ssh, erro = conectar_ssh()
    if erro:
        return jsonify({'sucesso': False, 'erro': erro})

    try:
        sftp = ssh.open_sftp()
        itens = sftp.listdir_attr(caminho)
        pastas = []
        for item in sorted(itens, key=lambda x: x.filename):
            if stat_module.S_ISDIR(item.st_mode) and not item.filename.startswith('.'):
                pastas.append(item.filename)
        sftp.close()

        # Monta pai
        pai = '/'.join(caminho.rstrip('/').split('/')[:-1]) or '/'

        return jsonify({'sucesso': True, 'caminho': caminho, 'pai': pai, 'pastas': pastas})
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)})

@app.route('/api/backup/listar-windows')
def backup_listar_windows():
    """Lista drives e subpastas do Windows local."""
    caminho = request.args.get('caminho', '').strip()

    try:
        if not caminho:
            # Raiz: lista drives disponíveis
            import string
            drives = []
            for letra in string.ascii_uppercase:
                drive = f"{letra}:\\"
                if os.path.exists(drive):
                    drives.append({'nome': drive, 'caminho': drive})
            return jsonify({'sucesso': True, 'caminho': '', 'pai': '', 'pastas': drives})

        if not os.path.isdir(caminho):
            return jsonify({'sucesso': False, 'erro': 'Pasta não encontrada'})

        pastas = []
        try:
            for nome in sorted(os.listdir(caminho)):
                caminho_item = os.path.join(caminho, nome)
                if os.path.isdir(caminho_item) and not nome.startswith('.'):
                    pastas.append({'nome': nome, 'caminho': caminho_item})
        except PermissionError:
            pass

        # Monta pai
        pai = str(os.path.dirname(caminho.rstrip('/\\')) or '')

        return jsonify({'sucesso': True, 'caminho': caminho, 'pai': pai, 'pastas': pastas})
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)})

def _sftp_baixar_pasta(sftp, caminho_remoto, zip_file, prefixo_base):
    """Baixa recursivamente uma pasta remota para um ZipFile local."""
    try:
        itens = sftp.listdir_attr(caminho_remoto)
    except Exception as e:
        logger.warning(f"BACKUP: não foi possível listar {caminho_remoto}: {e}")
        return

    for item in itens:
        nome = item.filename
        # ignora .git, __pycache__, *.pyc, node_modules, venv, .env
        if nome in ('.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env'):
            continue
        if nome.endswith('.pyc'):
            continue

        caminho_item = caminho_remoto.rstrip('/') + '/' + nome
        nome_no_zip = prefixo_base.rstrip('/') + '/' + nome

        if stat_module.S_ISDIR(item.st_mode):
            _sftp_baixar_pasta(sftp, caminho_item, zip_file, nome_no_zip)
        else:
            try:
                with sftp.open(caminho_item, 'rb') as f_remoto:
                    dados = f_remoto.read()
                zip_file.writestr(nome_no_zip, dados)
                logger.debug(f"BACKUP: adicionado {nome_no_zip} ({len(dados)} bytes)")
            except Exception as e:
                logger.warning(f"BACKUP: erro ao baixar {caminho_item}: {e}")

@app.route('/api/backup/servico', methods=['POST'])
def backup_servico():
    data = request.json
    diretorio = data.get('diretorio', '').strip()
    nome_app = data.get('nome', '').strip()
    pasta_destino_req = data.get('pasta_destino', '').strip()

    logger.info(f"========== BACKUP - {diretorio} ==========")

    if not diretorio or '..' in diretorio:
        return jsonify({'sucesso': False, 'erro': 'Diretório inválido'})

    pasta_destino = pasta_destino_req if pasta_destino_req else _ler_pasta_backup()

    ssh, erro = conectar_ssh()
    if erro:
        return jsonify({'sucesso': False, 'erro': f'Sem conexão SSH: {erro}'})

    try:
        sftp = ssh.open_sftp()
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': f'Erro ao abrir SFTP: {e}'})

    # Nome do arquivo zip: nomeprojeto_YYYYMMDD_HHMMSS.zip
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    nome_projeto = nome_app or diretorio.strip('/').replace('/', '_')
    nome_zip = f"{nome_projeto}_{ts}.zip"

    os.makedirs(pasta_destino, exist_ok=True)
    caminho_zip_local = os.path.join(pasta_destino, nome_zip)

    logger.info(f"BACKUP: baixando {diretorio} -> {caminho_zip_local}")

    try:
        with zipfile.ZipFile(caminho_zip_local, 'w', zipfile.ZIP_DEFLATED) as zf:
            prefixo = diretorio.strip('/').split('/')[-1]  # nome da pasta raiz dentro do zip
            _sftp_baixar_pasta(sftp, diretorio, zf, prefixo)
    except Exception as e:
        logger.error(f"BACKUP: erro ao criar zip: {e}")
        sftp.close()
        return jsonify({'sucesso': False, 'erro': str(e)})

    sftp.close()

    tamanho = os.path.getsize(caminho_zip_local)
    tamanho_mb = round(tamanho / 1024 / 1024, 2)
    logger.info(f"BACKUP: concluído! {caminho_zip_local} ({tamanho_mb} MB)")

    return jsonify({
        'sucesso': True,
        'arquivo': nome_zip,
        'caminho': caminho_zip_local,
        'pasta': pasta_destino,
        'tamanho_mb': tamanho_mb,
        'mensagem': f'Backup salvo em {pasta_destino}'
    })


# ==================== NOVAS FUNCIONALIDADES ====================

def _validar_nome_sistema(nome):
    import re
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', nome))

def _e_bool_verdadeiro(valor, padrao=False):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.lower() in ('true', '1', 'yes', 'on')
    return padrao

@app.route('/api/upload-projeto', methods=['POST'])
def upload_projeto():
    """Upload de projeto via arquivo comprimido"""
    logger.info("========== UPLOAD DE PROJETO ==========")
    
    if 'arquivo' not in request.files:
        return jsonify({'sucesso': False, 'erro': 'Nenhum arquivo enviado'}), 400
    
    arquivo = request.files['arquivo']
    nome = request.form.get('nome', '').strip()
    destino = request.form.get('destino', '/root').strip()
    arquivo_principal = request.form.get('arquivo_principal', 'app.py').strip()
    porta = request.form.get('porta', '').strip()
    requirements = _e_bool_verdadeiro(request.form.get('requirements'), True)
    
    logs = []
    
    def _log(msg):
        logger.info(f"UPLOAD: {msg}")
        logs.append(msg)
    
    if not nome or not _validar_nome_sistema(nome):
        return jsonify({'sucesso': False, 'erro': 'Nome inválido'}), 400
    
    if not arquivo or arquivo.filename == '':
        return jsonify({'sucesso': False, 'erro': 'Arquivo não selecionado'}), 400
    
    # Extensões permitidas
    extensoes_ok = ['.zip', '.tar.gz', '.rar']
    if not any(arquivo.filename.lower().endswith(ext) for ext in extensoes_ok):
        return jsonify({'sucesso': False, 'erro': 'Formato não suportado. Use .zip, .tar.gz ou .rar'}), 400
    
    remote_dir = f"{destino.rstrip('/')}/{nome}"
    temp_dir = tempfile.mkdtemp(prefix='upload_')
    
    try:
        # Salva arquivo temporariamente
        _log(f'Recebendo arquivo: {arquivo.filename}')
        arquivo_local = os.path.join(temp_dir, arquivo.filename)
        arquivo.save(arquivo_local)
        tamanho_mb = round(os.path.getsize(arquivo_local) / 1024 / 1024, 2)
        _log(f'Arquivo salvo localmente ({tamanho_mb} MB)')
        
        # Conecta SSH
        ssh, erro = conectar_ssh()
        if erro:
            _log(f'Erro SSH: {erro}')
            return jsonify({'sucesso': False, 'erro': 'Conexão SSH falhou', 'logs': logs})
        
        # Upload via SFTP
        _log('Enviando para VPS...')
        remote_tmp = f"/tmp/{nome}_{int(time.time())}.{arquivo.filename.split('.')[-1]}"
        
        sftp = ssh.open_sftp()
        sftp.put(arquivo_local, remote_tmp)
        sftp.close()
        _log('Upload concluído')
        
        # Extração
        _log(f'Criando diretório {remote_dir}...')
        cmd_setup = f"mkdir -p '{destino}' && rm -rf '{remote_dir}' && mkdir -p '{remote_dir}'"
        resultado = executar_comando(cmd_setup)
        if not resultado['sucesso']:
            _log(f"Erro ao criar diretório: {resultado.get('erro')}")
            return jsonify({'sucesso': False, 'erro': 'Falha ao criar diretório', 'logs': logs})
        
        # Comando de extração baseado na extensão
        if arquivo.filename.lower().endswith('.zip'):
            cmd_extract = f"cd '{remote_dir}' && unzip -q '{remote_tmp}' && rm -f '{remote_tmp}'"
        elif arquivo.filename.lower().endswith('.tar.gz'):
            cmd_extract = f"cd '{remote_dir}' && tar -xzf '{remote_tmp}' --strip-components=1 && rm -f '{remote_tmp}'"
        else:  # .rar
            cmd_extract = f"cd '{remote_dir}' && unrar x '{remote_tmp}' && rm -f '{remote_tmp}'"
        
        _log('Extraindo arquivos...')
        resultado = executar_comando(cmd_extract)
        if not resultado['sucesso']:
            _log(f"Erro na extração: {resultado.get('erro')}")
            return jsonify({'sucesso': False, 'erro': 'Falha na extração', 'logs': logs})
        
        # Instalar dependências
        if requirements:
            _log('Verificando requirements.txt...')
            cmd_req = f"cd '{remote_dir}' && if [ -f requirements.txt ]; then pip3 install -r requirements.txt --break-system-packages; else echo 'Sem requirements.txt'; fi"
            resultado = executar_comando(cmd_req)
            req_output = resultado.get('resultado', '')[:200]
            _log(f'Dependências: {req_output}')
        
        # Iniciar serviço
        _log(f'Iniciando {arquivo_principal}...')
        cmd_start = f"cd '{remote_dir}' && nohup python3 '{arquivo_principal}' > app.log 2>&1 & echo $!"
        resultado = executar_comando(cmd_start)
        
        if resultado['sucesso']:
            pid = resultado['resultado'].strip()
            _log(f'Serviço iniciado com PID {pid}')
            return jsonify({
                'sucesso': True,
                'logs': logs,
                'diretorio': remote_dir,
                'pid': pid,
                'mensagem': f'Projeto {nome} implantado com sucesso!'
            })
        else:
            _log(f"Erro ao iniciar: {resultado.get('erro')}")
            return jsonify({
                'sucesso': False,
                'erro': 'Projeto enviado mas não foi possível iniciar',
                'logs': logs,
                'diretorio': remote_dir
            })
    
    except Exception as e:
        _log(f'Exceção: {str(e)}')
        return jsonify({'sucesso': False, 'erro': str(e), 'logs': logs})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.route('/api/git-clone', methods=['POST'])
def git_clone():
    """Clona repositório Git no VPS"""
    logger.info("========== GIT CLONE ==========")
    
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    nome = data.get('nome', '').strip()
    destino = data.get('destino', '/root').strip()
    branch = data.get('branch', 'main').strip()
    arquivo = data.get('arquivo', 'app.py').strip()
    auth = data.get('auth', False)
    usuario = data.get('usuario', '').strip()
    senha = data.get('senha', '').strip()
    requirements = data.get('requirements', True)
    
    logs = []
    
    def _log(msg):
        logger.info(f"GIT CLONE: {msg}")
        logs.append(msg)
    
    if not url:
        return jsonify({'sucesso': False, 'erro': 'URL do repositório obrigatória'}), 400
    
    # Se não informou nome, extrai do URL
    if not nome:
        nome = url.split('/')[-1].replace('.git', '')
        if not nome:
            nome = 'projeto-git'
    
    if not _validar_nome_sistema(nome):
        return jsonify({'sucesso': False, 'erro': 'Nome de projeto inválido'}), 400
    
    remote_dir = f"{destino.rstrip('/')}/{nome}"
    
    try:
        _log(f'Clonando {url} -> {remote_dir}')
        
        # Monta URL com autenticação se necessário
        clone_url = url
        if auth and usuario and senha:
            # Para HTTPS: https://user:pass@github.com/user/repo.git
            if url.startswith('https://'):
                clone_url = url.replace('https://', f'https://{usuario}:{senha}@')
                _log('Usando autenticação HTTPS')
            else:
                _log('Autenticação disponível apenas para HTTPS')
        
        # Prepara comando git clone
        cmd_clone = f"cd '{destino}' && rm -rf '{nome}' && git clone -b '{branch}' '{clone_url}' '{nome}'"
        
        _log(f'Executando clone na branch {branch}...')
        resultado = executar_comando(cmd_clone)
        
        if not resultado['sucesso']:
            erro_msg = resultado.get('erro') or resultado.get('resultado') or 'Erro desconhecido'
            _log(f'Erro no clone: {erro_msg}')
            return jsonify({'sucesso': False, 'erro': f'Falha no git clone: {erro_msg}', 'logs': logs})
        
        _log('Clone concluído com sucesso')
        
        # Instalar dependências
        if requirements:
            _log('Instalando dependências...')
            cmd_req = f"cd '{remote_dir}' && if [ -f requirements.txt ]; then pip3 install -r requirements.txt --break-system-packages; else echo 'Sem requirements.txt'; fi"
            resultado_req = executar_comando(cmd_req)
            req_output = resultado_req.get('resultado', '')[:200]
            _log(f'Pip: {req_output}')
        
        # Iniciar serviço
        _log(f'Iniciando {arquivo}...')
        cmd_start = f"cd '{remote_dir}' && nohup python3 '{arquivo}' > app.log 2>&1 & echo $!"
        resultado_start = executar_comando(cmd_start)
        
        if resultado_start['sucesso']:
            pid = resultado_start['resultado'].strip()
            _log(f'Serviço iniciado com PID {pid}')
            return jsonify({
                'sucesso': True,
                'logs': logs,
                'diretorio': remote_dir,
                'pid': pid,
                'mensagem': f'Repositório clonado e iniciado!'
            })
        else:
            _log(f"Clone OK, mas erro ao iniciar: {resultado_start.get('erro')}")
            return jsonify({
                'sucesso': True,  # Clone foi bem-sucedido
                'logs': logs,
                'diretorio': remote_dir,
                'mensagem': 'Repositório clonado, mas não foi possível iniciar automaticamente'
            })
    
    except Exception as e:
        _log(f'Exceção: {str(e)}')
        return jsonify({'sucesso': False, 'erro': str(e), 'logs': logs})

@app.route('/api/executar-comando', methods=['POST'])
def executar_comando_api():
    """Executa comando único no VPS"""
    data = request.get_json() or {}
    comando = data.get('comando', '').strip()
    
    if not comando:
        return jsonify({'sucesso': False, 'erro': 'Comando vazio'})
    
    logger.info(f"COMANDO API: {comando}")
    resultado = executar_comando(comando)
    
    return jsonify(resultado)

@app.route('/api/teste-ssh')
def teste_ssh_simples():
    """Teste simples de conexão SSH"""
    try:
        ssh, erro = conectar_ssh()
        if erro:
            return jsonify({'sucesso': False, 'erro': erro})
        
        # Testa comando simples
        stdin, stdout, stderr = ssh.exec_command('echo "SSH OK"')
        resultado = stdout.read().decode('utf-8').strip()
        ssh.close()
        
        return jsonify({'sucesso': True, 'resultado': resultado})
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)})

# ==================== SOCKETIO PARA TERMINAL SSH ====================

# Armazenamento global de canais SSH (melhor que sessões para SocketIO)
ssh_channels = {}

@socketio.on('connect', namespace='/ssh')
def ssh_connect():
    logger.info(f"Cliente SSH conectado: {request.sid}")
    emit('ssh_status', {'status': 'connected'})

@socketio.on('disconnect', namespace='/ssh')
def ssh_disconnect():
    logger.info(f"Cliente SSH desconectado: {request.sid}")
    # Limpa canal SSH se existir
    if request.sid in ssh_channels:
        try:
            ssh_channels[request.sid]['channel'].close()
        except:
            pass
        del ssh_channels[request.sid]

@socketio.on('ssh_start', namespace='/ssh')
def ssh_start(data):
    """Inicia sessão SSH"""
    try:
        logger.info(f"Iniciando SSH para cliente: {request.sid}")
        cols = data.get('cols', 80)
        rows = data.get('rows', 24)
        
        ssh, erro = conectar_ssh()
        if erro:
            logger.error(f"Erro SSH: {erro}")
            emit('ssh_error', {'erro': f'Falha na conexão SSH: {erro}'})
            return
        
        # Cria canal SSH
        channel = ssh.invoke_shell(term='xterm-256color', width=cols, height=rows)
        channel.settimeout(0.1)  # Timeout para recv
        
        # Armazena no dicionário global
        ssh_channels[request.sid] = {
            'ssh': ssh,
            'channel': channel,
            'running': True
        }
        
        emit('ssh_ready')
        logger.info(f"SSH pronto para cliente: {request.sid}")
        
        # Thread para ler output do SSH
        def ler_ssh():
            try:
                while ssh_channels.get(request.sid, {}).get('running', False):
                    try:
                        if channel.recv_ready():
                            data_recv = channel.recv(1024).decode('utf-8', errors='ignore')
                            if data_recv:
                                socketio.emit('ssh_output', {'data': data_recv}, 
                                            namespace='/ssh', room=request.sid)
                        
                        if channel.exit_status_ready():
                            break
                            
                        socketio.sleep(0.01)
                    except Exception:
                        socketio.sleep(0.1)
                        
            except Exception as e:
                logger.error(f"Erro na thread SSH {request.sid}: {e}")
                socketio.emit('ssh_error', {'erro': str(e)}, namespace='/ssh', room=request.sid)
            finally:
                # Limpa recursos
                if request.sid in ssh_channels:
                    ssh_channels[request.sid]['running'] = False
                    try:
                        channel.close()
                        ssh.close()
                    except:
                        pass
                    del ssh_channels[request.sid]
                socketio.emit('ssh_closed', namespace='/ssh', room=request.sid)
                logger.info(f"Thread SSH finalizada para cliente: {request.sid}")
        
        socketio.start_background_task(ler_ssh)
        
    except Exception as e:
        logger.error(f"Erro ao iniciar SSH para {request.sid}: {e}")
        emit('ssh_error', {'erro': str(e)})

@socketio.on('ssh_input', namespace='/ssh')
def ssh_input(data):
    """Envia input para o SSH"""
    try:
        if request.sid in ssh_channels:
            channel = ssh_channels[request.sid]['channel']
            input_data = data['data']
            channel.send(input_data)
            logger.debug(f"Input SSH enviado para {request.sid}: {repr(input_data[:20])}")
    except Exception as e:
        logger.error(f"Erro ao enviar input SSH para {request.sid}: {e}")
        emit('ssh_error', {'erro': str(e)})

@socketio.on('ssh_resize', namespace='/ssh')
def ssh_resize(data):
    """Redimensiona terminal SSH"""
    try:
        if request.sid in ssh_channels:
            channel = ssh_channels[request.sid]['channel']
            channel.resize_pty(width=data['cols'], height=data['rows'])
            logger.debug(f"Terminal redimensionado para {request.sid}: {data['cols']}x{data['rows']}")
    except Exception as e:
        logger.error(f"Erro ao redimensionar SSH para {request.sid}: {e}")

if __name__ == '__main__':
    import socket
    
    # Função para encontrar porta disponível
    def encontrar_porta_disponivel(porta_inicial=5002):
        for porta in range(porta_inicial, porta_inicial + 20):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('0.0.0.0', porta))
                    return porta
            except OSError:
                continue
        return None
    
    # Usa porta do ambiente ou encontra uma disponível
    porta_env = os.getenv('VPS_MANAGER_PORT')
    if porta_env:
        try:
            porta = int(porta_env)
            # Testa se a porta está disponível
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', porta))
        except (ValueError, OSError):
            porta = encontrar_porta_disponivel()
    else:
        porta = encontrar_porta_disponivel()
    
    if not porta:
        logger.error("Não foi possível encontrar uma porta disponível!")
        exit(1)
    
    logger.info("=" * 60)
    logger.info(f"  VPS Manager Pro iniciando na porta {porta}")
    logger.info("=" * 60)
    logger.info(f"  Acesse: http://localhost:{porta}")
    logger.info("=" * 60)
    
    try:
        socketio.run(app, host='0.0.0.0', port=porta, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro ao iniciar servidor: {e}")
        exit(1)
