import os
import posixpath
import re
import shlex
from datetime import datetime
from functools import wraps
from typing import Dict, List, Optional

import paramiko
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)

load_dotenv()

app = Flask(__name__)

SSH_CONFIG = {
    "host": os.getenv("SSH_HOST"),
    "port": int(os.getenv("SSH_PORT", "22")),
    "user": os.getenv("SSH_USER"),
    "password": os.getenv("SSH_PASSWORD"),
}

VPS_IDENTIFIER = "8TLARNyaw5ULmYdenO3aE1xjIqe4xgfgESjUEJKx4d960f2e"
DEFAULT_POSTGRES_LIST_CMD = (
    'sudo -u postgres psql -Atc "'
    "SELECT datname, pg_size_pretty(pg_database_size(datname)) "
    "FROM pg_database WHERE datistemplate = false ORDER BY pg_database_size(datname) DESC;"
    '"'
)
POSTGRES_LIST_CMD = os.getenv("POSTGRES_LIST_DB_CMD", DEFAULT_POSTGRES_LIST_CMD)
DEFAULT_PYTHON_PROCESS_CMD = os.getenv(
    "PYTHON_PROCESS_CMD",
    "ps -eo pid,%cpu,%mem,cmd --sort=-%cpu | head -n 40",
)
APP_GIT_PATH = os.getenv("APP_GIT_PATH")
APP_UPDATE_COMMAND = os.getenv("APP_UPDATE_COMMAND")
APP_RESTART_COMMAND = os.getenv("APP_RESTART_COMMAND")
PROJECTS_BASE_PATH = os.getenv("PROJECTS_BASE_PATH", "/root")
ADMIN_USER = os.getenv("admin")
ADMIN_PASSWORD = os.getenv("senha")
app.secret_key = os.getenv("SECRET_KEY") or (ADMIN_PASSWORD or "monitor").encode()


def _calc_percent(used: int, total: int) -> float:
    if not total:
        return 0.0
    return round((used / total) * 100, 2)


def _ensure_config():
    missing = [key for key, value in SSH_CONFIG.items() if value in (None, "")]
    if missing:
        raise RuntimeError(
            "Missing SSH configuration values: " + ", ".join(missing)
        )


def _get_ssh_client() -> paramiko.SSHClient:
    _ensure_config()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SSH_CONFIG["host"],
        port=SSH_CONFIG["port"],
        username=SSH_CONFIG["user"],
        password=SSH_CONFIG["password"],
        timeout=10,
    )
    return client


def _run_command(
    client: paramiko.SSHClient,
    command: str,
    timeout: int = 10,
    stream_callback=None,
) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    stdin.close()
    output_chunks = []

    while True:
        line = stdout.readline()
        if not line:
            break
        decoded = line.rstrip("\n")
        output_chunks.append(decoded)
        if stream_callback:
            stream_callback(decoded)

    error = stderr.read().decode("utf-8").strip()
    output = "\n".join(output_chunks).strip()
    if error and not output:
        raise RuntimeError(f"Command '{command}' failed: {error}")
    return output if output else error


def _serialize_ssh_info() -> Dict[str, object]:
    return {
        "host": SSH_CONFIG.get("host"),
        "user": SSH_CONFIG.get("user"),
        "port": SSH_CONFIG.get("port"),
        "app_path": APP_GIT_PATH,
    }


def _parse_memory_info(raw: str) -> Dict[str, int]:
    lines = [line for line in raw.splitlines() if line.strip()]
    mem_line = next((line for line in lines if line.lower().startswith("mem")), None)
    if not mem_line:
        raise ValueError("Unable to parse memory information")

    parts = mem_line.split()
    return {
        "total": int(parts[1]),
        "used": int(parts[2]),
        "free": int(parts[3]),
        "shared": int(parts[4]),
        "cache": int(parts[5]),
        "available": int(parts[6]) if len(parts) > 6 else 0,
    }


def _parse_swap_info(raw: str) -> Dict[str, int]:
    lines = [line for line in raw.splitlines() if line.strip()]
    swap_line = next((line for line in lines if line.lower().startswith("swap")), None)
    if not swap_line:
        return {"total": 0, "used": 0, "free": 0}

    parts = swap_line.split()
    return {
        "total": int(parts[1]),
        "used": int(parts[2]),
        "free": int(parts[3]) if len(parts) > 3 else 0,
    }


def _parse_disk_info(raw: str) -> Dict[str, str]:
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("Unable to parse disk information")

    header, values = lines[0], lines[1]
    parts = values.split()
    return {
        "filesystem": parts[0],
        "size": parts[1],
        "used": parts[2],
        "available": parts[3],
        "use_percent": parts[4],
        "mount": parts[5],
    }


def _parse_processes(raw: str) -> List[Dict[str, str]]:
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) <= 1:
        return []

    processes = []
    for line in lines[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, command, cpu, mem = parts
        processes.append(
            {
                "pid": int(pid),
                "command": command,
                "cpu": float(cpu),
                "mem": float(mem),
            }
        )
    return processes


def _parse_postgres_databases(raw: str) -> List[Dict[str, str]]:
    databases = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            name, size = parts
            databases.append({"name": name.strip(), "size": size.strip()})
        else:
            databases.append({"name": line.strip(), "size": "-"})
    return databases


def _fetch_postgres_databases(client: paramiko.SSHClient) -> Dict[str, object]:
    if not POSTGRES_LIST_CMD:
        return {"databases": [], "error": "POSTGRES_LIST_DB_CMD não configurado"}

    try:
        raw = _run_command(client, POSTGRES_LIST_CMD, timeout=15)
        return {"databases": _parse_postgres_databases(raw), "error": None}
    except Exception as exc:  # pylint: disable=broad-except
        return {"databases": [], "error": str(exc)}


def _extract_system_name(command_text: str) -> str:
    """
    Extrai o nome do sistema/pasta a partir do comando do processo.
    Exemplo: '/usr/bin/python3 /path/to/sistema/main.py' -> 'sistema'
    """
    # Procura por padrões de caminho de arquivo Python
    patterns = [
        r'python\d*\s+([^\s]+/([^/]+)\.(py|pyw))',  # python /path/to/system/file.py
        r'python\d*\s+([^\s]+/([^/]+))$',           # python /path/to/system
        r'cd\s+([^\s]+);\s*python',                 # cd /path/to/system; python
        r'python.*-m\s+([^\s]+)',                   # python -m module.name
    ]
    
    for pattern in patterns:
        match = re.search(pattern, command_text, re.IGNORECASE)
        if match:
            if len(match.groups()) >= 2:
                return match.group(2)  # Nome do arquivo ou pasta
            elif len(match.groups()) >= 1:
                return match.group(1)  # Módulo ou caminho completo
    
    # Se não encontrar padrão, tenta extrair do último argumento
    parts = command_text.split()
    if len(parts) > 1:
        last_part = parts[-1]
        if '/' in last_part:
            return last_part.split('/')[-1].replace('.py', '')
        elif '.' in last_part and not last_part.startswith('.'):
            return last_part.split('.')[0]
    
    return "Desconhecido"


def _resolve_process_cwd(client: paramiko.SSHClient, pid: int) -> Optional[str]:
    """Resolve o diretório atual de um processo remoto."""
    command = f"if [ -e /proc/{pid}/cwd ]; then readlink -f /proc/{pid}/cwd; fi"
    try:
        raw = _run_command(client, command, timeout=5).strip()
        return raw or None
    except Exception:  # pylint: disable=broad-except
        return None


def _fetch_python_processes(client: paramiko.SSHClient) -> Dict[str, object]:
    command = DEFAULT_PYTHON_PROCESS_CMD
    try:
        raw = _run_command(client, command, timeout=15)
    except Exception as exc:  # pylint: disable=broad-except
        return {"processes": [], "error": str(exc)}

    processes = []
    for line in raw.splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, cpu, mem, command_text = parts
        if "python" not in command_text.lower():
            continue
        
        # Excluir processos do próprio sistema de monitoramento
        # Verifica se o caminho contém indicadores do sistema atual
        if any(indicator in command_text.lower() for indicator in [
            "monitor", "nexus_sistemas", "app.py", "gerenciador-d-vps"
        ]):
            continue
        
        system_path = _resolve_process_cwd(client, int(pid))
        system_name = (
            posixpath.basename(system_path.rstrip("/")) if system_path else _extract_system_name(command_text)
        ) or _extract_system_name(command_text)
            
        processes.append(
            {
                "pid": int(pid),
                "cpu": float(cpu),
                "mem": float(mem),
                "command": command_text,
                "system_name": system_name,
                "system_path": system_path,
            }
        )
        if len(processes) >= 10:
            break

    return {"processes": processes, "error": None}


_START_FILE_PRIORITY = ["start.sh", "run.py", "main.py", "app.py", "manage.py"]


def _scan_project_directories(client: paramiko.SSHClient, base_path: str) -> List[Dict]:
    """
    Varre subpastas de base_path, detecta arquivos de start e retorna lista de apps.
    Apenas subpastas que contenham um arquivo de start reconhecido são incluídas.
    Faz uma única chamada SSH.
    """
    priorities = " ".join(_START_FILE_PRIORITY)
    safe_base = shlex.quote(base_path)
    # Tenta nomes conhecidos primeiro; se não achar, pega o primeiro .py da pasta raiz
    script = (
        f"for dir in {safe_base}/*/; do "
        '[ -d "$dir" ] || continue; '
        'dir="${dir%/}"; '
        'name="${dir##*/}"; '
        'sf=""; '
        f"for f in {priorities}; do "
        '[ -f "$dir/$f" ] && sf=$f && break; '
        "done; "
        '[ -z "$sf" ] && sf=$(ls "$dir"/*.py 2>/dev/null | head -1 | xargs -I{} basename {}); '
        '[ -n "$sf" ] && echo "$name|$dir|$sf"; '
        "done"
    )
    command = f"bash -c {shlex.quote(script)}"
    try:
        raw = _run_command(client, command, timeout=15).strip()
    except Exception:  # pylint: disable=broad-except
        return []

    projects = []
    for line in raw.splitlines():
        if "|" not in line:
            continue
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        name, path, start_file = parts
        projects.append(
            {
                "name": name.strip(),
                "path": path.strip(),
                "start_file": start_file.strip() or None,
            }
        )
    return projects


def _build_applications_list(
    running_processes: List[Dict], scanned_dirs: List[Dict]
) -> List[Dict]:
    """
    Mescla processos rodando com diretórios escaneados.
    Retorna lista unificada com status 'running' ou 'stopped'.
    """
    running_by_path: Dict[str, Dict] = {
        proc["system_path"]: proc
        for proc in running_processes
        if proc.get("system_path")
    }

    applications: List[Dict] = []
    scanned_paths: set = set()

    for dir_info in scanned_dirs:
        path = dir_info["path"]
        scanned_paths.add(path)
        proc = running_by_path.get(path)
        app: Dict = {
            "name": dir_info["name"],
            "path": path,
            "start_file": dir_info["start_file"],
            "status": "running" if proc else "stopped",
            "pid": proc["pid"] if proc else None,
            "cpu": proc["cpu"] if proc else None,
            "mem": proc["mem"] if proc else None,
            "command": proc["command"] if proc else None,
        }
        applications.append(app)

    # Processos rodando que não estão em nenhum dir escaneado
    for proc in running_processes:
        if proc.get("system_path") not in scanned_paths:
            applications.append(
                {
                    "name": proc["system_name"],
                    "path": proc.get("system_path"),
                    "start_file": None,
                    "status": "running",
                    "pid": proc["pid"],
                    "cpu": proc["cpu"],
                    "mem": proc["mem"],
                    "command": proc["command"],
                }
            )

    return applications


def _run_remote_shell(command: str, timeout: int = 30) -> str:
    client = _get_ssh_client()
    try:
        return _run_command(client, command, timeout)
    finally:
        client.close()


def _build_update_command() -> str:
    if APP_UPDATE_COMMAND:
        return APP_UPDATE_COMMAND
    if not APP_GIT_PATH:
        raise RuntimeError("APP_GIT_PATH não configurado")
    return f"cd {APP_GIT_PATH} && git pull --ff-only"


def trigger_update_application() -> str:
    command = _build_update_command()
    return _run_remote_shell(command)


def _stream_remote_command(command: str, intro: Optional[str] = None, timeout: int = 180) -> Response:
    def generate():
        if intro:
            yield intro + "\n"
        client = _get_ssh_client()
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            stdin.close()
            while True:
                line = stdout.readline()
                if not line:
                    break
                yield line if line.endswith("\n") else f"{line}\n"
            error = stderr.read().decode("utf-8")
            if error.strip():
                yield f"[erro] {error}\n"
            yield "Concluído.\n"
        finally:
            client.close()

    response = Response(stream_with_context(generate()), mimetype="text/plain")
    response.headers["X-Accel-Buffering"] = "no"
    return response


def _build_project_update_command(system_path: str) -> str:
    if not system_path:
        raise ValueError("Caminho do projeto é obrigatório")
    if not system_path.startswith("/"):
        raise ValueError("Caminho do projeto inválido")

    safe_path = shlex.quote(system_path)
    return f"cd {safe_path} && git pull --ff-only"


def trigger_update_project(system_path: str) -> str:
    command = _build_project_update_command(system_path)
    return _run_remote_shell(command)


def _build_restart_script(pid: int, system_path: str, command_text: str) -> str:
    if pid <= 0:
        raise ValueError("PID inválido")
    if not system_path:
        raise ValueError("Caminho do projeto é obrigatório")
    if not command_text:
        raise ValueError("Comando do processo é obrigatório")

    safe_path = shlex.quote(system_path)
    safe_cmd = shlex.quote(command_text)

    script = f"""
set -euo pipefail
PID={pid}
WORKDIR={safe_path}
COMMAND={safe_cmd}
echo "Parando processo $PID..."
if kill -0 $PID 2>/dev/null; then
    kill $PID
    COUNT=0
    while kill -0 $PID 2>/dev/null && [ $COUNT -lt 15 ]; do
        sleep 1
        COUNT=$((COUNT + 1))
    done
    if kill -0 $PID 2>/dev/null; then
        echo "Forçando parada após timeout..."
        kill -9 $PID
    fi
else
    echo "Processo já não está em execução."
fi
echo "Iniciando novamente em $WORKDIR..."
cd $WORKDIR
nohup bash -lc $COMMAND >/tmp/restart_$PID.log 2>&1 &
NEW_PID=$!
echo "Novo PID: $NEW_PID"
sleep 1
if [ -f /tmp/restart_$PID.log ]; then
    echo "Últimas linhas do log:"
    tail -n 20 /tmp/restart_$PID.log || true
fi
""".strip()

    return f"bash -lc {shlex.quote(script)}"


def trigger_restart_application() -> str:
    if not APP_RESTART_COMMAND:
        raise RuntimeError("APP_RESTART_COMMAND não configurado")
    return _run_remote_shell(APP_RESTART_COMMAND)


def collect_metrics() -> Dict[str, object]:
    client = _get_ssh_client()
    try:
        uptime = _run_command(client, "uptime -p")
        load_avg_raw = _run_command(client, "cat /proc/loadavg").split()
        load_avg = [float(value) for value in load_avg_raw[:3]]

        memory_raw = _run_command(client, "free -m")
        memory_info = _parse_memory_info(memory_raw)
        swap_info = _parse_swap_info(memory_raw)
        memory_info["usage_percent"] = _calc_percent(memory_info["used"], memory_info["total"])
        swap_info["usage_percent"] = _calc_percent(swap_info["used"], swap_info["total"])

        disk_raw = _run_command(client, "df -h /")
        disk_info = _parse_disk_info(disk_raw)
        disk_info["usage_percent_value"] = float(disk_info["use_percent"].rstrip("%"))

        processes_raw = _run_command(
            client,
            "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -n 6",
        )
        processes = _parse_processes(processes_raw)

        hostname = _run_command(client, "hostname")
        kernel = _run_command(client, "uname -sr")
        postgres = _fetch_postgres_databases(client)
        python_processes = _fetch_python_processes(client)

        scanned_dirs = (
            _scan_project_directories(client, PROJECTS_BASE_PATH)
            if PROJECTS_BASE_PATH
            else []
        )
        applications = _build_applications_list(python_processes["processes"], scanned_dirs)

        return {
            "hostname": hostname,
            "kernel": kernel,
            "uptime": uptime,
            "load_average": load_avg,
            "memory": memory_info,
            "swap": swap_info,
            "disk": disk_info,
            "processes": processes,
            "postgres": postgres,
            "python_processes": python_processes,
            "applications": applications,
            "projects_base_path": PROJECTS_BASE_PATH,
            "retrieved_at": datetime.utcnow().isoformat() + "Z",
            "can_restart": bool(APP_RESTART_COMMAND),
        }
    finally:
        client.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"status": "error", "message": "Não autorizado"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        error = "Usuário ou senha incorretos."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/")
@login_required
def dashboard():
    try:
        metrics = collect_metrics()
        return render_template(
            "index.html",
            metrics=metrics,
            vps_identifier=VPS_IDENTIFIER,
            ssh_info=_serialize_ssh_info(),
            error=None,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return render_template(
            "index.html",
            metrics=None,
            vps_identifier=VPS_IDENTIFIER,
            ssh_info=_serialize_ssh_info(),
            error=str(exc),
        ), 500


@app.route("/api/status")
@login_required
def api_status():
    try:
        metrics = collect_metrics()
        return jsonify({"status": "ok", "data": metrics})
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.post("/api/actions/update")
@login_required
def api_update_app():
    try:
        output = trigger_update_application()
        return jsonify({"status": "ok", "message": output})
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.post("/api/actions/update-project/logs")
@login_required
def api_update_project_logs():
    payload = request.get_json(silent=True) or {}
    system_path = payload.get("path")
    try:
        command = _build_project_update_command(system_path)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return _stream_remote_command(
        command,
        intro=f"Atualizando projeto {system_path}",
    )


@app.post("/api/actions/restart-project/logs")
@login_required
def api_restart_project_logs():
    payload = request.get_json(silent=True) or {}
    system_path = payload.get("path")
    command_text = payload.get("command")
    pid = payload.get("pid")
    try:
        pid_int = int(pid)
        command = _build_restart_script(pid_int, system_path, command_text)
    except (TypeError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return _stream_remote_command(
        command,
        intro=f"Reiniciando processo {pid_int} em {system_path}",
        timeout=240,
    )


@app.post("/api/actions/update-project")
@login_required
def api_update_project():
    payload = request.get_json(silent=True) or {}
    system_path = payload.get("path")
    try:
        output = trigger_update_project(system_path)
        return jsonify({"status": "ok", "message": output})
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"status": "error", "message": str(exc)}), 500


def _build_clone_command(repo_url: str, folder_name: str, base_path: str) -> str:
    if not re.match(r'^[\w\-]+$', folder_name):
        raise ValueError("Nome da pasta inválido (use apenas letras, números e hífens)")
    if not re.match(r'^https?://|^git@', repo_url):
        raise ValueError("URL do repositório inválida")

    safe_base = shlex.quote(base_path)
    safe_folder = shlex.quote(folder_name)
    safe_url = shlex.quote(repo_url)

    script = f"""set -euo pipefail
TARGET={safe_base}/{safe_folder}
if [ -d "$TARGET" ]; then
    echo "ERRO: A pasta $TARGET já existe."
    exit 1
fi
echo "Clonando {repo_url} em $TARGET..."
git clone {safe_url} "$TARGET"
echo "Clone concluido com sucesso."
""".strip()

    return f"bash -lc {shlex.quote(script)}"


def _build_start_script(system_path: str, start_file: str) -> str:
    if not system_path or not start_file:
        raise ValueError("Caminho e arquivo de inicialização são obrigatórios")
    if not system_path.startswith("/"):
        raise ValueError("Caminho do projeto inválido")
    if not re.match(r'^[\w\-]+\.(py|sh)$', start_file):
        raise ValueError(f"Arquivo de start inválido: {start_file}")

    safe_path = shlex.quote(system_path)
    log_name = posixpath.basename(system_path.rstrip("/"))
    log_file = f"/tmp/app_{log_name}.log"

    if start_file.endswith(".py"):
        run_cmd = f"python3 {shlex.quote(start_file)}"
    else:
        run_cmd = f"bash {shlex.quote(start_file)}"

    script = f"""set -euo pipefail
cd {safe_path}
echo "Iniciando {log_name} com {start_file}..."
nohup {run_cmd} >{shlex.quote(log_file)} 2>&1 &
NEW_PID=$!
echo "PID: $NEW_PID"
sleep 2
if kill -0 $NEW_PID 2>/dev/null; then
    echo "Processo iniciado com sucesso (PID $NEW_PID)."
    echo "Ultimas linhas do log:"
    tail -n 20 {shlex.quote(log_file)} || true
else
    echo "ERRO: processo terminou inesperadamente."
    cat {shlex.quote(log_file)} || true
fi""".strip()

    return f"bash -lc {shlex.quote(script)}"


def _build_process_log_command(pid: int) -> str:
    return (
        f"journalctl --follow --pid={pid} -n 100 2>/dev/null"
        f" || tail -f -n 100 /tmp/restart_{pid}.log 2>/dev/null"
        f" || echo 'Nenhum log disponivel para o processo {pid}'"
    )


@app.post("/api/actions/clone-project/logs")
@login_required
def api_clone_project_logs():
    payload = request.get_json(silent=True) or {}
    repo_url = payload.get("repo_url", "").strip()
    folder_name = payload.get("folder_name", "").strip()
    try:
        command = _build_clone_command(repo_url, folder_name, PROJECTS_BASE_PATH)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return _stream_remote_command(
        command,
        intro=f"Clonando {repo_url}",
        timeout=120,
    )


@app.post("/api/actions/start-project/logs")
@login_required
def api_start_project_logs():
    payload = request.get_json(silent=True) or {}
    system_path = payload.get("path")
    start_file = payload.get("start_file")
    try:
        command = _build_start_script(system_path, start_file)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    name = posixpath.basename((system_path or "").rstrip("/"))
    return _stream_remote_command(
        command,
        intro=f"Iniciando {name} com {start_file}",
        timeout=60,
    )


@app.post("/api/actions/process-logs")
@login_required
def api_process_logs():
    payload = request.get_json(silent=True) or {}
    pid = payload.get("pid")
    try:
        pid_int = int(pid)
        if pid_int <= 0:
            raise ValueError("PID inválido")
    except (TypeError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    command = _build_process_log_command(pid_int)
    return _stream_remote_command(command, intro=f"Logs do processo {pid_int}", timeout=300)


@app.post("/api/actions/restart")
@login_required
def api_restart_app():
    try:
        output = trigger_restart_application()
        return jsonify({"status": "ok", "message": output})
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"status": "error", "message": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
