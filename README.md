# Monitoramento VPS HXVTDiwjVGEph3bAbkSFncQyFwWJ6keq2tnsWTGK4589be83

Aplicação Flask para coletar métricas em tempo real de uma VPS via SSH e exibi-las em um painel web responsivo.

## Requisitos

- Python 3.10+
- Dependências listadas em `requirements.txt`
- Variáveis de ambiente com credenciais SSH no arquivo `.env`

## Configuração

1. Crie um ambiente virtual (opcional, porém recomendado):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
2. Instale as dependências:
   ```powershell
   pip install -r requirements.txt
   ```
3. Configure o arquivo `.env` com as credenciais da VPS:
   ```env
   SSH_HOST=seu_ip
   SSH_PORT=22
   SSH_USER=root
   SSH_PASSWORD=senha
   ```

## Execução

```powershell
python app.py
```

A aplicação estará disponível em `http://localhost:5000`. O painel recarrega automaticamente a cada 60 segundos e permite atualização manual via botão "Atualizar agora".

## Estrutura

- `app.py`: lógica Flask e coleta de métricas via Paramiko.
- `templates/index.html`: painel HTML com Jinja2.
- `static/style.css`: estilos do dashboard.
- `requirements.txt`: dependências do projeto.

## Segurança

- Não comite o arquivo `.env`.
- Prefira configurar variáveis de ambiente diretamente no servidor de produção.
