# Guia de produção

Como colocar o ConvencendoAI no ar em um servidor (VPS), de duas formas:

- **Parte A, VPS manual:** você prepara o servidor, instala o Docker e sobe o sistema com o
  `docker-compose.prod.yml`. É o caminho para **aprender** o que existe por baixo de qualquer painel.
- **Parte B, Dokploy:** um painel instalado na VPS que faz o deploy a partir do GitHub, cuida do
  certificado e agenda o backup. Usa o `docker-compose.dokploy.yml`.

A ordem recomendada é fazer a **Parte A primeiro**, com usuários de teste, e a Parte B depois, numa
VPS limpa. O que você aprende na A (SSH, firewall, Docker, DNS, certificado) é exatamente o que o
Dokploy esconde, e é por ali que se descobre o problema quando algo falha.

Os nomes de menu do Dokploy e da Contabo podem mudar um pouco entre versões. Quando um passo não
bater com a tela, vale a documentação oficial deles.

---

## 0. Como as peças se encaixam

### O que roda no servidor

```
 Aluno (navegador, microfone exige HTTPS)
        │  https://app.seu-dominio.com.br
        ▼
 ┌────────────────────┐
 │ Proxy com TLS       │  Parte A: Caddy (no compose)
 │ (80 e 443)          │  Parte B: Traefik (do Dokploy)
 └─────────┬──────────┘
           ▼
 ┌────────────────────┐
 │ convencendoai-web   │  nginx sem root: entrega o React e repassa
 │ (porta 8080)        │  /api  /admin  /static  /ws  para a API
 └─────────┬──────────┘
           ▼
 ┌────────────────────┐        ┌────────────────────┐
 │ convencendoai-api   │──────► │ Postgres            │  Parte A: serviço db do compose
 │ Django + gunicorn   │        │ (porta 5432 interna)│  Parte B: serviço de banco do Dokploy
 └────────────────────┘        └────────────────────┘
           │
           ▼  chaves vindas do ambiente do servidor
     Groq, Google e Ollama Cloud (internet)
```

Só o proxy fica exposto à internet. A API e o banco nunca publicam porta.

### Os dois proxies e o IP do aluno

Entre o aluno e a API há **dois** proxies (o de TLS e o nginx). Cada um acrescenta o IP de quem falou
com ele ao `X-Forwarded-For`, e o backend lê a lista a partir do fim, por isso o compose fixa
`TRUSTED_PROXY_COUNT=2`. É isso que faz o bloqueio de login (5 erros, 15 minutos) olhar o IP do
aluno e não o do proxy. Se você acrescentar mais um proxy na frente, esse número muda.

### Quando usar cada compose

| Arquivo | Para quê |
|---|---|
| `docker-compose.dev.yml` | Desenvolvimento na sua máquina (já existente). |
| `docker-compose.prod.yml` | **VPS manual.** Tem tudo: banco, API, web e Caddy com TLS automático. |
| `docker-compose.dokploy.yml` | **Dokploy.** Só API e web; o Postgres é um serviço do Dokploy e o TLS é do Traefik. |
| `docker-compose.dokploy.local.yml` | Testar na sua máquina a pilha do Dokploy, com um Postgres descartável. |

### Variáveis

- Manual: copie `.env.prod.example` para `.env` no servidor.
- Dokploy: cole as variáveis na aba **Environment** do serviço (lista na Parte B).

O `.env` real **nunca** vai para o git. As chaves dos provedores de IA vivem só nele: o banco guarda
apenas o nome da variável.

---

## Parte A. VPS manual

Tempo estimado: uma tarde, se for a primeira vez. Cada passo tem um "como saber que deu certo".

### A1. Contratar a VPS

1. Plano básico da Contabo (Cloud VPS), **Ubuntu 24.04 LTS**, região dos EUA (menor latência para os
   provedores de IA). 2 GB de RAM já roda, mas o build do frontend fica mais tranquilo com 4 GB.
2. Gere sua chave SSH no Windows (PowerShell) e **cadastre a chave pública** no painel da Contabo
   quando ele oferecer, em vez de usar senha:

   ```powershell
   ssh-keygen -t ed25519 -C "convencendoai-vps"
   Get-Content $HOME\.ssh\id_ed25519.pub
   ```

   O arquivo `id_ed25519` (sem `.pub`) é a chave **privada**: nunca sai da sua máquina.
3. Anote o IP que o painel mostrar.

Como saber que deu certo: `ssh root@IP-DA-VPS` entra sem pedir senha.

### A2. Atualizar e criar um usuário sem privilégio

Trabalhar como root o tempo todo é o erro mais comum. Crie um usuário `deploy`:

```bash
apt update && apt upgrade -y
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
reboot
```

Como saber que deu certo: `ssh deploy@IP-DA-VPS` entra, e `sudo whoami` responde `root`.

### A3. Fechar o SSH

Ainda logado como `deploy`, **mantenha uma segunda janela de terminal aberta** durante este passo: se
errar a configuração, ela é a sua porta de volta.

```bash
sudo tee /etc/ssh/sshd_config.d/00-hardening.conf > /dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sudo sshd -t
sudo systemctl restart ssh
sudo sshd -T | grep -E "passwordauthentication|permitrootlogin"
```

O arquivo se chama `00-` para ser lido **primeiro**: o `sshd` vale o primeiro valor que encontra, e
a imagem da Contabo pode trazer um arquivo `50-cloud-init.conf` com `PasswordAuthentication yes`.

Como saber que deu certo: a última linha mostra `passwordauthentication no` e
`permitrootlogin no`, e `ssh root@IP` agora é recusado.

### A4. Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

> **Armadilha do Docker:** porta **publicada** por um container (`ports:` no compose) passa por fora
> do `ufw`. No `docker-compose.prod.yml` só o Caddy publica porta, e são justamente a 80 e a 443.
> Nunca publique `5432` (banco) nem a porta da API num compose: o `ufw` não vai te proteger.

Opcional, mas barato: `sudo apt install -y fail2ban` (o bloqueio de tentativas de SSH já vem ligado)
e `sudo apt install -y unattended-upgrades` seguido de
`sudo dpkg-reconfigure -plow unattended-upgrades` para atualizações de segurança automáticas.

### A5. Instalar o Docker

Pelo repositório oficial (não pelo pacote `docker.io` da distribuição):

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker deploy
```

Impeça os logs dos containers de encherem o disco (o log do gunicorn cresce para sempre por padrão):

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}
EOF
sudo systemctl restart docker
```

Saia e entre de novo no SSH (para o grupo `docker` valer).

Como saber que deu certo: `docker run --rm hello-world` imprime a mensagem de boas-vindas, e
`docker compose version` responde.

### A6. Domínio

1. Registre o domínio (Registro.br para `.com.br`, ou outro registrador).
2. Crie um registro **A** apontando um nome (por exemplo `app`) para o IP da VPS.
3. Espere propagar. Do seu computador: `nslookup app.seu-dominio.com.br` deve devolver o IP da VPS.

Sem isso o Caddy não consegue o certificado, porque a Let's Encrypt precisa chegar no seu servidor
pelo nome.

### A7. Baixar o projeto

O repositório é privado, então o servidor precisa de uma **chave de deploy** (somente leitura):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/convencendoai_deploy -N ""
cat ~/.ssh/convencendoai_deploy.pub
```

No GitHub: repositório, **Settings, Deploy keys, Add deploy key**, cole a chave pública e deixe
**sem** permissão de escrita. Depois:

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/convencendoai_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
git clone git@github.com:Ryans007/ConvencendoAI.git
cd ConvencendoAI
git checkout v0.23.0
```

Use sempre uma **tag de versão** (`git tag` lista as existentes), e não a `main`: assim você sabe
exatamente o que está rodando e consegue voltar.

### A8. Configurar o `.env`

```bash
cp .env.prod.example .env
chmod 600 .env
openssl rand -base64 48
openssl rand -hex 24
nano .env
```

Preencha `DOMAIN` (sem `https://`), `DJANGO_SECRET_KEY` (use a primeira saída do `openssl`),
`POSTGRES_PASSWORD` (a segunda) e `GROQ_API_KEY`, que o `seed_llm` grava no provedor Groq na A10.
As outras chaves de IA são cadastradas no admin de cada provedor (**Nova chave**). Todas ficam
criptografadas no banco com uma chave derivada do `DJANGO_SECRET_KEY`: trocar o `DJANGO_SECRET_KEY`
exige cadastrar as chaves de novo. Não cole chave de API em chat, e-mail nem issue. Numa instalação
que já tinha as variáveis `*_API_KEY` no `.env`, a migration `llm 0009` as importa para o banco.

### A9. Subir

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f convencendoai-api
```

O primeiro build leva alguns minutos. A API aplica as migrations sozinha ao subir.

Como saber que deu certo: os quatro serviços (`db`, `convencendoai-api`, `convencendoai-web`,
`caddy`) aparecem `healthy` ou `Up`, e `https://app.seu-dominio.com.br/api/health/` responde
`{"application":"ok","database":"ok"}`. Se o certificado falhar, olhe `docker compose logs caddy`: as
causas usuais são DNS ainda não propagado ou porta 80 fechada.

### A10. Primeiro acesso

```bash
docker compose exec convencendoai-api python manage.py createsuperuser
docker compose exec convencendoai-api python manage.py seed_llm
```

O `seed_llm` cadastra a Groq com a `GROQ_API_KEY` do `.env`, os modelos `gpt-oss-20b`,
`gpt-oss-120b`, `whisper-large-v3-turbo` e `orpheus-v1-english`, e preenche os papéis. Ele só completa
o que falta e nunca sobrescreve o que foi configurado no admin, então pode rodar de novo a qualquer
momento. Sem a variável, ele avisa e a chave pode ser colada no admin do provedor.

Abra `https://app.seu-dominio.com.br/admin/` e entre. Confira:

- O provedor Groq mostra o começo da chave em **Chave atual** (e não "não definida").
- Cadastre um usuário de teste pelo admin (ele gera uma senha temporária que aparece uma única vez).
  Entre no sistema com ele, troque a senha e faça uma sessão curta.
- **Prove o IP real:** erre a senha de um usuário inexistente uma vez, e no admin abra
  *Tentativas de login com erro*. O IP registrado precisa ser o **seu**, e não um `172.x` interno.

### A11. Backup

Sem backup, um `docker compose down -v` ou um disco com defeito apaga tudo. Crie
`/home/deploy/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /home/deploy/ConvencendoAI
set -a
. ./.env
set +a
mkdir -p /home/deploy/backups
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > "/home/deploy/backups/convencendoai-$(date +%F).dump"
find /home/deploy/backups -name 'convencendoai-*.dump' -mtime +14 -delete
```

```bash
chmod +x /home/deploy/backup.sh
/home/deploy/backup.sh && ls -lh /home/deploy/backups
crontab -e
```

No `crontab`, acrescente a linha (o servidor usa UTC, então 06:00 UTC são 03:00 em Brasília):

```
0 6 * * * /home/deploy/backup.sh
```

**Cópia fora do servidor:** um backup que mora na mesma máquina morre com ela. Instale o `rclone`,
configure um bucket (Cloudflare R2 ou Backblaze B2 têm plano gratuito pequeno) e acrescente ao fim do
script `rclone copy /home/deploy/backups remoto:convencendoai-backups`.

**Teste a restauração**, em um banco temporário, para nunca descobrir tarde que o backup não presta:

```bash
docker compose exec -T db createdb -U "$POSTGRES_USER" restore_test
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d restore_test --no-owner \
  < /home/deploy/backups/convencendoai-AAAA-MM-DD.dump
docker compose exec -T db psql -U "$POSTGRES_USER" -d restore_test -c "select count(*) from users_user;"
docker compose exec -T db dropdb -U "$POSTGRES_USER" restore_test
```

(Rode antes `set -a; . ./.env; set +a` para ter `$POSTGRES_USER` na sessão.)

### A12. Atualizar e voltar atrás

```bash
cd ~/ConvencendoAI
git fetch --tags
git checkout v0.24.0
docker compose up -d --build
```

Para voltar: `git checkout` na tag anterior e o mesmo `up -d --build`. Se a versão nova trouxe
migrations, voltar o código **não** desfaz o banco: faça um backup antes de cada atualização.

---

## Parte B. Dokploy

Faça numa VPS **limpa** (ou reinstale a da Parte A): o Dokploy quer as portas 80, 443 e 3000 livres,
e instala o próprio Docker.

### B1. Preparar a VPS

Repita os passos **A1 a A4** (VPS, usuário `deploy`, SSH fechado, firewall). Acrescente a porta do
painel ao firewall, só até configurar o domínio dele: `sudo ufw allow 3000/tcp`.

### B2. Instalar o Dokploy

Como root (ou `sudo -i`):

```bash
curl -sSL https://dokploy.com/install.sh | sh
```

Abra `http://IP-DA-VPS:3000`, crie a conta de administrador e use uma senha longa de gerenciador de
senhas. Ative a autenticação em dois fatores no perfil.

### B3. Domínios

Crie dois registros **A** para o IP da VPS: um para o sistema (`app`) e outro para o painel
(`painel`). No Dokploy, em **Settings, Server**, configure o domínio do painel com HTTPS
(Let's Encrypt).

Quando o painel abrir por `https://painel.seu-dominio.com.br`, feche a porta 3000 publicada. Não faça
antes, ou você perde o acesso:

```bash
docker service update --publish-rm "published=3000,target=3000,mode=host" dokploy
sudo ufw delete allow 3000/tcp
```

> O `ufw` **não** bloqueia portas publicadas pelo Docker, então o comando do `docker service
> update` é o que de fato fecha a 3000. Depois, confira de fora (outro computador ou 4G) que
> `http://IP:3000` não abre.

### B4. Banco de dados

1. Crie um **Project** (por exemplo `convencendoai`) e, nele, um serviço **Database, PostgreSQL**
   (a versão mais próxima de 18, que é a do desenvolvimento).
2. Defina nome do banco, usuário e uma senha longa. O Dokploy mostra o **nome interno do host**
   (App Name): é o valor de `POSTGRES_HOST` abaixo.
3. Não habilite acesso externo (porta publicada) ao banco.
4. **Backup:** em **Settings, S3 Destinations**, cadastre um bucket (R2 ou B2). No banco, aba
   **Backup**, escolha o destino, informe o nome do banco, um cron (por exemplo `0 6 * * *`, em UTC)
   e um prefixo. Use o botão **Test** e confira o arquivo no bucket. **Teste a restauração** pela
   seção Restore do próprio Dokploy, em um banco novo, uma vez antes de liberar o acesso.

### B5. O sistema

1. No projeto, **Create Service, Compose**, tipo **Docker Compose** (não *Stack*: ele não faz
   `build`).
2. Origem: **Git**. Para repositório privado, gere uma chave SSH em **Settings, SSH Keys**, cadastre
   a pública como **Deploy key** (somente leitura) no GitHub e use a URL
   `git@github.com:Ryans007/ConvencendoAI.git`. Branch: use uma **tag** (`v0.23.0`) ou a `main`.
3. Caminho do compose: `./docker-compose.dokploy.yml`.
4. Aba **Environment**:

   ```
   DJANGO_SECRET_KEY=<chave longa e aleatória>
   DJANGO_ALLOWED_HOSTS=app.seu-dominio.com.br
   DJANGO_CSRF_TRUSTED_ORIGINS=https://app.seu-dominio.com.br
   POSTGRES_DB=<nome do banco criado no B4>
   POSTGRES_USER=<usuário criado no B4>
   POSTGRES_PASSWORD=<senha criada no B4>
   POSTGRES_HOST=<App Name do banco no B4>
   ```

   Para o `seed_llm` cadastrar a Groq sozinho, acrescente `GROQ_API_KEY=<chave>`; as demais chaves
   de IA são cadastradas no admin de cada provedor, em **Nova chave**. Numa instalação que já tinha `GEMINI_API_KEY`, `GROQ_API_KEY` e `OLLAMA_CLOUD_API_KEY` nesta
   aba, mantenha-as até o primeiro deploy desta versão: a migration `llm 0009` as importa para o
   banco.

   O Dokploy grava isso num `.env` ao lado do compose, e o compose lê com `${VARIÁVEL}`. O
   compose acrescenta `localhost` ao `DJANGO_ALLOWED_HOSTS` sozinho, para a checagem de saúde.
5. Aba **Domains, Add Domain**: serviço `convencendoai-web`, host `app.seu-dominio.com.br`, porta
   do container `8080`, **HTTPS ligado**, certificado **Let's Encrypt**. O Dokploy gera os rótulos do
   Traefik; o botão **Preview Compose** mostra o resultado antes de subir.
6. **Deploy**, e acompanhe a aba de logs.

Depois do primeiro deploy, crie o super-admin e rode o seed no terminal do serviço
`convencendoai-api` (aba **Docker**, ou `docker exec` no container): `python manage.py
createsuperuser` e `python manage.py seed_llm`, como na A10.

Como saber que deu certo: o mesmo da Parte A (A9 e A10): `/api/health/` responde `ok` e o IP
registrado nas tentativas de login com erro é o seu.

### B6. Atualizar

Para uma versão nova, troque a tag no serviço e clique **Deploy**. Para voltar, a tag anterior. O
Dokploy também oferece webhook do GitHub para deploy automático; deixe desligado enquanto o sistema
tiver usuários de verdade, para uma atualização nunca ser surpresa.

---

## Comum às duas partes

### Monitoramento

- **Disponibilidade:** crie um monitor no UptimeRobot (plano gratuito) para
  `https://app.seu-dominio.com.br/api/health/` a cada 5 minutos, com alerta por e-mail. A rota
  responde 503 quando o banco não responde.
- **Gasto com IA:** o admin mostra o consumo por aluno e o custo em dólar (*Uso de modelos*). Confira
  uma vez por semana enquanto houver convidados novos, e ponha um limite de gasto no painel de cada
  provedor.
- **Disco:** `df -h` de vez em quando. Backups e imagens antigas (`docker image prune`) são o que
  mais enche.

### Convidados

Não há cadastro aberto. Para cada pessoa, crie o usuário no admin: o sistema gera uma senha
temporária, mostrada **uma única vez**, que você repassa por um canal seguro. No primeiro login a
pessoa é obrigada a trocá-la.

### Chaves de API

As três chaves (Groq, Google, Ollama Cloud) passaram por conversa e por arquivos locais durante o
desenvolvimento. **Gere chaves novas nos painéis dos provedores para o servidor**, não reutilize as de
desenvolvimento, e revogue as antigas. Para trocar uma chave depois, cole a nova em **Nova chave**, no admin do
provedor: vale na chamada seguinte, sem reiniciar nada. O banco guarda a chave criptografada com uma
chave derivada do `DJANGO_SECRET_KEY`, e o admin só mostra o começo dela.

### Antes de convidar alguém (checklist)

- [ ] SSH só por chave, root sem login, firewall ativo, só 22, 80 e 443 respondendo vistos de fora.
- [ ] `https://dominio/` abre com cadeado, `http://` redireciona, `/api/docs/` dá 404.
- [ ] Login funciona, o IP das tentativas de login com erro é o seu, e uma sessão de voz completa e uma rodada de
      revisão funcionam com microfone de verdade.
- [ ] O log da API (`docker compose logs convencendoai-api`) **não** mostra a fala dos alunos.
- [ ] Backup roda sozinho, há uma cópia fora do servidor e a restauração foi testada.
- [ ] Monitor de disponibilidade avisando por e-mail.
- [ ] Chaves de API novas, com limite de gasto nos provedores.
- [ ] A auditoria de segurança repetida sobre o ambiente montado (critério de pronto da issue #58).

### Problemas comuns

| Sintoma | Causa provável |
|---|---|
| Caddy não emite certificado | DNS ainda aponta para outro IP, ou porta 80 fechada. `docker compose logs caddy`. |
| 400 *Bad Request (400)* ao abrir o sistema | O domínio não está em `DJANGO_ALLOWED_HOSTS` (`DOMAIN`, na Parte A). |
| Login do admin falha com erro de CSRF | `DJANGO_CSRF_TRUSTED_ORIGINS` sem o `https://` do domínio. |
| A sessão de voz cai sozinha | Algum proxy com timeout curto no meio; o nginx já aceita 1 hora. |
| Todos os alunos aparecem com o mesmo IP | `TRUSTED_PROXY_COUNT` menor que o número de proxies reais. |
| A sessão mostra "serviço de IA indisponível" | Variável da chave do provedor ausente ou vazia no servidor. |
| O build do frontend morre sem erro claro | Falta de memória na VPS; use 4 GB ou crie swap. |
