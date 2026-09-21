# Sistema — API Django

API de organização pessoal. O módulo `accounts` oferece cadastro, login JWT,
refresh, logout, usuário atual e alteração de senha. O banco continua sendo
SQLite em `BASE_DIR / "db.sqlite3"`.

## Desenvolvimento local

Requer Python **3.12 ou superior** (ambiente local verificado: 3.13.5).
Execute os comandos abaixo na raiz deste repositório, em Bash.

### Ambiente virtual e dependências

O ambiente virtual existente está em `../.env`; preserve esse diretório:

```bash
source ../.env/bin/activate
python -m pip install -r requirements.txt
```

Em um checkout novo, sem esse ambiente, crie e ative um `.venv` local:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Variáveis

Usamos somente `os.environ`, sem dependência adicional. O Django não carrega
arquivos `.env` automaticamente. Para desenvolvimento, use **`.env.local`**
na raiz do repositório; ele não conflita com o virtualenv `../.env`.

Na primeira configuração, copie o exemplo se `.env.local` ainda não existir:

```bash
cp -n .env.example .env.local
chmod 600 .env.local
python - <<'PY'
from pathlib import Path
from secrets import token_urlsafe

path = Path('.env.local')
text = path.read_text()
text = text.replace('DJANGO_SECRET_KEY=change-me', 'DJANGO_SECRET_KEY=' + token_urlsafe(64))
path.write_text(text)
PY
```

O comando substitui apenas o marcador `change-me`, preservando uma chave já
configurada. O exemplo contém valores fictícios e não inicia a aplicação sem
essa substituição. A chave local deve permanecer estável entre execuções.

Carregue o arquivo em **cada novo terminal**, antes de qualquer comando Django:

```bash
set -a
source .env.local
set +a
```

O shell exporta os valores para os processos filhos. O arquivo usa sintaxe de
shell; coloque entre aspas valores com espaços ou caracteres especiais e
carregue somente seu arquivo local confiável. `source` substitui variáveis de
mesmo nome já definidas no terminal; em deploy, injete-as diretamente no processo.
`.env`, `.env.local`, outros `.env.*` e `.venv/` são ignorados pelo Git;
`.env.example` é versionável. O virtualenv existente não é renomeado nem alterado.

| Variável | Padrão / comportamento |
| --- | --- |
| `DJANGO_SECRET_KEY` | Obrigatória, sem fallback. Chave aleatória com pelo menos 50 caracteres, 5 caracteres distintos e sem prefixo `django-insecure-`. |
| `DJANGO_DEBUG` | `false`; use `true` explicitamente no desenvolvimento. |
| `DJANGO_ALLOWED_HOSTS` | Lista separada por vírgulas; espaços e entradas vazias são removidos. Padrão vazio, obrigatório com debug desativado. Sem wildcard padrão. |
| `DJANGO_SESSION_COOKIE_SECURE` | `false` com debug ativado; `true` com debug desativado. |
| `DJANGO_CSRF_COOKIE_SECURE` | Mesmo padrão acima. |
| `DJANGO_SECURE_SSL_REDIRECT` | Mesmo padrão acima. |
| `DJANGO_TRUST_PROXY_HEADERS` | `false`; habilite somente atrás de um proxy confiável que defina `X-Forwarded-Proto`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Lista opcional de origens com esquema, separadas por vírgulas; padrão vazio. |

Booleanos aceitam `true/false`, `1/0`, `yes/no` ou `on/off`, sem diferenciar
maiúsculas e ignorando espaços nas extremidades. Valor vazio ou desconhecido
gera erro claro de configuração; ausência usa o padrão. A validação de chave
rejeita valores obviamente inseguros, mas não mede aleatoriedade: use o gerador.

### Banco, testes e servidor

Com o virtualenv ativo e as variáveis carregadas:

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check
python manage.py migrate --check
python manage.py test
python -m pip check
git diff --check
python manage.py runserver
```

O servidor local usa `http://127.0.0.1:8000/`; o admin está em `/admin/`.
Se precisar acessar o admin, crie um usuário com `python manage.py createsuperuser`.
Os testes de integração locais usam a configuração de desenvolvimento, sem
redirecionamento HTTPS. Exemplos da API estão em [test.rest](test.rest), e a
política de tokens em [docs/change-password.md](docs/change-password.md).

## Deploy de testes no Render

Este deploy é um **Web Service gratuito e descartável**, somente para dados
fictícios. O filesystem do plano Free é efêmero: dados no SQLite podem desaparecer
em deploys, reinicializações e suspensão por inatividade. `db.sqlite3` hospedado
nunca é fonte confiável de persistência. Cadastros e registros de blacklist também
podem desaparecer. Será necessário adotar PostgreSQL antes de usar dados reais.
Não há tentativa de preservar o banco entre instâncias. Consulte as
[limitações oficiais do plano Free](https://render.com/docs/free).

### Criar o serviço

1. Envie as alterações revisadas para o repositório público do GitHub.
2. No dashboard do Render, selecione **New → Web Service**, conecte o repositório
   e escolha a branch que contém estas alterações.
3. Selecione runtime **Python 3** e instância **Free**. Use como Root Directory
   a pasta que contém `manage.py` e `requirements.txt` (a raiz deste repositório).
4. Configure os comandos abaixo e as variáveis na seção **Environment**.
5. Configure **Health Check Path** como `/health/`.
6. Confirme o hostname atribuído pelo Render e ajuste `DJANGO_ALLOWED_HOSTS`
   antes de validar a API. Salve as alterações e execute o deploy.

Usamos o dashboard manualmente: um serviço com dois comandos não precisa de
`render.yaml` nesta fase. Nenhum hostname real ou segredo é mantido no código.
O arquivo `.python-version` seleciona Python 3.13, com o patch disponível no
Render; a validação local usa Python 3.13.5. O Render documenta essa seleção em
[Python version](https://render.com/docs/python-version).

**Build Command**:

```sh
python -m pip install -r requirements.txt && python manage.py collectstatic --noinput
```

**Start Command**:

```sh
python manage.py migrate --noinput && exec gunicorn mysite.wsgi:application --bind "0.0.0.0:$PORT" --workers 1
```

`PORT` é fornecida pelo Render; não cadastre uma porta fixa. Gunicorn executa o
WSGI existente, com um worker, suficiente para este teste com SQLite. `exec`
mantém o Gunicorn como processo principal para receber os sinais da plataforma.
Nunca use `runserver` no deploy.

### Migrations e dados temporários

As migrations são executadas **uma vez por inicialização do serviço, antes do
Gunicorn**, no filesystem da própria instância. Se falharem, `&&` impede a
inicialização do servidor. O Django aplica somente migrations ainda pendentes;
repetir o start em um banco já migrado não reaplica as migrations.

Isso recria o schema quando o SQLite efêmero desaparece. Não colocamos migrations
no build, em imports, em `AppConfig.ready()` ou em hooks de workers. O comando
pre-deploy do Render é restrito a serviços pagos e executa em outra instância,
cujas alterações de filesystem não chegam ao serviço. Veja
[Deploy steps](https://render.com/docs/deploys#deploy-steps).

Esta escolha é específica para uma instância de testes com banco local descartável.
Ao adotar PostgreSQL/persistência ou múltiplas instâncias, rever a execução das
migrations para ocorrer em uma etapa única e controlada do deploy.

### Variáveis no painel

Os valores abaixo são apenas exemplos públicos. Substitua os domínios fictícios
no painel; não versione o ambiente real nem copie `.env.local` para o Render.

| Nome | Configuração no Render |
| --- | --- |
| `DJANGO_SECRET_KEY` | Gere uma chave nova e exclusiva deste ambiente; guarde apenas no Environment do Render. Sem valor de exemplo utilizável. |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_ALLOWED_HOSTS` | Hostname atribuído, sem esquema ou barra; exemplo fictício: `example.onrender.com`. Nunca `*`. |
| `DJANGO_SESSION_COOKIE_SECURE` | `true` |
| `DJANGO_CSRF_COOKIE_SECURE` | `true` |
| `DJANGO_SECURE_SSL_REDIRECT` | `true` |
| `DJANGO_TRUST_PROXY_HEADERS` | `true`, para este serviço atrás do proxy do Render. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Opcional: origem HTTPS exata do admin; exemplo fictício: `https://example.onrender.com`. |

A chave deve ser aleatória, ter pelo menos 50 caracteres e 5 caracteres distintos
e não começar com `django-insecure-`. Gere-a em um gerenciador de segredos e
insira-a no painel, sem incluí-la em comandos, logs, screenshots, testes ou Git.
Ela deve ser diferente da chave local e da antiga chave presente no histórico.
**A chave antiga está comprometida**: nunca reutilize; rotacione-a onde tiver sido
usada. O histórico não foi reescrito. O JWT HS256 usa `SECRET_KEY`; sua troca
invalida tokens anteriores e afeta sessões Django.

### Estáticos, HTTPS e CSRF

WhiteNoise fica imediatamente após `SecurityMiddleware` e serve os arquivos
coletados em `staticfiles/`, incluindo os assets do Django Admin. Com debug
desativado, `CompressedManifestStaticFilesStorage` gera nomes com hash e versões
comprimidas. A pasta gerada é ignorada pelo Git. Em desenvolvimento, o storage
simples preserva `runserver` e testes sem exigir `collectstatic` previamente.
Não há armazenamento externo ou suporte a uploads. Essa configuração segue o
[guia do WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html).

O Render termina TLS antes de encaminhar a requisição. A opção
`DJANGO_TRUST_PROXY_HEADERS=true` define
`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, para o Django
reconhecer o HTTPS original e evitar loops. Fora de um proxy confiável que
controle esse header, mantenha a opção desativada. Não ativamos confiança em
`X-Forwarded-Host`; o hostname continua limitado por `DJANGO_ALLOWED_HOSTS`.
Veja a explicação do [proxy do Render](https://render.com/tutorials/web-service-vs-static-site/web-services).

O admin na mesma origem HTTPS não precisa de uma origem CSRF adicional quando
o proxy está configurado corretamente. A variável opcional permite declarar a
origem exata quando necessário; a proteção CSRF permanece ativa. A API mobile
autenticada por JWT continua independente de cookies/CSRF. CORS não foi adicionado.

HSTS permanece desativado. `check --deploy` ainda aponta **`security.W004`**;
isso é intencional neste primeiro teste. Confirme HTTPS, redirects e cookies no
domínio público antes de definir uma política HSTS gradual, sem período longo
durante a experimentação inicial.

### Superusuário e verificação após deploy

Não existe criação automática de superusuário. Se o plano disponibilizar shell
na instância que está executando o serviço, use manualmente:

```sh
python manage.py createsuperuser
```

O plano Free atualmente não oferece shell via dashboard/SSH nem one-off jobs.
Portanto, neste plano, valide a página de login e os estáticos do admin sem criar
um administrador remoto. Não coloque credenciais no build/start e não copie um
banco local para contornar essa limitação. No desenvolvimento, o comando acima
continua disponível no terminal local.

Após o deploy:

1. Abra `https://example.onrender.com/health/`, substituindo o hostname apenas
   no seu cliente: deve retornar 200 e somente `{"status":"ok"}`.
2. Abra `/admin/login/` por HTTPS e confirme carregamento do CSS/JS, ausência de
   loops e cookie CSRF com `Secure`.
3. Confirme que `/accounts/me/` sem JWT retorna 401 e que um caminho inexistente
   retorna 404 sem traceback detalhado.
4. Use `test.rest` ou um cliente HTTP com a URL pública configurada localmente.
   Cadastre somente dados fictícios, valide login, refresh, `/accounts/me/`,
   alteração de senha e logout. Não publique os tokens obtidos.

`/health/` é público, aceita GET/HEAD e não consulta o banco. Ele confirma que o
processo responde; não garante persistência de dados ou integridade do banco.
O primeiro acesso após inatividade pode demorar enquanto o serviço é reativado.

### Verificações e próximos passos

Com variáveis representativas do Render configuradas no processo, execute:

```sh
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Os testes locais continuam usando `.env.local` com debug ativado. Eles cobrem
também HTTPS encaminhado, ausência de loops, CSRF do admin e `/health/`.

Pendências reais: validar o domínio público e TLS no primeiro deploy, decidir
HSTS depois dessa validação, adotar PostgreSQL com backups antes de dados reais
e planejar limpeza periódica de tokens expirados (`flushexpiredtokens`).

Não há Docker, CI/CD, domínio customizado ou configuração de PostgreSQL nesta etapa.
