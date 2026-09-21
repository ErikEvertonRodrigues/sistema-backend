# Alteração de senha

`POST /accounts/change-password/` exige autenticação JWT com
`Authorization: Bearer <access>`. O usuário é exclusivamente `request.user`.

```json
{
  "current_password": "SenhaAtual123!",
  "new_password": "NovaSenha456!",
  "new_password_confirm": "NovaSenha456!"
}
```

Os valores acima são exemplos sintéticos. Os três campos são obrigatórios e
`write_only`; campos extras são rejeitados, inclusive `user_id`, `username`,
`email` e `is_staff`. Parâmetros da URL não selecionam o usuário.

O serializer verifica a senha atual com `check_password()`, exige confirmação
igual à nova senha, impede reutilizar a senha atual e chama
`validate_password(new_password, user=user)`. Todos os validators configurados
em `AUTH_PASSWORD_VALIDATORS` são aplicados, incluindo similaridade com os
atributos do usuário. Espaços fazem parte da senha e são preservados.

Após validar, usa `set_password()` e salva apenas o campo `password`, com hash.

| Resultado | HTTP |
| --- | --- |
| Senha alterada; resposta sem corpo | 204 |
| Campo ausente, vazio, inválido ou inesperado; senha atual incorreta; confirmação diferente; senha reutilizada ou rejeitada pelos validators | 400 |
| Autenticação ausente ou access inválido/expirado | 401 |

As respostas deste endpoint não incluem senhas nem hashes. Após a alteração, o login com a
senha antiga retorna 401 e o login com a nova senha retorna access e refresh.
Há um exemplo executável em `../test.rest`, usando os tokens da requisição de login.

## JWTs emitidos antes da alteração

`SIMPLE_JWT["CHECK_REVOKE_TOKEN"] = True` habilita a opção oficial
[`CHECK_REVOKE_TOKEN`](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/settings.html#check-revoke-token)
para verificar mudança de senha na autenticação JWT. A biblioteca inclui a
claim `hash_password`, uma impressão derivada do hash armazenado pelo Django,
nos tokens emitidos; não inclui a senha nem o hash completo do banco.

**Alteração de senha → invalida tokens JWT emitidos com a senha anterior.**

Os testes de integração confirmam o fluxo final:

1. Login retorna access A e refresh A.
2. Alteração autenticada com access A retorna 204.
3. Access A em `/accounts/me/` retorna 401 (`password_changed`).
4. Refresh A em `/accounts/token/refresh/` retorna 401, sem emitir tokens.
5. Login com senha antiga retorna 401; com senha nova retorna access B e refresh B.
6. Access B autentica normalmente; refresh B emite access utilizável.

Tokens de outros usuários continuam funcionando. Uma tentativa de alteração
rejeitada não invalida os tokens. A proteção também funciona após
`user.set_password(...)` e `user.save(...)` fora deste endpoint.

### Particularidade do SimpleJWT 5.5.1

Habilitar apenas a configuração **não rejeita a requisição de refresh** nessa
versão: um teste inicial confirmou HTTP 200 quando se esperava 401. O
[`TokenRefreshSerializer` oficial](https://github.com/jazzband/djangorestframework-simplejwt/blob/v5.5.1/rest_framework_simplejwt/serializers.py)
não executa a checagem de mudança de senha; o access que ele gera ainda carrega
a claim anterior e não autentica.

Para cumprir o contrato, `accounts.RefreshSerializer` valida o refresh com a
classe oficial e chama `JWTAuthentication.get_user(refresh)` antes de delegar
a emissão à biblioteca. A comparação da claim e a rejeição são realizadas
inteiramente pelo recurso oficial. Não há algoritmo próprio de revogação,
novos registros em banco, timestamps, cache ou blacklist de access tokens.
Essa integração mantém a emissão e as verificações do serializer base, embora
a biblioteca valide o token e consulte o usuário novamente nessa etapa.

Tokens emitidos antes de habilitar a opção, sem a claim `hash_password`, também
são rejeitados e exigem novo login. As durações permanecem 5 minutos para access
e 1 dia para refresh, sem rotação.

### Logout após alteração

Logout com access anterior retorna 401 antes de executar a lógica da view e
não cria entrada na blacklist. Não existe exceção especial para esse caso.
Com tokens novos, o logout continua retornando 204 e revogando somente o refresh
informado. O logout por si só não invalida o access.

Os testes em `accounts/test_change_password.py` exercitam os endpoints reais
com tokens emitidos pelo login, sem sobrescrever a configuração JWT. Também
cobrem validações, isolamento entre usuários, persistência com hash e login
após alteração.

## Pendências fora do escopo

- Recuperação de senha.
- Provisionamento de segredos no deploy, conforme [README](../README.md).
- Limpeza periódica de tokens expirados com `flushexpiredtokens`.
