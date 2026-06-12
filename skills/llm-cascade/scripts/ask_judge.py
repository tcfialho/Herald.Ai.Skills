#!/usr/bin/env python3
"""ask_judge.py — transporte generico do llm-cascade (driver barato -> judge caro).

O driver (modelo barato: agy/haiku/codex/...) dirige a tarefa inteira e chama ESTE
script para os atos de alta alavancagem do judge (modelo forte): plan, handshake,
review. Evolucao do ask_claude.py do reverse-delegate, com:

  * REGISTRY DE PROVIDERS (config/providers.json): claude, claude-deepseek (env),
    codex, agy — trocar o judge = 1 linha de config ou 2 env vars. Multiplataforma
    (stdlib puro; cuidados win32 herdados do ask_claude.py).
  * RECEITA MINIMA claude: --tools "" + --system-prompt + --setting-sources ""
    derruba o overhead frio de ~35.3k para ~3.9k tokens (medido 2026-06-12).
  * ORCAMENTO MECANICO: state.json no task-dir conta chamadas por papel; estourou
    -> recusa com exit 75 (prompt nao segura roundtrip; codigo segura).
  * RESUME POR SESSION-ID (nunca --continue cego): handshake retoma a thread do
    plan; review roda FRIA por padrao (independencia do avaliador — o judge que
    escreveu o plano tende a aprovar codigo que o segue; payload leva o plano).
  * CONTRATO DE VEREDITO no review: 1a linha "VERDICT: APPROVE|FIX". Malformado
    -> 1 retry automatico; persiste malformado -> exit 4.
  * ANTI-LOOP: seta CASCADE_DEPTH+1 e AGY_CALLED_BY_AI=1 no ambiente do judge;
    recusa rodar se a propria profundidade ja for >= 2.

Handoff SEMPRE por arquivo: --in e lido, --out e escrito. Nada de substancia
viaja inline em argv (e prompt vai por stdin quando o provider suporta — evita
o limite de linha de comando do Windows).

Uso:
  ask_judge.py --role plan|handshake|review --in PATH --out PATH
               [--task-dir DIR] [--light] [--provider P] [--model M]
               [--timeout SECS] [--warm] [--force] [--extra "linha imperativa"]
  ask_judge.py --summary [--task-dir DIR]

Exit codes:
  0 ok | 2 erro de uso/config | 3 erro do provider/saida | 4 veredito malformado
  75 orcamento/profundidade recusados | 124 timeout
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

EXIT_USAGE = 2
EXIT_PROVIDER = 3
EXIT_VERDICT = 4
EXIT_BUDGET = 75
EXIT_TIMEOUT = 124

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "..", "config", "providers.json")
USER_CONFIG = os.path.join(os.path.expanduser("~"), ".config", "llm-cascade", "providers.json")

# ---------------------------------------------------------------- preambulos

PREAMBLE_COMMON = (
    "Você é o JUDGE (consultor sênior) numa cascata de modelos: outra IA, o driver "
    "(modelo barato), gere a tarefa, faz o trabalho braçal e gerencia você. Responda "
    "APENAS o artefato pedido — sem narração, sem cumprimento, sem oferta de ajuda. "
    "Sua resposta em texto é capturada automaticamente e gravada em disco; não use "
    "ferramentas, não tente escrever arquivos."
)

ROLE_SYSTEM = {
    "plan": PREAMBLE_COMMON + (
        " TAREFA: gerar um PLANO DE IMPLEMENTAÇÃO a partir do brief. O driver vai CODAR "
        "seguindo seu plano — escreva para um executor de IA: arquivos a tocar, contratos/"
        "assinaturas reais, passos na ordem, critérios de aceitação, riscos. Nível de "
        "detalhe proporcional ao risco (esqueleto para tarefa clara; passo-a-passo para "
        "tarefa traiçoeira). Máximo ~120 linhas. Se o brief tiver lacuna ou risco GRAVE "
        "que invalide qualquer plano, responda na primeira linha 'OBJECTIONS:' seguido de "
        "lista numerada (máx 5, 1-2 linhas cada) — objeções estruturadas, nunca pergunta "
        "aberta."
    ),
    "handshake": PREAMBLE_COMMON + (
        " TAREFA: o driver respondeu às suas objeções (aceitou/rejeitou, com razões). "
        "Produza o PLANO FINAL incorporando o que foi aceito e respeitando o que foi "
        "rejeitado — o driver é o árbitro; não reabra ponto decidido, não insista em "
        "objeção rejeitada. Responda SOMENTE o plano final consolidado."
    ),
    "review": PREAMBLE_COMMON + (
        " TAREFA: revisar o diff que o driver codou (o gate objetivo — testes/compilação — "
        "JÁ PASSOU). Foque no que teste não pega: bug real, caso de borda, contrato "
        "violado, regressão silenciosa, divergência do plano. NÃO aponte estilo nem "
        "preferência. FORMATO OBRIGATÓRIO — primeira linha: 'VERDICT: APPROVE' ou "
        "'VERDICT: FIX'; segunda linha: 'BLOCKERS: <n>'; depois os achados, um por item: "
        "'[B1] arquivo:linha — problema — correção concreta' (1-2 linhas cada; máx 6 "
        "blockers; blocker = erro de correção que causa comportamento errado). Nits "
        "não-bloqueantes: '[N1] ...' (máx 4). REGRAS JÁ DECIDIDAS (não pergunte): o driver "
        "vai aplicar TODOS os blockers sem consultar você e tratar nits como opcionais. É "
        "PROIBIDO terminar com pergunta, pedir aprovação ou oferecer opções. Se está "
        "correto: 'VERDICT: APPROVE', 'BLOCKERS: 0' e nada mais (nits opcionais)."
    ),
}

VERDICT_RE = re.compile(r"^VERDICT:\s*(APPROVE|FIX)\b", re.IGNORECASE)
BLOCKERS_RE = re.compile(r"^BLOCKERS:\s*(\d+)", re.IGNORECASE | re.MULTILINE)

RETRY_PROMPT = (
    "Sua resposta anterior NÃO seguiu o formato obrigatório. Reenvie a revisão COMPLETA "
    "começando exatamente com a linha 'VERDICT: APPROVE' ou 'VERDICT: FIX', depois "
    "'BLOCKERS: <n>', depois os achados '[B1] arquivo:linha — problema — correção'. "
    "Sem qualquer outro texto antes da primeira linha."
)

# ------------------------------------------------------------------- config


def deep_merge(base, extra):
    """Dicts mesclam recursivamente; qualquer outro valor substitui."""
    if not isinstance(base, dict) or not isinstance(extra, dict):
        return extra
    out = dict(base)
    for k, v in extra.items():
        out[k] = deep_merge(out.get(k), v) if k in out else v
    return out


def load_config():
    paths = [DEFAULT_CONFIG, USER_CONFIG]
    env_cfg = os.environ.get("CASCADE_CONFIG")
    if env_cfg:
        paths.append(env_cfg)
    cfg = {}
    loaded_any = False
    for p in paths:
        if p and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    cfg = deep_merge(cfg, json.load(f))
                loaded_any = True
            except (OSError, json.JSONDecodeError) as e:
                die(EXIT_USAGE, f"config invalida em {p}: {e}")
    if not loaded_any:
        die(EXIT_USAGE, f"nenhuma config encontrada (procurei: {', '.join(paths)})")
    return cfg


def resolve_provider(cfg, name, _seen=None):
    """Resolve a entry do provider aplicando 'inherits' (com guarda de ciclo)."""
    _seen = _seen or set()
    if name in _seen:
        die(EXIT_USAGE, f"ciclo de 'inherits' em providers: {name}")
    _seen.add(name)
    providers = cfg.get("providers", {})
    if name not in providers:
        die(EXIT_USAGE, f"provider '{name}' nao existe na config (tem: {', '.join(sorted(providers))})")
    entry = dict(providers[name])
    parent = entry.pop("inherits", None)
    if parent:
        entry = deep_merge(resolve_provider(cfg, parent, _seen), entry)
    return entry


def resolve_role(cfg, role, light, cli_provider, cli_model):
    """role do orcamento -> (provider_name, model) com overrides de env e CLI."""
    role_key = "judge.plan" if role in ("plan", "handshake") else (
        "judge.light" if light else "judge.review")
    spec = dict(cfg.get("roles", {}).get(role_key, {}))
    if not spec.get("provider"):
        die(EXIT_USAGE, f"role '{role_key}' sem provider na config")
    # env: global e por-papel (por-papel vence)
    env_suffix = {"judge.plan": "PLAN", "judge.review": "REVIEW", "judge.light": "LIGHT"}[role_key]
    for key, env_names in (
        ("provider", (f"CASCADE_JUDGE_{env_suffix}_PROVIDER", "CASCADE_JUDGE_PROVIDER")),
        ("model", (f"CASCADE_JUDGE_{env_suffix}_MODEL", "CASCADE_JUDGE_MODEL")),
    ):
        for env_name in env_names:
            val = os.environ.get(env_name)
            if val:
                spec[key] = val
                break
    if cli_provider:
        spec["provider"] = cli_provider
    if cli_model:
        spec["model"] = cli_model
    return spec["provider"], spec.get("model", "")


def expand_env_refs(value, provider_name):
    """Expande ${VAR} em valores de env do provider; var ausente = erro claro."""
    def sub(m):
        var = m.group(1)
        v = os.environ.get(var)
        if v is None:
            die(EXIT_USAGE, f"provider '{provider_name}' requer a env var {var}, que nao esta setada")
        return v
    return re.sub(r"\$\{(\w+)\}", sub, value)


# -------------------------------------------------------------------- state


def state_path(task_dir):
    return os.path.join(task_dir, "state.json")


def load_state(task_dir):
    p = state_path(task_dir)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            warn(f"state.json corrompido em {p}; recomecando contagem do zero")
    return {"calls": {}, "total_calls": 0, "sessions": {}, "history": []}


def save_state(task_dir, state):
    try:
        os.makedirs(task_dir, exist_ok=True)
        with open(state_path(task_dir), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
    except OSError as e:
        warn(f"nao consegui gravar state.json: {e}")


def check_budget(state, budgets, role, force):
    used = state["calls"].get(role, 0)
    cap = budgets.get(role)
    total_cap = budgets.get("total")
    if force:
        return
    if cap is not None and used >= cap:
        advice = {
            "review": ("Politica: aplique os blockers ja reportados, rode o gate e FINALIZE "
                       "reportando o que ficou. NAO chame review de novo."),
            "handshake": ("Politica: voce e o arbitro — decida com o material que tem, registre "
                          "o impasse no counter.md e va codar."),
            "plan": "Politica: siga com o plan.md existente; nao se replaneja no meio da tarefa.",
        }.get(role, "")
        die(EXIT_BUDGET, f"ORCAMENTO ESGOTADO: '{role}' ja usou {used}/{cap} chamadas nesta tarefa. {advice} "
                         "(--force apenas com aprovacao humana explicita.)")
    if total_cap is not None and state.get("total_calls", 0) >= total_cap:
        die(EXIT_BUDGET, f"ORCAMENTO TOTAL ESGOTADO: {state['total_calls']}/{total_cap} chamadas ao judge "
                         "nesta tarefa. Finalize com o que tem e reporte honestamente o estado.")


# ----------------------------------------------------------------- execucao


def build_argv(entry, model, system_text, prompt_text, out_path, session_id, resuming):
    subst = {
        "{model}": model,
        "{system}": system_text,
        "{prompt}": prompt_text,
        "{out_file}": out_path,
        "{session_id}": session_id or "",
        "{in_file}": "",
    }
    argv = []
    for item in entry.get("argv", []):
        if item == "@RESUME@":
            if resuming:
                for r in entry.get("resume_argv", []):
                    argv.append(_subst_item(r, subst))
            continue
        argv.append(_subst_item(item, subst))
    if resuming and "@RESUME@" not in entry.get("argv", []):
        for r in entry.get("resume_argv", []):
            argv.append(_subst_item(r, subst))
    return argv


def _subst_item(item, subst):
    for k, v in subst.items():
        if k in item:
            item = item.replace(k, v)
    return item


def run_provider(entry, provider_name, argv, prompt_text, timeout):
    exe = argv[0]
    resolved = shutil.which(os.environ.get("CASCADE_BIN_" + provider_name.upper().replace("-", "_"), exe))
    if not resolved:
        die(EXIT_USAGE, f"executavel '{exe}' do provider '{provider_name}' nao esta no PATH")
    argv = [resolved] + argv[1:]

    env = dict(os.environ)
    for k, v in (entry.get("env") or {}).items():
        env[k] = expand_env_refs(v, provider_name)
    # anti-loop: o judge sabe que e sub-trabalhador; nunca escala de volta
    env["CASCADE_DEPTH"] = str(int(os.environ.get("CASCADE_DEPTH", "0") or 0) + 1)
    env["AGY_CALLED_BY_AI"] = "1"

    use_stdin = entry.get("prompt_via", "argv") == "stdin"
    stdin_data = prompt_text.encode("utf-8") if use_stdin else None

    # win32: CLIs npm sao shims .cmd -> precisa do shell; list2cmdline preserva
    # args vazios ("" de --tools/--setting-sources) que o join ingenuo perderia.
    use_shell = sys.platform == "win32"
    cmd = subprocess.list2cmdline(argv) if use_shell else argv

    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            stdin=(None if use_stdin else subprocess.DEVNULL),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=use_shell,
            env=env,
        )
    except subprocess.TimeoutExpired:
        die(EXIT_TIMEOUT, f"TIMEOUT apos {timeout}s — tarefa grande ou provider travado. "
                          "Reacao: aumente --timeout e/ou rode em background; nao desista no 1o 124.")
    return proc


def json_path(data, dotted):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def extract_result(entry, proc, out_path):
    """-> (result_text, parsed_json_or_None)."""
    stdout = proc.stdout.decode("utf-8", "replace")
    spec = entry.get("result", "stdout")
    data = None
    if spec.startswith("json:"):
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout.strip(), None  # provider prometeu json e nao mandou: usa cru
        return (json_path(data, spec[5:]) or ""), data
    if spec.startswith("file:"):
        path = spec[5:].replace("{out_file}", out_path)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return f.read(), None
            except OSError:
                pass
        return stdout.strip(), None
    return stdout.strip(), None


def log_tokens(task_dir, role, provider_name, model, data, fallback_chars):
    usage = (data or {}).get("usage") or {}
    if usage:
        line = (f"{time.strftime('%Y-%m-%dT%H:%M:%S')} JUDGE {role} provider={provider_name} "
                f"model={model or '?'} in={usage.get('input_tokens', '?')} "
                f"out={usage.get('output_tokens', '?')} "
                f"cache_read={usage.get('cache_read_input_tokens', '?')} "
                f"cache_create={usage.get('cache_creation_input_tokens', '?')}")
    else:
        line = (f"{time.strftime('%Y-%m-%dT%H:%M:%S')} JUDGE {role} provider={provider_name} "
                f"model={model or '?'} (sem usage) approx_chars={fallback_chars}")
    try:
        os.makedirs(task_dir, exist_ok=True)
        with open(os.path.join(task_dir, "tokens.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    return usage


# ----------------------------------------------------------------- summary


def print_summary(task_dir):
    log = os.path.join(task_dir, "tokens.log")
    if not os.path.isfile(log):
        print(f"(sem tokens.log em {task_dir})")
        return
    per_role = {}
    with open(log, encoding="utf-8") as f:
        for line in f:
            m = re.search(r"JUDGE (\S+) provider=(\S+) model=(\S+)", line)
            if not m:
                continue
            role = m.group(1)
            agg = per_role.setdefault(role, {"calls": 0, "in": 0, "out": 0, "cache_read": 0, "cache_create": 0})
            agg["calls"] += 1
            for field in ("in", "out", "cache_read", "cache_create"):
                fm = re.search(rf"\b{field}=(\d+)", line)
                if fm:
                    agg[field] += int(fm.group(1))
    # Regra do usuario: consumo SEMPRE em tokens, nunca em valores monetarios.
    print(f"Consumo do judge (tokens) — {task_dir}")
    total = {"calls": 0, "in": 0, "out": 0, "cache_read": 0, "cache_create": 0}
    for role, agg in per_role.items():
        print(f"  {role:10s} calls={agg['calls']} in={agg['in']} out={agg['out']} "
              f"cache_read={agg['cache_read']} cache_create={agg['cache_create']}")
        for k in total:
            total[k] += agg[k]
    print(f"  {'TOTAL':10s} calls={total['calls']} in={total['in']} out={total['out']} "
          f"cache_read={total['cache_read']} cache_create={total['cache_create']}")
    st = load_state(task_dir)
    if st.get("last_verdict"):
        print(f"  ultimo veredito: {st['last_verdict']}")


# -------------------------------------------------------------------- main


def warn(msg):
    print(f"ask_judge.py: {msg}", file=sys.stderr)


def die(code, msg):
    print(f"ask_judge.py: {msg}", file=sys.stderr)
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--role", choices=["plan", "handshake", "review"])
    ap.add_argument("--in", dest="in_path", help="arquivo que o judge le")
    ap.add_argument("--out", dest="out_path", help="arquivo onde a resposta e gravada")
    ap.add_argument("--task-dir", default="", help="dir de state.json/tokens.log (default: dir do --out)")
    ap.add_argument("--light", action="store_true", help="usa o role judge.light (judge barato) no review")
    ap.add_argument("--provider", default="", help="override do provider da config")
    ap.add_argument("--model", default="", help="override do modelo")
    ap.add_argument("--timeout", type=int, default=0)
    ap.add_argument("--warm", action="store_true",
                    help="review retoma a sessao anterior (default: fria, por independencia)")
    ap.add_argument("--force", action="store_true", help="ignora orcamento (so com aprovacao humana)")
    ap.add_argument("--extra", default="", help="linha imperativa extra no system do judge")
    ap.add_argument("--summary", action="store_true", help="imprime totais de tokens da tarefa e sai")
    args = ap.parse_args()

    if args.summary:
        print_summary(args.task_dir or ".")
        return

    if not (args.role and args.in_path and args.out_path):
        die(EXIT_USAGE, "uso: --role plan|handshake|review --in PATH --out PATH (ou --summary)")

    depth = int(os.environ.get("CASCADE_DEPTH", "0") or 0)
    if depth >= 2:
        die(EXIT_BUDGET, f"CASCADE_DEPTH={depth}: profundidade de delegacao excedida — voce e um "
                         "sub-trabalhador; execute a tarefa diretamente, nao escale.")

    if not os.path.isfile(args.in_path):
        die(EXIT_USAGE, f"--in nao encontrado: {args.in_path}")
    task_dir = args.task_dir or os.path.dirname(os.path.abspath(args.out_path))

    cfg = load_config()
    provider_name, model = resolve_role(cfg, args.role, args.light, args.provider, args.model)
    entry = resolve_provider(cfg, provider_name)
    timeout = args.timeout or int(cfg.get("timeout_default", 600))
    budgets = cfg.get("budgets", {})

    state = load_state(task_dir)
    check_budget(state, budgets, args.role, args.force)

    try:
        material = open(args.in_path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        die(EXIT_USAGE, f"nao consegui ler --in: {e}")

    system_text = ROLE_SYSTEM[args.role]
    if args.extra:
        system_text += " " + args.extra.strip()

    # handshake retoma a thread do plan (mesmo provider); review e fria salvo --warm
    session_id = state.get("sessions", {}).get(provider_name, "")
    resuming = bool(session_id) and entry.get("resume_argv") and (
        args.role == "handshake" or (args.role == "review" and args.warm))
    if args.role == "handshake" and not resuming:
        warn("handshake sem sessao previa do plan — seguindo frio (judge le so o counter)")

    prompt_text = f"--- MATERIAL ({os.path.basename(args.in_path)}) ---\n{material}"
    if entry.get("system_via", "prompt") == "prompt":
        prompt_text = system_text + "\n\n" + prompt_text
        system_text_argv = ""
    else:
        system_text_argv = system_text

    argv = build_argv(entry, model, system_text_argv, prompt_text, args.out_path, session_id, resuming)
    proc = run_provider(entry, provider_name, argv, prompt_text, timeout)

    if proc.returncode != 0:
        warn(f"provider '{provider_name}' saiu com codigo {proc.returncode}")
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])
        sys.exit(EXIT_PROVIDER)

    result_text, data = extract_result(entry, proc, args.out_path)
    usage = log_tokens(task_dir, args.role, provider_name, model, data, len(result_text or ""))

    new_session = json_path(data or {}, entry.get("session", "")[5:]) if str(entry.get("session", "")).startswith("json:") else None
    if new_session:
        state.setdefault("sessions", {})[provider_name] = new_session

    if not (result_text or "").strip():
        warn("resposta vazia do judge.")
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-1000:])
        sys.exit(EXIT_PROVIDER)

    # ----- contrato de veredito (so review): 1 retry, depois exit 4
    verdict = blockers = None
    if args.role == "review":
        verdict, blockers = parse_verdict(result_text)
        if verdict is None:
            warn("review sem 'VERDICT:' na 1a linha — 1 retry automatico de formato")
            retry_prompt = RETRY_PROMPT
            retry_resuming = bool(new_session) and bool(entry.get("resume_argv"))
            if not retry_resuming:  # provider sem sessao: reenvia material com correcao no topo
                retry_prompt = RETRY_PROMPT + "\n\n" + prompt_text
            if entry.get("system_via", "prompt") == "prompt":
                retry_full = system_text + "\n\n" + retry_prompt
            else:
                retry_full = retry_prompt
            argv2 = build_argv(entry, model, system_text_argv, retry_full, args.out_path,
                               new_session or session_id, retry_resuming)
            proc2 = run_provider(entry, provider_name, argv2, retry_full, timeout)
            if proc2.returncode == 0:
                rt2, data2 = extract_result(entry, proc2, args.out_path)
                log_tokens(task_dir, args.role + "-retry", provider_name, model, data2, len(rt2 or ""))
                v2, b2 = parse_verdict(rt2 or "")
                if v2 is not None:
                    result_text, verdict, blockers = rt2, v2, b2

    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.out_path)), exist_ok=True)
        with open(args.out_path, "w", encoding="utf-8") as f:
            f.write(result_text)
    except OSError as e:
        die(EXIT_PROVIDER, f"nao consegui gravar --out: {e}")

    # orcamento conta apenas chamada logica BEM-SUCEDIDA (timeout/erro nao queimam)
    state["calls"][args.role] = state["calls"].get(args.role, 0) + 1
    state["total_calls"] = state.get("total_calls", 0) + 1
    state.setdefault("history", []).append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "role": args.role,
        "provider": provider_name, "model": model,
        "in": usage.get("input_tokens"), "out": usage.get("output_tokens"),
    })
    if verdict:
        state["last_verdict"] = f"{verdict} (blockers={blockers if blockers is not None else '?'})"
    save_state(task_dir, state)

    tok = f" tokens: in={usage.get('input_tokens','?')} out={usage.get('output_tokens','?')}" if usage else ""
    if args.role == "review":
        if verdict is None:
            warn(f"veredito AINDA malformado apos retry — leia {args.out_path} e decida voce.")
            print(f"ESCRITO: {args.out_path} (sem VERDICT valido).{tok}")
            sys.exit(EXIT_VERDICT)
        print(f"OK: review em {args.out_path}. VERDICT: {verdict} | BLOCKERS: "
              f"{blockers if blockers is not None else '?'}.{tok}")
        if verdict == "APPROVE" and (blockers or 0) == 0:
            print("(APPROVE sem blockers — nao precisa ler o arquivo; finalize.)")
    else:
        first = (result_text.strip().splitlines() or [""])[0][:80]
        print(f"OK: {args.role} em {args.out_path}. 1a linha: {first!r}.{tok}")


def parse_verdict(text):
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None, None
    m = VERDICT_RE.match(lines[0].strip())
    if not m:
        return None, None
    verdict = m.group(1).upper()
    bm = BLOCKERS_RE.search(text)
    return verdict, (int(bm.group(1)) if bm else None)


if __name__ == "__main__":
    main()
