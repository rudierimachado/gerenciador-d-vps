#!/usr/bin/env python3
"""
VPS Manager Pro - Executar
Script simples para iniciar o sistema
"""

import subprocess
import sys
import os
import webbrowser
import time
import threading

def abrir_navegador():
    """Abre o navegador após 3 segundos"""
    time.sleep(3)
    try:
        webbrowser.open('http://localhost:5002')
    except:
        pass

def main():
    print("VPS Manager Pro")
    print("=" * 30)
    print("Iniciando servidor...")
    
    # Thread para abrir navegador
    threading.Thread(target=abrir_navegador, daemon=True).start()
    
    try:
        # Executa o gerenciador de serviços
        subprocess.run([sys.executable, 'gerenciador_servicos.py'], check=True)
    except KeyboardInterrupt:
        print("\nServidor encerrado pelo usuario")
    except Exception as e:
        print(f"Erro: {e}")
        input("Pressione Enter para sair...")

if __name__ == '__main__':
    main()