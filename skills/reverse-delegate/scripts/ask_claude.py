#!/usr/bin/env python3
"""ask_claude.py — transport for the INVERTED delegation skill.

The agy agent (Gemini, cheap, the PO/manager) drives the whole task and calls
THIS to hand a high-leverage act (plan / review / handshake) to Claude Opus.
It is the mirror image of delegate.py: there Opus delegated DOWN to agy; here
agy delegates UP to Opus.

WHY A WRAPPER (same hard-won lessons as delegate.py, reversed):
  * `claude -p` must run with stdin detached (</dev/null) or it can hang.
  * capture stdout to a file, never pipe (pipes can swallow the final bytes).
  * `--setting-sources ""` so the nested Opus does NOT inherit the user's
    ~/.claude/CLAUDE.md / MEMORY.md (which tell it to delegate to agy -> would
    cause recursion + token bloat on the expensive meter). Verified: with this
    flag the nested model has no agy reflex.
  * `--continue` keeps the Opus side WARM across handshake rounds: round 2+
    re-sends only the delta, not brief+plan again.
  * `--output-format json` gives real token usage -> we log it per crossing so
    the user gets a MEASURED Opus-meter cost, not a guess.

HANDOFF IS ALWAYS BY FILE PATH (user rule): --in is read, --out is written.
Nothing of substance travels inline in argv.

Usage:
  ask_claude.py --in PATH --out PATH [--continue] [--task-dir DIR]
                [--role plan|review|handshake] [--timeout SECS]
                [--model M] [--extra "imperative line"]

Exit codes: 0 ok | 124 timeout | other = claude error (see stderr)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

# Imperative preamble injected before every payload. Tells Opus it is being
# managed by another AI, to be terse, and that it MAY object — but only via
# structured objections, never by silent override.
#
# NOTE: Opus answers DIRECTLY in its text response; the wrapper persists that
# response to --out. We deliberately do NOT ask Opus to use a write tool: in
# `claude -p` non-interactive mode tool writes hit the permission gate and waste
# turns, and Opus is a consultant that produces TEXT (plan/review/objections) —
# the agy side is what touches disk. So: no file-writing, no tool use, just text.
PREAMBLE = """\
Você está sendo GERIDO POR OUTRA IA (o agente "agy"), que é o PO/gestor desta tarefa.
Execute de forma direta: sem preâmbulo, sem narração, sem conversa, sem perguntar "posso ajudar",
sem usar ferramentas. Apenas LEIA o material abaixo e RESPONDA DIRETAMENTE no seu texto — uma
outra IA captura sua resposta automaticamente e a grava em disco. Não tente escrever arquivos.

Sua resposta deve conter SOMENTE o artefato pedido (o plano, a revisão, ou as objeções) — nada
de "aqui está", nada de explicar o que você vai fazer.

Você É LIVRE para questionar se identificar algo ruim, arriscado ou incoerente no material —
mas APENAS por objeções ESTRUTURADAS, nunca reescrevendo à revelia. Para objetar: consolide
suas objeções e sugestões de forma numerada e peça aprovação ao agy; não imponha mudanças.

{role_block}
"""

ROLE_BLOCKS = {
    "plan": (
        "TAREFA: gerar um PLANO DE IMPLEMENTAÇÃO a partir do brief.\n"
        "- Decida você o NÍVEL de detalhe pela complexidade: esqueleto de restrições (quais\n"
        "  arquivos/contratos/APIs) para tarefa clara; passo-a-passo para tarefa traiçoeira.\n"
        "- O agy é quem vai CODAR seguindo seu plano — escreva para um executor, não para um humano.\n"
        "- Se o brief tiver lacuna ou risco que comprometa o plano, levante como objeção estruturada."
    ),
    "handshake": (
        "TAREFA: o agy respondeu às suas objeções (aceitou algumas, rejeitou outras, com razões).\n"
        "Leia o contra-argumento e produza a PROPOSTA FINAL do plano incorporando o que foi aceito\n"
        "e respeitando o que foi rejeitado. Não reabra pontos já decididos pelo agy. Escreva o plano\n"
        "final consolidado — é a versão que o agy vai aprovar ou não."
    ),
    "review": (
        "TAREFA: REVISAR o diff de código que o agy escreveu seguindo o plano.\n"
        "- Foque em correção: bugs, casos de borda, contrato violado, regressão silenciosa.\n"
        "- Para cada achado: arquivo:linha, o problema, e a correção concreta. Seja específico.\n"
        "- Se estiver correto, diga claramente que aprova. Não invente trabalho."
    ),
    "": "",
}


def build_prompt(in_path, out_path, role, extra):
    role_block = ROLE_BLOCKS.get(role, "")
    if extra:
        role_block = (role_block + "\n" + extra).strip()
    return PREAMBLE.format(in_path=in_path, out_path=out_path, role_block=role_block)


def log_tokens(task_dir, role, data, fallback_chars):
    """Append a measured-usage line to tokens.log for the Opus meter total."""
    if not task_dir:
        return
    line = None
    usage = (data or {}).get("usage") or {}
    if usage:
        line = (
            f"{time.strftime('%Y-%m-%dT%H:%M:%S')} OPUS {role or 'call'} "
            f"in={usage.get('input_tokens', '?')} out={usage.get('output_tokens', '?')} "
            f"cache_read={usage.get('cache_read_input_tokens', '?')} "
            f"cache_create={usage.get('cache_creation_input_tokens', '?')} "
            f"cost_usd={(data or {}).get('total_cost_usd', '?')}"
        )
    else:
        line = (
            f"{time.strftime('%Y-%m-%dT%H:%M:%S')} OPUS {role or 'call'} "
            f"(no json usage) approx_chars={fallback_chars}"
        )
    try:
        os.makedirs(task_dir, exist_ok=True)
        with open(os.path.join(task_dir, "tokens.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--in", dest="in_path", required=True, help="input file Opus reads")
    ap.add_argument("--out", dest="out_path", required=True, help="file Opus writes")
    ap.add_argument("--continue", dest="do_continue", action="store_true",
                    help="resume the prior Opus conversation (warm handshake rounds)")
    ap.add_argument("--task-dir", dest="task_dir", default="",
                    help="dir for tokens.log (usually the task artifact dir)")
    ap.add_argument("--role", default="", choices=list(ROLE_BLOCKS.keys()),
                    help="plan | review | handshake — selects the imperative role block")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--extra", default="", help="extra imperative line appended to the role block")
    args = ap.parse_args()

    # claude is expected on PATH (normal npm install). shutil.which honors
    # PATHEXT on Windows, so it resolves claude.cmd there too — no manual
    # extension probing needed. Override with CLAUDE_BIN if it lives elsewhere.
    claude_bin = shutil.which(os.environ.get("CLAUDE_BIN", "claude"))
    if not claude_bin:
        print("ask_claude.py: 'claude' not found on PATH. Set CLAUDE_BIN if it is installed elsewhere.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.in_path):
        print(f"ask_claude.py: --in file not found: {args.in_path}", file=sys.stderr)
        sys.exit(2)

    try:
        material = open(args.in_path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        print(f"ask_claude.py: cannot read --in: {e}", file=sys.stderr)
        sys.exit(2)

    prompt = build_prompt(args.in_path, args.out_path, args.role, args.extra)
    full_prompt = prompt + "\n\n--- MATERIAL (" + args.in_path + ") ---\n" + material

    # --setting-sources "" isolates the nested Opus from user/project config
    # (no agy reflex from ~/.claude/CLAUDE.md). Opus only produces text — it does
    # not write files or use tools — so no --add-dir / permission flags needed.
    cmd = [
        claude_bin, "-p",
        "--model", args.model,
        "--setting-sources", "",
        "--output-format", "json",
    ]
    if args.do_continue:
        cmd.append("--continue")
    cmd.extend(["--", full_prompt])

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            # On Windows, claude ships as claude.cmd (npm shim); shell=True lets
            # it resolve without the full path. stdin=DEVNULL still applies.
            shell=(sys.platform == "win32"),
        )
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT after {args.timeout}s — task too large or claude stalled.", file=sys.stderr)
        sys.exit(124)

    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")

    if proc.returncode != 0:
        print(f"claude exited with code {proc.returncode}", file=sys.stderr)
        sys.stderr.write(stderr[-2000:])
        sys.exit(proc.returncode)

    # Parse JSON envelope; the model wrote --out itself, but we also capture the
    # textual result as a safety net and for token logging.
    data = None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        pass

    result_text = (data or {}).get("result", "") if data else stdout
    log_tokens(args.task_dir, args.role, data, len(result_text))

    if not result_text.strip():
        print("ask_claude.py: empty result from Opus.", file=sys.stderr)
        sys.stderr.write(stderr[-1000:])
        sys.exit(3)

    # The wrapper persists Opus's text response to --out (Opus does not write
    # files itself). This is the single source of the artifact the agy reads.
    try:
        with open(args.out_path, "w", encoding="utf-8") as f:
            f.write(result_text)
    except OSError as e:
        print(f"ask_claude.py: cannot write --out: {e}", file=sys.stderr)
        sys.exit(3)

    print(f"OK: wrote Opus {args.role or 'response'} to {args.out_path}")


if __name__ == "__main__":
    main()
