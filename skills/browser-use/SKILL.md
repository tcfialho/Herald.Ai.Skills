---
name: browser-automation-cdp
description: >
  Use this skill whenever the task involves browser automation, web scraping, or
  interacting with pages that require an authenticated session — especially via
  Chrome DevTools Protocol (CDP) over WebSocket. Triggers include: SPAs (React,
  Vue, Angular, Svelte), Shadow DOM / Web Components, nested iframes, lazy-loaded
  or virtualized content, JWT/token extraction from live browser sessions, masked
  or conditional forms, drag-and-drop, file upload, WebSockets/SSE, Service Workers,
  Canvas/WebGL, WebAssembly, PWA offline, browser permission APIs, and CORS/rate-limit
  handling. Also activate when the user needs to call a protected API using tokens
  from an active Edge session, or when HTTP-direct access fails due to SSO/auth
  cookie requirements.
---

# Browser Automation & Advanced Web Navigation (CDP)

---

## Princípio Operacional: Sonda → Interpreta → Decide

**Nunca executar um bloco de automação completo sem antes sondar o estado real da página.**

Cada interação segue este ciclo:

```
1. SONDA     — envia 1 evaluate pequeno para observar estado atual
2. INTERPRETA — lê o resultado: o que existe, o que está null, que erro retornou
3. DECIDE    — escolhe próximo passo ou fallback baseado na evidência
4. CONFIRMA  — após agir, sonda novamente para verificar que o efeito ocorreu
```

Se a confirmação falhar → não repetir o mesmo comando. Descer para o próximo
fallback da hierarquia. Cada falha reduz o espaço de hipóteses.

---

## Onde Começar

```
HTTP direto funciona? → Usar fetch/curl normal — não precisa de CDP
NÃO (SSO/cookies/JS required)
└── Edge aberto e autenticado?
    ├── SIM → Setup CDP abaixo, depois Protocolo de Sondagem
    └── NÃO → Instruir usuário: abrir Edge com --remote-debugging-port=9222
              e autenticar antes de continuar
```

---

## Setup CDP (executar uma vez por sessão)

### Hard Rules
- **PROIBIDO** `--headless` — destrói contexto SSO
- **PROIBIDO** `Stop-Process` / `kill` em `msedge.exe`
- **PROIBIDO** `Add-Type` para WebSocket — classe já nativa no .NET
- **PROIBIDO** hardcodar porta de debug
- **PROIBIDO** colar script no console do browser se CDP disponível

```powershell
# 1. PORTA — extrair dinamicamente
$port = (Get-CimInstance Win32_Process -Filter "name='msedge.exe'" |
    Select-Object -ExpandProperty CommandLine |
    Select-String '--remote-debugging-port=(\d+)' |
    ForEach-Object { $_.Matches[0].Groups[1].Value } |
    Select-Object -First 1)
if (-not $port) { throw "Edge sem --remote-debugging-port. Instruir usuário." }

# 2. TARGET — /json/list (não /json — retorna vazio no Edge moderno)
$targets = Invoke-RestMethod "http://localhost:$port/json/list"
$target  = $targets | Where-Object { $_.type -eq 'page' -and $_.url -notlike 'chrome-extension://*' } |
           Select-Object -First 1
$wsUrl   = $target.webSocketDebuggerUrl

# 3. CONEXÃO
$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$ws.ConnectAsync([Uri]$wsUrl, [Threading.CancellationToken]::None).Wait()

# 4. HELPERS BASE
function WsSend($obj) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Compress -Depth 10))
    $ws.SendAsync($bytes, 'Text', $true, [Threading.CancellationToken]::None).Wait()
}
function WsRecv {
    $buf = [byte[]]::new(65536); $ms = [IO.MemoryStream]::new()
    do {
        $seg = [ArraySegment[byte]]::new($buf)
        $res = $ws.ReceiveAsync($seg, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
        $ms.Write($buf, 0, $res.Count)
    } while (-not $res.EndOfMessage)
    [Text.Encoding]::UTF8.GetString($ms.ToArray())
}

# Eval: retornar sempre string 'k=v|k2=v2' — nunca objetos complexos
function Eval($expr) {
    WsSend @{ id=1; method='Runtime.evaluate'; params=@{
        expression=$expr; returnByValue=$true; awaitPromise=$false } }
    (WsRecv | ConvertFrom-Json).result.result.value
}

# EvalAsync: para expressões que retornam Promise real
function EvalAsync($expr) {
    WsSend @{ id=1; method='Runtime.evaluate'; params=@{
        expression=$expr; returnByValue=$true; awaitPromise=$true } }
    (WsRecv | ConvertFrom-Json).result.result.value
}

# DrainWs: OBRIGATÓRIO após qualquer Page.navigate
function DrainWs {
    WsSend @{ id=99; method='Runtime.evaluate'; params=@{ expression="'PING'"; returnByValue=$true } }
    $n=0; do { $r = WsRecv | ConvertFrom-Json; $n++ } while ($r.id -ne 99 -and $n -lt 50)
}

function Navigate($url) {
    WsSend @{ id=2; method='Page.navigate'; params=@{ url=$url } }
    WsRecv | Out-Null; Start-Sleep -Seconds 2; DrainWs
}

# TEARDOWN (executar ao encerrar sessão)
# $ws.CloseAsync('NormalClosure','', [Threading.CancellationToken]::None).Wait(); $ws.Dispose()
```

---

## Protocolo de Sondagem Reativa

### Passo 1 — Reconhecimento inicial (sempre o primeiro evaluate)

```javascript
// Retorna snapshot do estado atual como string JSON
JSON.stringify({
  url:         location.href,
  title:       document.title,
  readyState:  document.readyState,
  hasReact:    !!(window.React || window.__REACT_DEVTOOLS_GLOBAL_HOOK__),
  hasVue:      !!(window.Vue   || window.__VUE__),
  hasAngular:  !!(window.ng    || window.getAllAngularRootElements),
  iframes:     document.querySelectorAll('iframe').length,
  shadowHosts: [...document.querySelectorAll('*')].filter(e => e.shadowRoot).length,
  loaders:     document.querySelectorAll('[class*=load],[class*=spin],[class*=skeleton]').length,
})
```

**Interpreta:** a resposta determina o caminho. Ver tabela abaixo.

---

### Passo 2 — Tabela de Decisão por Evidência

| Evidência | Próxima ação | Confirma com |
|---|---|---|
| `readyState != 'complete'` | `Start-Sleep 2` + re-sondar | `readyState == 'complete'` |
| `loaders > 0` | `WaitForElement` aguardando loader sumir | `loaders == 0` |
| `hasReact/Vue/Angular = true` | Verificar hydration antes de interagir | `window.__APP_HYDRATED__` ou polling |
| `iframes > 0` | Sondar same-origin vs cross-origin | `contentDocument != null` |
| `shadowHosts > 0` | Sondar `shadowRoot.mode` do host alvo | elemento encontrado via `shadowRoot` |
| Tudo limpo | Prosseguir para interação direta | `querySelector` retorna não-null |

---

### Passo 3 — Sondar antes de interagir com qualquer elemento

```powershell
# NUNCA interagir diretamente sem sondar — pode ser null
# ERRADO:  Eval "document.getElementById('cpf').value = '123'"

# CORRETO: sondar primeiro
$exists = Eval "document.getElementById('cpf') !== null ? 'found' : 'null'"

switch ($exists) {
    'found'  { <# prosseguir — elemento existe #> }
    'null'   { <# elemento ausente — executar hierarquia de fallbacks abaixo #> }
    default  { <# erro inesperado — inspecionar resposta raw do WsRecv #> }
}
```

---

### Passo 4 — Hierarquia de Fallbacks: Elemento não encontrado

Descer sequencialmente. **Não repetir o mesmo passo.**

```
1. Página carregou?
   → Eval "document.readyState"
   → 'loading': Start-Sleep 2 + re-sondar | 'complete' e null: próximo

2. SPA com hydration pendente?
   → Eval "!!window.__APP_HYDRATED__ || document.querySelector('[data-reactroot]') !== null"
   → false: WaitHydrated (polling 200ms×50) | ainda null após hydration: próximo

3. Está em Shadow DOM?
   → Eval "document.querySelector('my-component')?.shadowRoot !== null ? 'shadow':'no'"
   → 'shadow': queryDeepShadow | 'no': próximo

4. Está em iframe?
   → Eval "document.querySelectorAll('iframe').length+'|'+(()=>{try{return !!document.querySelector('iframe')?.contentDocument}catch{return false}})()"
   → tem iframe same-origin: contentDocument | cross-origin: postMessage | sem iframe: próximo

5. Está fora do viewport (lazy-load)?
   → Eval "window.scrollTo(0, document.body.scrollHeight); 'scrolled'"
   → Start-Sleep 1 + re-sondar o elemento

6. Depende de ação prévia (campo condicional)?
   → Eval "typeof window.exibirCampo === 'function' ? 'has-trigger' : 'no-trigger'"
   → 'has-trigger': chamar + Start-Sleep 0.2 + re-sondar | 'no-trigger': próximo

7. Esgotou → reportar estado atual e solicitar contexto adicional ao usuário
```

---

### Passo 5 — Hierarquia de Fallbacks: Ação sem efeito

```
1. Valor foi aplicado?
   → Eval "document.getElementById('x').value" — mudou?
   → Não mudou: adicionar dispatchEvent('change') + re-confirmar

2. Framework não detectou?
   → Adicionar blur após set: Eval "el.blur(); el.value"
   → Alguns validators React/Vue só disparam no blur

3. Campo disabled/readonly?
   → Eval "'d='+el.disabled+'|r='+el.readOnly"
   → Se sim: Eval "el.removeAttribute('disabled'); el.removeAttribute('readonly')"
   → Re-interagir + confirmar

4. Overlay/modal interceptando?
   → Eval "document.querySelector('[class*=modal],[class*=overlay]') !== null ? 'blocked':'clear'"
   → CDP ignora z-index — chamar função de fechar diretamente: window.fecharModal()
   → Re-confirmar que overlay sumiu antes de continuar
```

---

### Passo 6 — Hierarquia de Fallbacks: Auth (401/403)

```
1. Token no localStorage?
   → Eval "Object.keys(localStorage).filter(k=>/token|auth|bearer/i.test(k)).join('|')"
   → Existe: extrair + usar como Bearer

2. Refresh token disponível?
   → Eval "localStorage.getItem('refresh_token') !== null ? 'yes':'no'"
   → 'yes': executar interceptor de refresh abaixo
   → Confirma: Eval "typeof window.__ACCESS_TOKEN__" → deve ser 'string'

3. Variável de ambiente?
   → Verificar $env:AZDEVOPS_TOKEN, $env:GITHUB_TOKEN, $env:JIRA_API_TOKEN

4. Cookie httpOnly (inacessível via JS)?
   → CDP: WsSend @{ method='Network.getAllCookies' }
   → Reautenticar via fluxo interativo se necessário
```

---

## Padrões de Confirmação por Tipo de Ação

Após cada ação, enviar evaluate de confirmação específico.
**Nunca assumir que funcionou.**

| Ação | Confirmação esperada |
|---|---|
| Preencher input mascarado | `el.value` retorna valor formatado (ex: `'123.456.789-01'`) |
| Submit de formulário | `document.querySelector('.success,.error')?.textContent \|\| 'pending'` |
| Navegar para nova página | `location.href + '\|' + document.readyState` após DrainWs |
| Upload de arquivo | `window.getUploadState?.() \|\| input.files.length` > 0 |
| Fechar modal | `document.querySelector('[class*=modal]')` retorna null |
| Acionar campo condicional | `document.getElementById('campoDinamico') !== null` |
| Scroll lazy-load | `document.querySelectorAll('.item').length` aumentou |
| Refresh token | `typeof window.__ACCESS_TOKEN__ === 'string'` |

---

## Snippets Reativos por Situação

### Aguardar elemento (MutationObserver — não polling cego)

```powershell
function WaitForElement($selector, $timeoutMs = 5000) {
    $expr = @"
new Promise(resolve => {
  if (document.querySelector('$selector')) return resolve('found');
  const obs = new MutationObserver(() => {
    if (document.querySelector('$selector')) { obs.disconnect(); resolve('found'); }
  });
  obs.observe(document.body, { childList: true, subtree: true });
  setTimeout(() => { obs.disconnect(); resolve('timeout'); }, $timeoutMs);
})
"@
    EvalAsync $expr
    # 'found' → prosseguir | 'timeout' → descer na hierarquia de fallbacks
}
```

### Aguardar hydration SPA

```powershell
function WaitHydrated {
    for ($i = 0; $i -lt 50; $i++) {
        if ((Eval "!!window.__APP_HYDRATED__") -eq 'true') { return 'hydrated' }
        Start-Sleep -Milliseconds 200
    }
    return 'timeout'  # caller decide: tentar WaitForElement sem loader
}
```

### Shadow DOM — sondagem progressiva

```powershell
# Sonda 1: shadow root existe e qual modo?
$mode = Eval "document.querySelector('my-component')?.shadowRoot?.mode || 'no-shadow'"
# → 'open': acesso direto | 'closed': monkey-patch abaixo | 'no-shadow': elemento errado

# Se 'open' — Sonda 2: alvo existe dentro?
$inner = Eval "document.querySelector('my-component').shadowRoot.querySelector('.target') !== null ? 'found':'null'"

# Se 'closed' — monkey-patch (injetar antes da init do componente):
Eval @"
  const _o = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function(i){ return _o.call(this,{...i,mode:'open'}); };
  'patched'
"@
# Confirma: re-sondar $mode — deve retornar 'open'
```

### Formulário mascarado — ciclo completo

```powershell
# Sonda: campo existe, tipo e valor atual
$info = Eval "(el=>el?el.tagName+'|'+el.type+'|'+el.value:'null')(document.getElementById('cpf'))"
# → 'INPUT|text|' : existe e vazio → prosseguir
# → 'null'        : não existe → hierarquia de fallbacks

# Ação
Eval "const el=document.getElementById('cpf'); el.value='12345678901'; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.value"

# Confirma: valor deve estar formatado
$formatted = Eval "document.getElementById('cpf').value"
# → '123.456.789-01' : OK
# → '12345678901'    : máscara não ativou → adicionar blur
# → ''               : campo resetou → verificar validator que limpa em change
```

### Iframe — sondagem de acesso

```powershell
$info = Eval "(f=>f?f.src+'|'+(()=>{try{return !!f.contentDocument}catch{return false}})()+
              '|'+document.querySelectorAll('iframe').length:'none')(document.querySelector('iframe'))"
# → 'https://same.com/p|true|1'  : same-origin → contentDocument direto
# → 'https://other.com/p|false|1': cross-origin → postMessage
# → 'none'                        : sem iframe → procurar em shadow DOM ou nested
```

### Refresh Token — interceptor completo

```javascript
// Injetar uma vez; todos os fetches subsequentes são interceptados automaticamente
const _f = window.fetch.bind(window);
window.fetch = async function(...args) {
  let res = await _f(...args);
  if (res.status === 401) {
    const ok = await (async () => {
      const rt = localStorage.getItem('refresh_token');
      if (!rt) return false;
      const r = await _f('/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt })
      });
      if (!r.ok) return false;
      const { access_token } = await r.json();
      localStorage.setItem('access_token', access_token);
      window.__ACCESS_TOKEN__ = access_token;
      return true;
    })();
    if (!ok) throw new Error('Refresh falhou');
    const [input, init={}] = args;
    res = await _f(input, { ...init, headers: { ...(init.headers||{}),
      Authorization: `Bearer ${window.__ACCESS_TOKEN__}` }});
  }
  return res;
};
// Confirma: Eval "typeof window.__ACCESS_TOKEN__"  → deve ser 'string'
```

### Microsoft / Azure DevOps (MSAL — sem PAT)

```python
import msal, os

CLIENT_ID  = '04b07795-8ddb-461a-bbee-02f9e1bf7b46'
AUTHORITY  = 'https://login.microsoftonline.com/organizations'
SCOPE      = ['499b84ac-1321-427f-aa17-267ca6975798/.default']
CACHE_FILE = os.path.expanduser('~/.msal_cache.json')

cache = msal.SerializableTokenCache()
if os.path.exists(CACHE_FILE):
    cache.deserialize(open(CACHE_FILE).read())

app    = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
result = app.acquire_token_silent(SCOPE, account=(app.get_accounts() or [None])[0])
if not result:
    result = app.acquire_token_interactive(SCOPE)

if 'access_token' in result:
    open(CACHE_FILE, 'w').write(cache.serialize())
    # usar result['access_token'] como Bearer — nunca logar o valor
```

---

## Outros Padrões (referência rápida)

| Categoria | Sondar com | Confirmar com |
|---|---|---|
| **WebSockets/SSE** | `typeof window.__WS_MESSAGES__` | `.length > 0` após evento esperado |
| **Service Workers** | `navigator.serviceWorker.controller !== null` | `caches.keys()` lista cache esperado |
| **Canvas/WebGL** | `canvas.getContext('webgl')?.getContextAttributes().preserveDrawingBuffer` | `canvas.toDataURL().length > 100` |
| **WebAssembly** | `typeof WebAssembly` | instanciar módulo mínimo (magic bytes) |
| **Rate Limit 429** | header `Retry-After` na resposta | próximo request retorna 200 |
| **Drag & Drop** | `typeof window.simulateDragDrop` | `getDragState()` após ação |
| **Notifications** | `Notification.permission` (read-only) | interceptar `requestPermission`, não forçar |
| **File Upload** | `typeof window.simulateFileSelect` | `getUploadState()` ou `input.files.length` |
| **WASM Benchmark** | usar `n < 170` para factorial | `speedup !== NaN && speedup !== Infinity` |
| **PWA/LocalStorage** | `localStorage.getItem('chave')` | valor persiste após `salvarOffline()` |

---

## Anti-Patterns

| Anti-Pattern | Por que falha | Substituir por |
|---|---|---|
| Executar bloco completo sem sondar | Falha silenciosa sem diagnóstico | Reconhecimento inicial primeiro |
| Repetir mesmo comando após falha | Mesmo input → mesmo output | Descer na hierarquia de fallbacks |
| Assumir que ação funcionou | DOM pode não ter refletido ainda | Sempre confirmar com evaluate pós-ação |
| `querySelector` sem verificar null | TypeError na próxima linha | Sondar existência antes de usar |
| Keypress em input mascarado | Máscara não ativa | `value =` + `dispatchEvent('input')` |
| `awaitPromise=true` com `setTimeout` solto | Trava WsRecv indefinidamente | Promise wrapper real ou Start-Sleep externo |
| `/json` no Edge moderno | Retorna lista vazia | Usar `/json/list` |
| Objeto complexo em `evaluate` | Serialização CDP falha | Retornar string `'k=v\|k2=v2'` |
| WS sem drain após navegação | IDs de resposta desalinhados | DrainWs obrigatório após Navigate |
| `Notification.permission = 'granted'` | Propriedade read-only | Interceptar `requestPermission` |
