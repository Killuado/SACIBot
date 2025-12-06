# 🛒 SACIBot — Sistema Automático de Monitoramento e Boletagem de Promoções

SACIBot é um sistema integrado composto por um **back-end em Python/Django** e um **bot do Discord**, projetado para monitorar promoções de marketplaces, lives promocionais e grupos do Telegram, identificar produtos desejados através de expressões regulares e **boletar automaticamente** ofertas que atendam ao interesse de cada usuário.

O objetivo principal é automatizar todo o fluxo de descoberta, notificação e compra rápida de produtos em promoção.

---

## 📌 Sumário

* [Visão Geral](#visão-geral)
* [Arquitetura do Sistema](#arquitetura-do-sistema)
* [Funcionalidades Principais](#funcionalidades-principais)
* [Fluxo Completo do Sistema](#fluxo-completo-do-sistema)
* [Back-end (Django)](#back-end-django)
* [Bot do Discord](#bot-do-discord)
* [Watchlist do Usuário](#watchlist-do-usuário)
* [Websocket entre Bot e Servidor](#websocket-entre-bot-e-servidor)
* [Sistema de Re-Tentativa | Fila de Estoque Zerado](#sistema-de-re-tentativa--fila-de-estoque-zerado)
* [Banco de Dados](#banco-de-dados)
* [Configurações e Intervalos](#configurações-e-intervalos)
* [Tecnologias Usadas](#tecnologias-usadas)
* [Como Rodar o Projeto](#como-rodar-o-projeto)
* [Licença](#licença)

---

# 📖 Visão Geral

O SACIBot combina um **bot do Discord** com um **servidor Django rodando em VPS** para:

* Monitorar lives promocionais e grupos de Telegram.
* Coletar cupons, preços e produtos.
* Aplicar regex da watchlist de cada usuário em todas promoções encontradas.
* Avisar o usuário via Discord quando houver correspondência.
* Boletar automaticamente ofertas compatíveis com o preço desejado.
* Manter uma fila de re-tentativa para ofertas esgotadas.

Cada usuário possui:

* Sua própria **watchlist** (com regex + preço máximo).
* Seu próprio **endereço cadastrado**.
* Suas configurações individuais via bot.

---

# 🧩 Arquitetura do Sistema

```
          ┌───────────────────────────┐
          │        Usuário            │
          │       (Discord)           │
          └─────────────▲─────────────┘
                        │ Comandos
                        │
        ┌───────────────┴────────────────┐
        │         Bot do Discord          │
        │  - Watchlist por usuário        │
        │  - Cadastro de endereço         │
        │  - Config. de marketplace       │
        │  - Integração via WebSocket     │
        └───────────────▲────────────────┘
                        │ WS
                        │
          ┌─────────────┴────────────────┐
          │ Servidor Back-end (Django)    │
          │  - Webscraping                │
          │  - Compra automática          │
          │  - Monitor de lives           │
          │  - Leitura de grupos Telegram │
          │  - Banco de dados             │
          │  - Fila de re-tentativa       │
          └─────────────▲────────────────┘
                        │ Retornos
                        │
          ┌─────────────┴─────────────────┐
          │           Marketplaces         │
          │        Lives e Grupos TG       │
          └───────────────────────────────┘
```

---

# ⚙️ Funcionalidades Principais

### ✔ Discord Bot

* Cadastro de endereço por usuário.
* Criação e gerenciamento de Watchlists.
* Watchlist baseada em Regex.
* Definição de preço máximo por produto.
* Integração com o back-end via WebSocket.
* Configuração de canais de marketplace permitidos.
* Exibição de promoções recebidas do servidor.

### ✔ Back-end em Django

* Webscraping automático.
* Boletagem automática de produtos compatíveis.
* Monitoramento de lives promocionais.
* Leitura de grupos de Telegram.
* Armazenamento de promoções por 3 dias.
* Limpeza automática de banco.
* Fila de re-tentativa para promoções esgotadas.
* Envio de notificações ao bot via WebSocket.

---

# 🔄 Fluxo Completo do Sistema

### **1. Usuário adiciona um item na Watchlist via Discord**

* Regex + preço máximo.
* Bot envia via API/WS para o servidor.

### **2. Back-end detecta promoções**

* Monitora lives a cada 10 minutos.
* Lê grupos do Telegram continuamente.
* Faz webscraping nos links coletados.

### **3. Servidor salva promoções no Banco**

* Com data de armazenamento.
* Limpa automaticamente a cada 3 dias.

### **4. Servidor aplica Watchlist de todos os usuários**

* Regex matching.
* Verificação de preço.

### **5. Se o preço for menor/igual ao limite do usuário → boletar**

* Back-end tenta comprar automaticamente.
* Resultado é enviado ao bot.

### **6. Discord envia mensagem ao usuário**

* Promoção encontrada.
* Se boletado: confirmação da compra.

### **7. Caso o estoque esteja zerado**

* Promoção entra na fila.
* Servidor re-tenta boletar conforme intervalo configurado por marketplace.

---

# 🧱 Back-end (Django)

### Principais responsabilidades:

* Realizar o webscraping.
* Registrar novas promoções.
* Verificar compatibilidade com Watchlist.
* Boletar automaticamente produtos compatíveis.
* Monitorar lives e grupos de Telegram.
* Armazenar cupons e promoções.
* Expor interface WebSocket para o bot.
* Rodar limpadores periódicos (celery/cron).
* Fazer re-tentativas quando estoque estiver zerado.

### Tarefas periódicas:

* **Cada 10 minutos:** buscar novas lives.
* **Cada X segundos (por marketplace):** tentar novamente promoções esgotadas.
* **A cada 3 dias:** limpar promoções antigas.

---

# 🤖 Bot do Discord

### O bot implementa as seguintes funcionalidades:

#### 📌 Comandos de Watchlist

```
/watchlist add <regex> <preço_max>
/watchlist list
/watchlist remove <id>
```

#### 📌 Comandos de Endereço

```
/endereco set <dados>
/endereco show
```

#### 📌 Configurações de Marketplace

```
/marketplace allow add <canal>
/marketplace allow remove <canal>
/marketplace allow list
```

#### 📌 Gerenciamento e Integração

* Todos os comandos enviam requisições ao back-end.
* O bot mantém WebSocket aberto com o servidor.
* Sempre que uma promoção nova for correspondente ao usuário → mensagem no Discord.

---

# 📝 Watchlist do Usuário

A Watchlist consiste em:

| Campo            | Tipo     | Descrição                                                |
| ---------------- | -------- | -------------------------------------------------------- |
| Regex do produto | string   | Identifica nomes e descrições compatíveis com a promoção |
| Preço máximo     | float    | Apenas notifica/boleta se o preço for menor/igual        |
| Usuário Discord  | int      | ID único do usuário                                      |
| Data de criação  | datetime | Controle interno                                         |

### Exemplo:

```
Regex: (rtx\s?4060|4060ti|rtx\s?4070)
Preço máximo: 2100.00
```

---

# 🔌 Websocket entre Bot e Servidor

O WebSocket é utilizado para:

### O servidor envia:

* Promoções compatíveis por usuário.
* Resultado das tentativas de boletagem.
* Informações sobre falha, estoque ou cupons.

### O bot recebe:

* Mensagem final formatada.
* Dados da promoção.
* Link direto para oferta.
* Informações de boletagem.

---

# 🔁 Sistema de Re-Tentativa | Fila de Estoque Zerado

Se a promoção estiver **esgotada**:

1. Servidor detecta falta de estoque.
2. Promoção vai para fila de re-tentativa.
3. Servidor tenta boletear novamente a cada X segundos.
4. X é configurado por marketplace via bot do Discord.
5. Quando o estoque volta:

   * Promo é boletada.
   * Usuário recebe alerta via bot.

---

# 🗄 Banco de Dados

Estruturas principais:

* **Users**
* **Watchlist**
* **Addresses**
* **MarketplaceChannels**
* **Promotions**
* **Coupons**
* **RetryQueue**
* **LiveSources**

Dados de promoções são purgados a cada 3 dias para evitar acúmulo.

---

# 🛠 Tecnologias Usadas

### Back-end

* Python 3.x
* Django
* Django Rest Framework
* Websockets / Django Channels
* Celery + Redis
* BeautifulSoup / Playwright / Selenium
* PostgreSQL

### Bot do Discord

* Python
* discord.py (ou pycord)
* WebSockets
* Sistema de cache interno

### Infra

* VPS Linux
* Docker (opcional)
* Nginx
* Systemd services

---

# 🚀 Como Rodar o Projeto

### Back-end

```bash
git clone <repo>
cd SACIBot/backend

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Bot do Discord

```bash
cd SACIBot/discord-bot

pip install -r requirements.txt
python bot.py
```

---

# 📜 Licença

Este projeto é disponibilizado sob a licença MIT.
Sinta-se livre para usar, estudar, modificar e melhorar.

---

Se quiser, posso criar também:

✅ estrutura de pastas
✅ exemplo real de `models.py`
✅ exemplo de WebSocket server
✅ comandos do bot em Python
✅ diagramas PNG para colocar no GitHub
✅ documentação separada em arquivos (`docs/`)

Só pedir!
