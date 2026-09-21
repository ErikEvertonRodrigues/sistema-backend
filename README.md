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

## Preparação para produção

Mantemos um único `mysite/settings.py`. Sem chave adequada, ou sem hosts com
`DJANGO_DEBUG=false`, a aplicação falha com `ImproperlyConfigured`, sem exibir
a chave. Os cookies seguros e o redirecionamento HTTPS ficam ativos por padrão
quando debug está desativado; as três opções podem ser ajustadas explicitamente
conforme a infraestrutura. Não reutilize o arquivo local de desenvolvimento.

Use uma chave própria por ambiente e configure hosts explícitos. O SimpleJWT
HS256 usa essa mesma `SECRET_KEY`: trocá-la invalida os JWTs anteriores e afeta
as sessões Django. A chave anteriormente embutida foi removida do código atual,
mas permanece no histórico Git; não a reutilize. Se foi usada em outro ambiente,
substitua-a nesse ambiente. Não houve reescrita do histórico.

Para uma verificação representativa, depois de carregar uma chave gerada, execute:

```bash
DJANGO_DEBUG=false \
DJANGO_ALLOWED_HOSTS=api.example.test \
DJANGO_SESSION_COOKIE_SECURE=true \
DJANGO_CSRF_COOKIE_SECURE=true \
DJANGO_SECURE_SSL_REDIRECT=true \
python manage.py check --deploy
```

`api.example.test` é fictício; use o domínio real no deploy. Essa verificação
avalia settings e não testa certificados, proxy ou disponibilidade do serviço.
Permanece o warning **`security.W004`**, pois HSTS ainda não foi configurado.
O prazo, os subdomínios e eventual preload devem ser decididos após validar HTTPS,
conforme o [checklist oficial do Django](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/).

Pendências de deploy:

- Provisionar segredos por ambiente e substituir a chave antiga onde tiver sido usada.
- Definir domínio, certificado TLS, terminação HTTPS e confiança nos headers do
  proxy; configurar `SECURE_PROXY_SSL_HEADER` somente conforme essa infraestrutura
  para evitar falsificação de headers ou redirecionamentos em loop.
- Decidir HSTS e, se necessário pela origem do admin, `CSRF_TRUSTED_ORIGINS`.
- Definir o servidor de aplicação e a entrega dos arquivos estáticos do admin,
  incluindo `STATIC_ROOT` e `collectstatic`; `runserver` é apenas para desenvolvimento.
- Garantir armazenamento persistente, permissões e backups do SQLite.
- Agendar limpeza de tokens expirados (`python manage.py flushexpiredtokens`).

Não há Docker, CI/CD, PostgreSQL ou configuração de CORS nesta etapa.
