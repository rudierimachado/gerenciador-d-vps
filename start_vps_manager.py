#!/usr/bin/env python3
"""
VPS Manager Pro - Inicializador
Inicia o sistema com verificações e tratamento de erros
"""

import os
import sys
import subprocess
import socket
import time
import webbrowser
from pathlib import Path

def verificar_dependencias():
    """Verifica se todas as dependências estão instaladas"""
    dependencias = [
        'flask',
        'flask_socketio', 
        'paramiko',
        'python-dotenv'
    ]
    
    faltando = []
    for dep in dependencias:
        try:
            __import__(dep.replace('-', '_'))
        except ImportError:
            faltando.append(dep)
    
    if faltando:
        print("ERRO: Dependencias faltando:")
        for dep in faltando:
            print(f"   - {dep}")
        print("\nInstale com: pip install " + " ".join(faltando))
        return False
    
    print("OK: Todas as dependencias estao instaladas")
    return True

def verificar_arquivo_env():
    """Verifica se o arquivo .env existe e tem as configurações necessárias"""
    env_path = Path('.env')
    
    if not env_path.exists():
        print("ERRO: Arquivo .env nao encontrado")
        print("Crie um arquivo .env com:")
        print("   SSH_HOST=seu-vps-ip")
        print("   SSH_USER=root")
        print("   SSH_PASSWORD=sua-senha")
        print("   SSH_PORT=22")
        return False
    
    # Verifica conteúdo básico
    content = env_path.read_text()
    required = ['SSH_HOST', 'SSH_USER', 'SSH_PASSWORD']
    
    for req in required:
        if req not in content:
            print(f"ERRO: Configuracao {req} nao encontrada no .env")
            return False
    
    print("OK: Arquivo .env configurado")
    return True

def encontrar_porta_disponivel(porta_inicial=5002):
    """Encontra uma porta disponível"""
    for porta in range(porta_inicial, porta_inicial + 10):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', porta))
                return porta
        except OSError:
            continue
    return None

def matar_processos_antigos():
    """Mata processos antigos do VPS Manager"""
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['taskkill', '/F', '/IM', 'python.exe', '/FI', 'WINDOWTITLE eq VPS*'], 
                         capture_output=True, check=False)
        else:  # Linux/Mac
            subprocess.run(['pkill', '-f', 'gerenciador_servicos.py'], 
                         capture_output=True, check=False)
    except:
        pass

def main():
    print("VPS Manager Pro - Inicializador")
    print("=" * 50)
    
    # Verificações
    if not verificar_dependencias():
        input("\nPressione Enter para sair...")
        return
    
    if not verificar_arquivo_env():
        input("\nPressione Enter para sair...")
        return
    
    # Mata processos antigos
    print("Verificando processos antigos...")
    matar_processos_antigos()
    time.sleep(1)
    
    # Encontra porta disponível
    porta = encontrar_porta_disponivel()
    if not porta:
        print("ERRO: Nao foi possivel encontrar uma porta disponivel!")
        input("Pressione Enter para sair...")
        return
    
    print(f"OK: Porta {porta} disponivel")
    
    # Inicia o servidor
    print("Iniciando VPS Manager Pro...")
    print(f"URL: http://localhost:{porta}")
    print("=" * 50)
    
    try:
        # Abre o navegador após 2 segundos
        def abrir_navegador():
            time.sleep(2)
            try:
                webbrowser.open(f'http://localhost:{porta}')
            except:
                pass
        
        import threading
        threading.Thread(target=abrir_navegador, daemon=True).start()
        
        # Inicia o servidor
        os.environ['VPS_MANAGER_PORT'] = str(porta)
        subprocess.run([sys.executable, 'gerenciador_servicos.py'], check=True)
        
    except KeyboardInterrupt:
        print("\n\nVPS Manager Pro encerrado pelo usuario")
    except Exception as e:
        print(f"\nERRO ao iniciar: {e}")
        input("Pressione Enter para sair...")

if __name__ == '__main__':
    main()