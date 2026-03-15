# Lab Extractions — Código Expandido por Cenário

Referência detalhada das 11 extrações do laboratório de automação CDP.  
Carregar sob demanda a partir do SKILL.md — não carregar integralmente por padrão.

**Índice:**
- [E1 — Hydration React/Vue/Angular](#e1--hydration-reactvueangular)
- [E2 — Shadow DOM: Open, Closed e Aninhado](#e2--shadow-dom-open-closed-e-aninhado)
- [E3 — Iframes: Same-Origin, Cross-Origin e Aninhados](#e3--iframes-same-origin-cross-origin-e-aninhados)
- [E4 — Refresh Token Interceptor](#e4--refresh-token-interceptor)
- [E5 — Canvas / WebGL Screenshot](#e5--canvas--webgl-screenshot)
- [E6 — Formulários Mascarados (Receita Universal)](#e6--formulários-mascarados-receita-universal)
- [E7 — Overlays e Async com Timer via CDP](#e7--overlays-e-async-com-timer-via-cdp)
- [E8 — CDP Drain Pattern (PING id=99)](#e8--cdp-drain-pattern-ping-id99)
- [E9 — File Upload via CDP](#e9--file-upload-via-cdp)
- [E10 — LocalStorage e PWA Offline](#e10--localstorage-e-pwa-offline)
- [E11 — WebAssembly: Detecção e Benchmark](#e11--webassembly-detecção-e-benchmark)

---

## E1 — Hydration React/Vue/Angular

**Cenário:** SPA com React.lazy + Suspense — múltiplos estágios de loading.  
**Problema:** DOM ready não implica app pronto; queries falham em elementos ainda não montados.  
**Root cause:** `React.lazy()` e `Suspense` diferem rendering de componentes até chunks JS carregarem.

```javascript
// Opção A: custom event (requer instrumentação no app)
// No componente raiz do app:
useEffect(() => {
  window.__APP_HYDRATED__ = true;
  window.dispatchEvent(new CustomEvent('__REACT_HYDRATION_COMPLETE__'));
}, []);

// No script de automação:
await new Promise(resolve => {
  if (window.__APP_HYDRATED__) return resolve();
  window.addEventListener('__REACT_HYDRATION_COMPLETE__', resolve, { once: true });
});

// Opção B: aguardar desaparecimento de loader (sem instrumentação)
await page.waitForSelector('[data-testid="page-loader"]', { state: 'hidden' });

// Opção C: network idle (Playwright/Puppeteer)
await page.waitForLoadState('networkidle');

// Opção D: via CDP — polling por flag global
function WaitHydrated($ws) {
  # PowerShell: polling a cada 200ms, máximo 10s
  for ($i = 0; $i -lt 50; $i++) {
    $r = Eval "!!window.__APP_HYDRATED__"
    if ($r -eq 'true') { return }
    Start-Sleep -Milliseconds 200
  }
  throw "App não hidratou em 10s"
}
```

**Aplicável quando:** qualquer SPA com lazy loading, code splitting ou SSR com hydration.

---

## E2 — Shadow DOM: Open, Closed e Aninhado

**Cenário:** Web Components com shadow roots — elementos invisíveis ao `querySelector` padrão.  
**Problema:** `document.querySelector('.target')` retorna `null` para elementos dentro de shadow DOM.  
**Root cause:** Shadow DOM cria árvore DOM isolada; seletores CSS não atravessam shadow boundaries por padrão.

```javascript
// OPEN shadow root — acesso direto via .shadowRoot
const host    = document.querySelector('my-component');
const shadow  = host.shadowRoot;           // null se mode: 'closed'
const target  = shadow.querySelector('.inner-element');

// CLOSED shadow root — shadowRoot é null; alternativas:
// 1. Capturar via composedPath no evento
host.addEventListener('click', e => {
  const path = e.composedPath();           // inclui elementos dentro do shadow
  console.log('elemento clicado:', path[0]);
}, true);

// 2. CSS ::part() — se o componente expõe parts públicas
// my-component::part(submit-btn) { cursor: pointer; }
// Via JS não há acesso direto a parts; usar apenas para styling

// 3. Monkey-patch de Element.attachShadow (antes do componente inicializar)
const _orig = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(init) {
  return _orig.call(this, { ...init, mode: 'open' });   // força open
};
// CUIDADO: só funciona se executado antes da inicialização do Web Component

// NESTED shadow DOM — travessia recursiva por array de seletores
function queryDeepShadow(selectors) {
  return selectors.reduce((node, sel) => {
    const el = node.querySelector(sel);
    return el?.shadowRoot ?? el;
  }, document);
}
// Uso: queryDeepShadow(['app-root', 'user-card', '.email-field'])

// LISTAR todos os shadow roots acessíveis (debugging)
function listShadowRoots(root = document) {
  const hosts = [];
  root.querySelectorAll('*').forEach(el => {
    if (el.shadowRoot) {
      hosts.push(el);
      hosts.push(...listShadowRoots(el.shadowRoot));
    }
  });
  return hosts;
}
```

**Aplicável quando:** Web Components nativos, Lit, Stencil, Angular Elements, qualquer componente com `attachShadow`.

---

## E3 — Iframes: Same-Origin, Cross-Origin e Aninhados

**Cenário:** Conteúdo encapsulado em iframes, incluindo casos multi-nível.  
**Problema:** `contentDocument` lança `SecurityError` para iframes cross-origin.  
**Root cause:** Same-Origin Policy impede acesso ao DOM de origens distintas (protocolo + host + porta).

```javascript
// SAME-ORIGIN — acesso total
const iframe  = document.querySelector('#iframe-same');
const doc     = iframe.contentDocument;
const win     = iframe.contentWindow;
const element = doc.querySelector('.target');
win.someFunction();                          // chamar funções do iframe

// CROSS-ORIGIN — acesso bloqueado; workarounds:

// 1. postMessage (requer cooperação do iframe)
iframe.contentWindow.postMessage({ action: 'getData', key: 'result' }, 'https://trusted.com');
window.addEventListener('message', e => {
  if (e.origin !== 'https://trusted.com') return;   // validar origem SEMPRE
  console.log('resposta:', e.data);
});

// 2. Screenshot via CDP quando acesso DOM não é possível
// Runtime.evaluate: "document.querySelector('#iframe-same').getBoundingClientRect()"
// Page.captureScreenshot com clip baseado no boundingClientRect

// 3. CORS proxy (controle de ambos os lados)
// Servir o iframe via proxy que adiciona Access-Control-Allow-Origin: *

// NESTED iframes — acesso por índice recursivo
function getNestedIframe(indices) {
  return indices.reduce((doc, idx) => {
    const frames = doc.querySelectorAll('iframe');
    return frames[idx]?.contentDocument ?? null;
  }, document);
}
// Uso: getNestedIframe([0, 1])  // iframe[1] dentro do iframe[0]

// LISTAR todos os iframes e origens (debugging)
Array.from(document.querySelectorAll('iframe')).map((f, i) => ({
  index: i,
  src: f.src || f.srcdoc?.slice(0, 50),
  sameOrigin: (() => { try { return !!f.contentDocument; } catch { return false; } })()
}));
```

**Aplicável quando:** widgets de terceiros, payment iframes, embedded apps, SSO flows em iframe.

---

## E4 — Refresh Token Interceptor

**Cenário:** APIs que expiram tokens JWT mid-session com resposta 401.  
**Problema:** Requests falham silenciosamente após expiração do access token.  
**Root cause:** Access tokens têm TTL curto (5–60 min); sem interceptor, cada request 401 falha definitivamente.

```javascript
// Interceptor universal para window.fetch
const _fetch = window.fetch.bind(window);

window.fetch = async function(...args) {
  let response = await _fetch(...args);

  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (!refreshed) throw new Error('Refresh token inválido — re-autenticação necessária');

    // Reenviar request original com novo token
    const [input, init = {}] = args;
    const newInit = {
      ...init,
      headers: {
        ...(init.headers || {}),
        'Authorization': `Bearer ${window.__ACCESS_TOKEN__}`
      }
    };
    response = await _fetch(input, newInit);
  }

  return response;
};

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  const res = await _fetch('/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken })
  });

  if (!res.ok) return false;

  const { access_token } = await res.json();
  localStorage.setItem('access_token', access_token);
  window.__ACCESS_TOKEN__ = access_token;
  return true;
}
```

**Aplicável quando:** APIs com JWT, sessões OAuth2, qualquer endpoint que retorne 401 por token expirado.

---

## E5 — Canvas / WebGL Screenshot

**Cenário:** Conteúdo renderizado em `<canvas>` (WebGL, Three.js, games, charts).  
**Problema:** `toDataURL()` retorna imagem em branco para contextos WebGL.  
**Root cause:** WebGL descarta o framebuffer após cada frame por padrão (`preserveDrawingBuffer: false`).

```javascript
// Canvas 2D — funciona diretamente
const canvas2d  = document.querySelector('canvas');
const dataURL2d = canvas2d.toDataURL('image/png');

// WebGL — exige preserveDrawingBuffer no momento da criação do contexto
// Se o contexto já foi criado sem a flag, é tarde demais — usar screenshot via CDP

// Verificar contexto existente
const canvas = document.querySelector('canvas');
const ctx2d  = canvas.getContext('2d');
const ctxWgl = canvas.getContext('webgl') || canvas.getContext('webgl2');

if (ctxWgl) {
  // Testar se preserveDrawingBuffer está ativo
  const params = ctxWgl.getContextAttributes();
  console.log('preserveDrawingBuffer:', params.preserveDrawingBuffer);
  // Se false: usar Page.captureScreenshot via CDP em vez de toDataURL
}

// Criação correta (controle total sobre a página)
const gl = canvas.getContext('webgl', { preserveDrawingBuffer: true });
// Agora toDataURL() funciona após qualquer frame
const dataURL = canvas.toDataURL('image/png');

// Extrair pixel data via readPixels (WebGL)
const w = canvas.width, h = canvas.height;
const pixels = new Uint8Array(4 * w * h);
gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);

// Offscreen canvas em Worker — mensagem para o worker principal
// worker.postMessage({ type: 'screenshot' })
// worker.onmessage = ({ data }) => console.log(data.dataURL)
```

**Aplicável quando:** Three.js, Babylon.js, WebGL apps, canvas-based charts (Chart.js, D3 com canvas), games.

---

## E6 — Formulários Mascarados (Receita Universal)

**Cenário:** Inputs com máscara JS (CPF, CNPJ, CEP, cartão), selects, radios, checkboxes, campos condicionais.  
**Problema:** Atribuir `.value` diretamente não ativa a máscara; campo exibe valor raw ou não valida.  
**Root cause:** Bibliotecas de máscara (Cleave.js, IMask, vanilla) ouvem eventos DOM (`input`, `keyup`), não mutação de `.value`.

```javascript
// INPUT MASCARADO — receita universal
function fillMasked(id, rawValue) {
  const el = document.getElementById(id);
  el.focus();
  el.value = rawValue;                                           // dígitos sem formatação
  el.dispatchEvent(new Event('input',  { bubbles: true }));     // ativa máscara
  el.dispatchEvent(new Event('change', { bubbles: true }));     // notifica validators
  el.blur();
  return el.value;                                              // retorna valor formatado
}

// Exemplos:
fillMasked('cpf',    '12345678901');     // → '123.456.789-01'
fillMasked('cnpj',   '11222333000181'); // → '11.222.333/0001-81'
fillMasked('cep',    '01310100');       // → '01310-100'
fillMasked('cartao', '4111111111111111'); // → '4111 1111 1111 1111'

// Extrair valor sem máscara após apply
const raw = document.getElementById('cpf').value.replace(/\D/g, '');

// SELECT
function selectOption(id, value) {
  const el = document.getElementById(id);
  el.value = value;
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

// RADIO  ← .click() é mais confiável que .checked = true
//         aciona onclick handlers registrados pelo framework
document.querySelector('input[name="opcao"][value="sim"]').click();

// CHECKBOX com validator
function toggleCheckbox(id, state) {
  const el = document.getElementById(id);
  if (el.checked !== state) {
    el.checked = state;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('click',  { bubbles: true }));  // alguns validators ouvem click
  }
}

// CAMPOS CONDICIONAIS — acionar função geradora ANTES de tentar acessar o elemento
window.exibirSecaoDependente();           // ou: selecionar radio que aciona o campo
await new Promise(r => setTimeout(r, 100)); // micro-wait para render
document.getElementById('campoDinamico').value = 'valor';
document.getElementById('campoDinamico').dispatchEvent(new Event('input', { bubbles: true }));

// WIZARD / MULTI-STEP — chamar next programaticamente se botão não está acessível
window.proximoPasso?.();
// ou via CDP se botão tem z-index issue:
// document.querySelector('[data-action="next"]').click()
```

**Aplicável quando:** qualquer input com Cleave.js, IMask, jQuery Mask, vue-the-mask, Angular ngxMask, ou máscara vanilla.

---

## E7 — Overlays e Async com Timer via CDP

**Cenário:** Modais com z-index alto, loading spinners, operações com setTimeout.  
**Problema:** Playwright/Selenium falham em clicks com overlay; `awaitPromise=true` trava o recv loop.  
**Root cause:** CDP `Runtime.evaluate` executa JS diretamente, sem checar visibilidade ou pointer-events. `awaitPromise=true` só funciona com Promises reais — `setTimeout` não retorna Promise, causa deadlock no WebSocket recv.

```javascript
// OVERLAY — CDP ignora completamente z-index e pointer-events
window.fecharModal();           // funciona mesmo com overlay cobrindo tudo
window.confirmarAcao();
document.getElementById('btn-hidden').click();  // click em elemento "invisível"

// ASYNC com setTimeout — NÃO usar awaitPromise=true
// ERRADO (trava WsRecv):
// { expression: "buscarCEP('01310-100')", awaitPromise: true }  ← PROIBIDO com setTimeout

// CORRETO: Promise wrapper que encapsula o setTimeout
const expr = `
  new Promise(resolve => {
    buscarCEP('01310-100');
    setTimeout(() => resolve(document.getElementById('logradouro').value), 800);
  })
`;
WsSend @{ id=1; method='Runtime.evaluate'; params=@{
  expression=$expr; returnByValue=$true; awaitPromise=$true
}}
# awaitPromise=true funciona porque a expressão retorna uma Promise real

// ALTERNATIVA: Start-Sleep externo (mais simples para casos lineares)
WsSend @{ id=1; method='Runtime.evaluate'; params=@{
  expression="buscarCEP('01310-100')"; returnByValue=$true; awaitPromise=$false
}}
WsRecv | Out-Null
Start-Sleep -Seconds 1    # aguardar fora do contexto JS
$logradouro = Eval "document.getElementById('logradouro').value"

// TOAST / LOADING SPINNER — detectar conclusão de operação
function WaitForElement($selector, $timeoutMs = 5000) {
  $expr = "
    new Promise(resolve => {
      const obs = new MutationObserver(() => {
        if (document.querySelector('$selector')) { obs.disconnect(); resolve(true); }
      });
      obs.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => { obs.disconnect(); resolve(false); }, $timeoutMs);
    })
  "
  WsSend @{ id=1; method='Runtime.evaluate'; params=@{
    expression=$expr; returnByValue=$true; awaitPromise=$true
  }}
  (WsRecv | ConvertFrom-Json).result.result.value
}
```

**Aplicável quando:** modais de confirmação, loading overlays, formulários com validação assíncrona (busca de CEP, CNPJ, etc.).

---

## E8 — CDP Drain Pattern (PING id=99)

**Cenário:** Após Page.navigate, eventos CDP buffered desalinham IDs de resposta.  
**Problema:** `WsRecv` retorna eventos de navegação (DOMContentLoaded, load, console.log) com ids que não correspondem ao próximo `evaluate`.  
**Root cause:** `Page.navigate` gera múltiplos eventos assíncronos no WebSocket que chegam antes do próximo envio.

```powershell
# PADRÃO COMPLETO: navegar + drain + evaluate

# 1. Navegar
WsSend @{ id=2; method='Page.navigate'; params=@{ url='https://exemplo.com' } }
WsRecv | Out-Null     # consumir ACK da navegação
Start-Sleep -Seconds 2  # aguardar carregamento

# 2. DRAIN — enviar mensagem de id improvável (99) e ler até encontrá-la
WsSend @{ id=99; method='Runtime.evaluate'; params=@{
  expression="'PING'"; returnByValue=$true; awaitPromise=$false
}}

$count = 0
do {
  $raw = WsRecv | ConvertFrom-Json
  $count++
  # Opcional: logar ids recebidos durante drain para debugging
  # Write-Host "drain[$count]: id=$($raw.id)"
} while ($raw.id -ne 99 -and $count -lt 50)

if ($count -ge 50) { Write-Warning "Drain atingiu limite — WebSocket pode estar sujo" }

# 3. Agora o buffer está limpo — evaluate com id=1 retorna apenas nosso resultado
WsSend @{ id=1; method='Runtime.evaluate'; params=@{
  expression="document.title"; returnByValue=$true; awaitPromise=$false
}}
$title = (WsRecv | ConvertFrom-Json).result.result.value

# WRAPPER de navegação com drain integrado (usar sempre)
function NavigateTo($url) {
  WsSend @{ id=2; method='Page.navigate'; params=@{ url=$url } }
  WsRecv | Out-Null
  Start-Sleep -Seconds 2
  DrainWs   # função definida no SKILL.md principal
}
```

**Aplicável quando:** SEMPRE que usar `Page.navigate` antes de `Runtime.evaluate`. Regra absoluta.

---

## E9 — File Upload via CDP

**Cenário:** Inputs `type="file"`, drag-and-drop zones, previews de imagem.  
**Problema:** `input.files` é somente leitura — não pode ser atribuído diretamente.  
**Root cause:** Browsers bloqueiam atribuição programática de `files` por design de segurança (previne upload silencioso).

```javascript
// OPÇÃO 1: helper exposto na window (preferível se disponível)
if (typeof window.simulateFileSelect === 'function') {
  window.simulateFileSelect(['documento.pdf', 'foto.jpg']);
  // Verificar resultado sem executar upload real:
  const state = window.getUploadState?.();
  console.log('arquivos adicionados:', state);
}

// OPÇÃO 2: DataTransfer API (conteúdo sintético)
function simulateFileUpload(inputId, files) {
  const dt = new DataTransfer();
  files.forEach(({ name, content = '', type = 'application/octet-stream' }) => {
    dt.items.add(new File([content], name, { type }));
  });

  const input = document.getElementById(inputId);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return input.files.length;
}

simulateFileUpload('fileInput', [
  { name: 'relatorio.pdf', content: '%PDF-1.4...', type: 'application/pdf' },
  { name: 'foto.jpg', content: '',               type: 'image/jpeg' }
]);

// OPÇÃO 3: drag-and-drop drop event com DataTransfer
function simulateFileDrop(dropZoneSelector, files) {
  const dt = new DataTransfer();
  files.forEach(f => dt.items.add(new File([f.content || ''], f.name, { type: f.type })));

  const zone = document.querySelector(dropZoneSelector);
  zone.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true }));
  zone.dispatchEvent(new DragEvent('drop',     { dataTransfer: dt, bubbles: true }));
}

simulateFileDrop('#upload-zone', [{ name: 'arquivo.csv', type: 'text/csv' }]);

// ARMADILHA: simularUpload() com arquivos sintéticos
// Funções como simularUpload() frequentemente usam setInterval que acessa DOM
// elements que não existem para arquivos simulados → TypeError em refs quebradas.
// Usar getUploadState() para verificar estado sem acionar o upload real.
const uploadOk = window.getUploadState?.()?.count > 0;
```

**Aplicável quando:** formulários com upload, drag-and-drop file zones, image preview inputs.

---

## E10 — LocalStorage e PWA Offline

**Cenário:** PWAs com offline-first, sync de dados, teste de persistência.  
**Problema:** `navigator.onLine` é somente leitura; funções de simulação offline podem ser sobrescritas.  
**Root cause:** APIs de conectividade são controladas pelo browser, não pelo JS da página.

```javascript
// LIMPAR estado anterior (testes repetíveis)
window.limparCache?.() ?? localStorage.clear();
sessionStorage.clear();

// SALVAR via helper — setar input.value ANTES se a função lê o campo
document.getElementById('newData').value = 'meu dado importante';
window.salvarOffline?.();

// Alternativa: salvar diretamente no localStorage
localStorage.setItem('minha_chave', JSON.stringify({ data: 'valor', ts: Date.now() }));

// LER e verificar persistência
const dados = JSON.parse(localStorage.getItem('offline_data') || '[]');
console.log('itens salvos:', dados.length);

// LISTAR todas as chaves e tamanhos
Object.entries(localStorage).map(([k, v]) => ({
  key: k,
  size: v.length,
  isJSON: (() => { try { JSON.parse(v); return true; } catch { return false; } })()
}));

// SIMULAR offline via interceptação de fetch
const _fetch = window.fetch;
window.fetch = () => Promise.reject(new TypeError('Network request failed'));
// Para restaurar: window.fetch = _fetch

// CUIDADO com simularOffline()
// Muitas implementações chamam atualizarStatus() que relê navigator.onLine
// (que permanece true) → estado "offline" da UI pode não persistir.
// Verificar a implementação antes de confiar:
// window.simularOffline.toString()

// SERVICE WORKER — verificar estado e cache
async function swStatus() {
  const regs  = await navigator.serviceWorker.getRegistrations();
  const keys  = await caches.keys();
  const sizes = await Promise.all(keys.map(async k => {
    const c = await caches.open(k);
    return { cache: k, entries: (await c.keys()).length };
  }));
  return { registrations: regs.length, caches: sizes };
}
```

**Aplicável quando:** PWAs, apps com IndexedDB/localStorage, testes de sync offline, Service Worker caching.

---

## E11 — WebAssembly: Detecção e Benchmark

**Cenário:** Páginas com módulos WASM, benchmarks de performance, feature detection.  
**Problema:** Benchmark retorna `NaN` no speedup; detecção de suporte retorna falso positivo.  
**Root cause:** Função de benchmark com early-return para `n > 170` (factorial → `Infinity`) gera `timeJS = 0ms` → divisão `0/0 = NaN`.

```javascript
// DETECÇÃO de suporte WebAssembly (mínimo módulo válido)
const wasmSupported = (() => {
  try {
    if (typeof WebAssembly !== 'object') return false;
    // Magic number + version do formato WASM binário
    const module   = new WebAssembly.Module(
      Uint8Array.of(0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00)
    );
    return new WebAssembly.Instance(module) instanceof WebAssembly.Instance;
  } catch { return false; }
})();

// VERIFICAR APIs disponíveis
const wasmAPIs = {
  Memory:    typeof WebAssembly.Memory    === 'function',
  Table:     typeof WebAssembly.Table     === 'function',
  Module:    typeof WebAssembly.Module    === 'function',
  Instance:  typeof WebAssembly.Instance  === 'function',
  compile:   typeof WebAssembly.compile   === 'function',
  streaming: typeof WebAssembly.compileStreaming === 'function',
};

// BENCHMARK seguro — evitar a armadilha do early-return
function benchmarkSafe(fn, label, n = 50) {
  // n < 170 para factorial (acima: Infinity → timeJS ≈ 0 → NaN)
  const SAFE_N = Math.min(n, 150);

  const t0js  = performance.now();
  const resJs = fn(SAFE_N);                     // implementação JS pura
  const timeJs = performance.now() - t0js;

  const t0wasm  = performance.now();
  const resWasm = window.wasmFn?.(SAFE_N);      // implementação WASM
  const timeWasm = performance.now() - t0wasm;

  if (timeJs === 0 || timeWasm === 0) {
    console.warn(`${label}: tempo zerado — resultado muito rápido para medir ou early-return`);
    return null;
  }

  const speedup = (timeJs / timeWasm).toFixed(2);
  return { n: SAFE_N, timeJs, timeWasm, speedup, match: resJs === resWasm };
}

// CARREGAR módulo WASM de URL
async function loadWasm(url) {
  const response = await fetch(url);
  const buffer   = await response.arrayBuffer();
  const module   = await WebAssembly.compile(buffer);
  const imports  = {}; // preencher conforme exports do módulo
  const instance = await WebAssembly.instantiate(module, imports);
  return instance.exports;
}

// SharedArrayBuffer (threads WASM) — requer headers COOP/COEP
const sharedMemoryAvailable =
  typeof SharedArrayBuffer !== 'undefined' &&
  crossOriginIsolated;
```

**Aplicável quando:** páginas com módulos .wasm, benchmarks WASM vs JS, feature detection de capacidades do browser.
