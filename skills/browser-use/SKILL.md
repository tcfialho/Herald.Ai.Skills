---
name: browser-use
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

Operational reference distilled from 20 validated lab scenarios.  
All patterns verified via Chrome DevTools Protocol over WebSocket (Edge).

---

## Decision Tree: Where to Start

```
Preciso acessar conteúdo web?
├── HTTP direto funciona? → Usar fetch/curl normal
└── NÃO (SSO/cookies/JS required)
    └── Edge aberto e autenticado?
        ├── SIM → PROTOCOLO CDP (seção abaixo)
        └── NÃO → Instruir usuário a abrir Edge com --remote-debugging-port
                  e autenticar manualmente antes de continuar
```

---

## PROTOCOLO CDP (Edge / PowerShell)

### Hard Rules
- **PROIBIDO** `--headless` (destrói contexto SSO)
- **PROIBIDO** `Stop-Process` / `kill` em `msedge.exe`
- **PROIBIDO** `Add-Type` para WebSocket (classe nativa no .NET)
- **PROIBIDO** hardcodar porta de debug
- **PROIBIDO** pedir ao usuário para colar script no console se CDP disponível

### Sequência de Execução

```powershell
# 1. DESCOBRIR PORTA
$port = (Get-CimInstance Win32_Process -Filter "name='msedge.exe'" |
    Select-Object -ExpandProperty CommandLine |
    Select-String '--remote-debugging-port=(\d+)' |
    ForEach-Object { $_.Matches[0].Groups[1].Value } |
    Select-Object -First 1)

if (-not $port) { throw "Edge não encontrado com --remote-debugging-port. Instrua o usuário." }

# 2. RESOLVER TARGET  ← usar /json/list (não /json — retorna vazio no Edge moderno)
$targets = Invoke-RestMethod "http://localhost:$port/json/list"
$target  = $targets | Where-Object { $_.type -eq 'page' -and $_.url -notlike 'chrome-extension://*' } |
           Select-Object -First 1
$wsUrl   = $target.webSocketDebuggerUrl

# 3. CONECTAR
$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$ws.ConnectAsync([Uri]$wsUrl, [Threading.CancellationToken]::None).Wait()

# 4. HELPERS
function WsSend($obj) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Compress -Depth 10))
    $ws.SendAsync($bytes, 'Text', $true, [Threading.CancellationToken]::None).Wait()
}

function WsRecv {
    $buf = [byte[]]::new(65536)
    $ms  = [IO.MemoryStream]::new()
    do {
        $seg = [ArraySegment[byte]]::new($buf)
        $res = $ws.ReceiveAsync($seg, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
        $ms.Write($buf, 0, $res.Count)
    } while (-not $res.EndOfMessage)
    [Text.Encoding]::UTF8.GetString($ms.ToArray())
}

# 5. DRAIN após navegação  ← SEMPRE executar antes do próximo evaluate
function DrainWs {
    WsSend @{ id=99; method='Runtime.evaluate'; params=@{ expression="'PING'"; returnByValue=$true } }
    $n = 0; do { $r = WsRecv | ConvertFrom-Json; $n++ } while ($r.id -ne 99 -and $n -lt 50)
}

# 6. AVALIAR JS  ← retornar string 'k=v|k2=v2', não objetos complexos
function Eval($expr) {
    WsSend @{ id=1; method='Runtime.evaluate'; params=@{ expression=$expr; returnByValue=$true; awaitPromise=$false } }
    (WsRecv | ConvertFrom-Json).result.result.value
}

# 7. NAVEGAR
function Navigate($url) {
    WsSend @{ id=2; method='Page.navigate'; params=@{ url=$url } }
    WsRecv | Out-Null
    Start-Sleep -Seconds 2
    DrainWs   # ← obrigatório após qualquer navegação
}

# 8. TEARDOWN
$ws.CloseAsync('NormalClosure', '', [Threading.CancellationToken]::None).Wait()
$ws.Dispose()
```

> **Saída final:** apenas `result.result.value` — nunca log do payload completo.

---

## Padrões por Categoria

### SPAs (React / Vue / Angular / Svelte)

**Problema:** React.lazy + Suspense criam múltiplos estágios de loading; DOM ready ≠ app pronto.

```javascript
// Aguardar hydration via flag global (adicionar no app):
await new Promise(resolve => {
  if (window.__APP_HYDRATED__) return resolve();
  window.addEventListener('__REACT_HYDRATION_COMPLETE__', resolve, { once: true });
});

// Alternativa: aguardar loader desaparecer
await page.waitForSelector('[data-testid="page-loader"]', { state: 'hidden' });
```

---

### Shadow DOM / Web Components

**Problema:** `querySelector` padrão não enxerga elementos dentro de shadow roots.

```javascript
// Open shadow root — acesso direto
const inner = document.querySelector('my-component').shadowRoot.querySelector('.target');

// Closed shadow root — usar composedPath no evento
element.addEventListener('click', e => console.log(e.composedPath()[0]));

// Nested shadow DOM — travessia recursiva
function queryDeepShadow(selectors) {
  return selectors.reduce((el, sel) => {
    el = el.querySelector(sel);
    return el?.shadowRoot ?? el;
  }, document);
}
// Uso: queryDeepShadow(['app-container', 'nested-level2', '.target'])
```

---

### Iframes

```javascript
// Same-origin — acesso direto
const doc = document.querySelector('#my-iframe').contentDocument;

// Cross-origin — postMessage (requer cooperação do iframe)
iframe.contentWindow.postMessage('getData', 'https://trusted.com');
window.addEventListener('message', e => {
  if (e.origin !== 'https://trusted.com') return;
  console.log(e.data);
});

// Nested iframes — acesso recursivo
function getNestedIframe(indices) {
  return indices.reduce((doc, idx) =>
    doc.querySelectorAll('iframe')[idx].contentDocument, document);
}
```

---

### Lazy Loading / Virtualização

```javascript
// Scroll incremental + espera antes de capturar
for (let y = 0; y < 5000; y += 500) {
  window.scrollTo(0, y);
  await new Promise(r => setTimeout(r, 300)); // aguardar render
}
```

---

### Formulários: Máscaras, Selects, Radios, Checkboxes

**Regra:** nunca simular keypress em inputs mascarados — a máscara ouve `input`/`change`.

```javascript
// Input mascarado (CPF, CNPJ, CEP, cartão)
const el = document.getElementById('cpf');
el.value = '12345678901';                                  // dígitos raw
el.dispatchEvent(new Event('input', { bubbles: true }));   // ativa máscara
const raw = el.value.replace(/\D/g, '');                   // extrair sem máscara

// Select
document.getElementById('estado').value = 'SP';
document.getElementById('estado').dispatchEvent(new Event('change', { bubbles: true }));

// Radio  ← .click() mais confiável que .checked = true (aciona onclick handlers)
document.querySelector('[value="sim"]').click();

// Checkbox com validator
const cb = document.getElementById('termos');
cb.checked = true;
cb.dispatchEvent(new Event('change', { bubbles: true }));

// Campos condicionais: chamar função geradora ANTES de tentar getElementById
window.exibirCamposCondicional();
document.getElementById('campoDinamico').value = 'valor';
```

---

### Overlays / Modais via CDP

CDP executa JS direto, ignorando `z-index`, `pointer-events` e `display:none`.

```javascript
window.abrirModal();      // funciona mesmo com overlay cobrindo a UI
window.confirmarEnvio();  // não requer click visual
```

**Async com timer:** não usar `awaitPromise=true` com `setTimeout` não-promisificado — trava o recv loop.

```javascript
// CORRETO: Promise wrapper
const result = await new Promise(resolve => {
  buscarCEP('01310-100');
  setTimeout(() => resolve(document.getElementById('logradouro').value), 800);
});

// ALTERNATIVA: Start-Sleep externo (PowerShell), sem awaitPromise
```

---

### File Upload

```javascript
// Opção 1: helper exposto (preferível)
window.simulateFileSelect(['foto.jpg', 'relatorio.pdf']);

// Opção 2: DataTransfer
const dt = new DataTransfer();
dt.items.add(new File(['conteúdo'], 'test.txt', { type: 'text/plain' }));
document.getElementById('fileInput').files = dt.files;
document.getElementById('fileInput').dispatchEvent(new Event('change', { bubbles: true }));

// CUIDADO: simularUpload() pode acessar DOM inexistente (setInterval com refs quebradas)
// Usar getUploadState() para verificar sem executar upload real
```

---

### Autenticação: Tokens via CDP

```javascript
// Escanear localStorage por JWTs
const keys = Object.keys(localStorage).filter(k => /token|auth|bearer/i.test(k));
const token = localStorage.getItem(keys[0]);
// Usar o token imediatamente via PowerShell e descartar da memória
```

**Hierarquia de auth para APIs protegidas:**
1. Variável de ambiente (`AZDEVOPS_TOKEN`, `GITHUB_TOKEN`, `JIRA_API_TOKEN`)
2. Extração CDP do Edge autenticado (acima)
3. Nunca pedir hardcode de token ao usuário

---

### Microsoft / Azure DevOps (MSAL — sem PAT)

```python
import msal, json, os

CLIENT_ID = '04b07795-8ddb-461a-bbee-02f9e1bf7b46'   # Azure CLI pública
AUTHORITY = 'https://login.microsoftonline.com/organizations'
SCOPE     = ['499b84ac-1321-427f-aa17-267ca6975798/.default']
CACHE_FILE = os.path.expanduser('~/.msal_cache.json')

cache = msal.SerializableTokenCache()
if os.path.exists(CACHE_FILE):
    cache.deserialize(open(CACHE_FILE).read())

app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

result = app.acquire_token_silent(SCOPE, account=app.get_accounts()[0] if app.get_accounts() else None)
if not result:
    result = app.acquire_token_interactive(SCOPE)

if 'access_token' in result:
    open(CACHE_FILE, 'w').write(cache.serialize())
    # Usar result['access_token'] como Bearer
```

---

### Outros Padrões

| Categoria | Padrão-chave |
|---|---|
| **WebSockets / SSE** | Inspecionar `window.__WS_MESSAGES__` ou variáveis globais; não criar nova conexão |
| **Service Workers** | `caches.keys()` para listar; `cache.match(url)` para bypass; aguardar `sw.active` |
| **Canvas / WebGL** | `canvas.getContext('webgl', { preserveDrawingBuffer: true })` → `toDataURL()` |
| **WebAssembly** | Detectar via `new WebAssembly.Module(Uint8Array.of(0,0x61,0x73,0x6d,1,0,0,0))` |
| **CORS** | Preflight OPTIONS; `credentials: 'include'`; modo `no-cors` retorna response opaca |
| **Rate Limit 429** | Ler `Retry-After` header; exponential backoff com jitter; nunca burlar |
| **Drag & Drop** | `window.simulateDragDrop(itemId, zoneId)` se exposto; fallback: `target.appendChild(item)` |
| **Notifications** | `Notification.permission` é read-only; interceptar `requestPermission` para simular |
| **PWA / LocalStorage** | Setar `input.value` ANTES de chamar helper que lê o campo; `localStorage.clear()` para reset |
| **Benchmark WASM** | Usar `n < 170` para factorial (acima retorna `Infinity` → speedup = `NaN`) |

---

## Anti-Patterns (Proibidos)

| Anti-Pattern | Falha | Solução |
|---|---|---|
| Query imediato após `page.goto()` em SPA | App não hidratou | Aguardar evento/flag de hydration |
| `querySelector` em Web Component | Shadow DOM isola o elemento | Acessar via `shadowRoot` |
| `contentDocument` cross-origin | SecurityError (Same-Origin Policy) | `postMessage` ou screenshot |
| Keypress em input mascarado | Máscara não ativa | `el.value = raw` + `dispatchEvent('input')` |
| `awaitPromise=true` com `setTimeout` não-promisificado | WsRecv bloqueia indefinidamente | Promise wrapper ou `Start-Sleep` externo |
| `/json` endpoint no Edge moderno | Lista vazia | Usar `/json/list` |
| Retornar objeto complexo de `evaluate` | Serialização CDP falha | Retornar string `'k=v|k2=v2'` |
| Chamar `simularUpload()` após `simulateFileSelect()` | DOM refs quebradas no `setInterval` | Usar `getUploadState()` |
| `Notification.permission = 'granted'` | Propriedade read-only | Interceptar `requestPermission` |
| Reutilizar WS sem drain após navegação | IDs de resposta desalinhados | PING `id=99` + drain loop |

---

## Status dos Cenários Validados

20/20 cenários validados via CDP. Lições completas em `references/lab-extractions.md`.

> Para cenários específicos com código expandido, leia o arquivo de referência correspondente.
