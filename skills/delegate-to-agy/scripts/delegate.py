#!/usr/bin/env python3
"""delegate.py — cross-platform wrapper for `agy` (Antigravity / Gemini agent)

Hand a self-contained task to agy and print ONLY the distilled result to stdout,
so the calling agent (Claude) spends minimal context on heavy work.

WHY THIS WRAPPER EXISTS (hard-won, do not "simplify" away):
  * agy -p HANGS on tool-using tasks unless stdin is detached -> we use DEVNULL
  * piping agy through shell pipelines can swallow the final answer -> capture to file
  * the process timeout MUST be >= agy --print-timeout or heavy jobs get killed mid-task
  * agy has no JSON output flag -> the structured contract is requested IN-BAND (tags)
  * on Windows, agy may be installed as agy.cmd (npm shim) -> use shell=True on Windows
    OR shutil.which() to resolve the actual executable path first.

Usage:
  python delegate.py [--dir PATH]... [--timeout SECS] [--continue] [--raw] [--mode M] -- "TASK PROMPT"

Options:
  --dir PATH     Add a directory to agy's workspace (repeatable). Use for disk/code tasks.
  --timeout S    Hard wall-clock limit in seconds (default 600). Also sets agy print-timeout.
  --continue     Resume agy's most recent conversation (for "you missed X, redo", or a
                 follow-up on the same big doc, without re-sending context).
  --mode M       web | docs — inject extra evidence rules for that task type.
  --raw          Do NOT append the contract; print agy's output verbatim.
  --             Everything after is the task prompt (quote it).

Exit codes: 0 ok | 124 timeout | other = agy error (see stderr)
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

# ── constants ──────────────────────────────────────────────────────────────────

CONTRACT = """

---
INSTRUCOES DE SAIDA (obrigatorias — sem excecao):
- PROIBIDO narrar passos, explicar raciocinio, ou escrever qualquer texto fora das tags abaixo.
- PROIBIDO escrever QUALQUER coisa antes da primeira tag ou depois da ultima tag.
- Cada token fora das tags e desperdicado — nao existe "introducao util".
- Sua resposta COMPLETA deve ser exatamente estas tags, nesta ordem:
<RESULT>resposta direta ao pedido — sem preambulo, sem conclusao</RESULT>
<SOURCES>urls ou caminho:linha separados por ponto-e-virgula (vazio se nenhuma)</SOURCES>
<QUOTE>trecho verbatim — inclua APENAS se o modo exigir; omita a tag inteira caso contrario</QUOTE>
<CONFIDENCE>numero 0-100</CONFIDENCE>
<CAVEATS>premissas ou ambiguidades relevantes; o que nao conseguiu confirmar; vazio se nao houver</CAVEATS>"""

MODE_BLOCKS = {
    "web": """

REGRAS DE PESQUISA WEB (para eu confiar sem repesquisar):
- Corrobore com PELO MENOS 3 fontes INDEPENDENTES (publicadores diferentes, nao espelhos do mesmo feed). Se nao achar 3 independentes, diga em <CAVEATS> quantas achou.
- Para cada fonte, reporte o valor/fato SEPARADAMENTE em <SOURCES> (ex.: "valorA (urlA); valorB (urlB); valorC (urlC)"). Se divergirem, NAO faca media: mostre todos.
- SEMPRE inclua a DATA/timestamp do dado (nao so a data de hoje). Para algo de mercado, diga se e fechamento oficial de qual data, ou preco intraday.
- Em <QUOTE>, cole um TRECHO VERBATIM curto de uma fonte que sustenta a resposta (para eu localizar sem refazer a busca).
- Se as fontes divergirem ou o dado puder estar desatualizado, diga isso em <CAVEATS>.""",

    "docs": """

REGRAS DE CONSULTA A DOCUMENTACAO:
- Consulte PELO MENOS 3 fontes independentes sobre o topico (documentacao oficial, guias, referencias — nao espelhos do mesmo conteudo).
- Em <RESULT>, escreva um resumo consolidado das 3+ fontes. O leitor e uma IA — seja conciso: sem introducao, sem conclusao, sem frases de transicao, sem explicacoes pedagogicas. So os fatos relevantes para a pergunta, no menor numero de caracteres que ainda seja legivel.
- Em <QUOTE>, cole um trecho verbatim de UMA das fontes que ancora o ponto mais critico do resumo.
- Em <SOURCES>, liste a URL exata (ou caminho:linha) de CADA fonte consultada separada por ponto-e-virgula — deve ser possivel abrir o link e encontrar a informacao diretamente.
- Se as fontes divergirem, reporte os valores separados em <RESULT> e explique a divergencia em <CAVEATS>. Nao harmonize versoes conflitantes.
- Se algum aspecto da pergunta nao for coberto por nenhuma fonte, diga em <CAVEATS>.""",
}

TAGS = ["RESULT", "SOURCES", "QUOTE", "CONFIDENCE", "CAVEATS"]


# ── argument parsing ────────────────────────────────────────────────────────────

def parse_args(argv):
    dirs = []
    timeout = 600
    do_continue = False
    raw = False
    mode = ""
    prompt_parts = []

    i = 0
    in_prompt = False
    while i < len(argv):
        arg = argv[i]
        if in_prompt:
            prompt_parts.append(arg)
            i += 1
            continue
        if arg == "--dir":
            dirs += ["--add-dir", argv[i + 1]]
            i += 2
        elif arg == "--timeout":
            timeout = int(argv[i + 1])
            i += 2
        elif arg == "--continue":
            do_continue = True
            i += 1
        elif arg == "--raw":
            raw = True
            i += 1
        elif arg == "--mode":
            mode = argv[i + 1]
            i += 2
        elif arg == "--":
            in_prompt = True
            i += 1
        else:
            print(
                f"delegate.py: unknown option '{arg}' (did you forget '--' before the prompt?)",
                file=sys.stderr,
            )
            sys.exit(2)

    prompt = " ".join(prompt_parts)
    return dirs, timeout, do_continue, raw, mode, prompt


# ── agy binary resolution ───────────────────────────────────────────────────────

def find_agy():
    """Resolve the agy binary, handling Windows .cmd shims from npm."""
    agy_env = os.environ.get("AGY_BIN", "agy")
    found = shutil.which(agy_env)
    if found:
        return found
    # On Windows, npm-installed CLIs ship as agy.cmd; which() finds them on PATH
    # via PATHEXT, but a plain name lookup may miss them on some environments.
    if sys.platform == "win32":
        for ext in (".cmd", ".bat", ".exe", ".ps1"):
            candidate = shutil.which(agy_env + ext)
            if candidate:
                return candidate
    return None  # caller will error


# ── tag parser ──────────────────────────────────────────────────────────────────

def parse_tags(raw_text):
    # Use the LAST match of each tag, not the first. With --continue, agy reprints
    # the entire prior conversation (each earlier turn carries its own <RESULT>… tags)
    # and the NEW answer comes last. Grabbing the first match would return a stale
    # turn; the final occurrence is always the current response.
    found = {}
    for tag in TAGS:
        matches = re.findall(rf"<{tag}>(.*?)</{tag}>", raw_text, re.DOTALL | re.IGNORECASE)
        if matches:
            found[tag] = matches[-1].strip()
    return found


# ── main ────────────────────────────────────────────────────────────────────────

def main():
    argv = sys.argv[1:]
    if not argv:
        print(
            'delegate.py: no task prompt given. Usage: delegate.py [--dir P]... [--timeout S] -- "TASK"',
            file=sys.stderr,
        )
        sys.exit(2)

    dirs, timeout, do_continue, raw, mode, prompt = parse_args(argv)

    if not prompt:
        print(
            'delegate.py: no task prompt given. Usage: delegate.py [--dir P]... [--timeout S] -- "TASK"',
            file=sys.stderr,
        )
        sys.exit(2)

    agy_bin = find_agy()
    if agy_bin is None:
        print(
            "delegate.py: 'agy' not found on PATH. Set AGY_BIN env var or install Antigravity.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build full prompt
    mode_block = MODE_BLOCKS.get(mode, "")
    full_prompt = prompt if raw else (prompt + mode_block + CONTRACT)

    # Build agy command
    cmd = [agy_bin, "--dangerously-skip-permissions"]
    if do_continue:
        cmd.append("--continue")
    cmd.extend(dirs)
    cmd.extend(["--print-timeout", f"{timeout}s", "-p", full_prompt])

    # Capture to temp file — do NOT stream through pipes (can swallow last bytes)
    out_fd, out_path = tempfile.mkstemp(prefix="agy_delegate_", suffix=".txt")
    err_fd, err_path = tempfile.mkstemp(prefix="agy_delegate_err_", suffix=".txt")

    # ANTI-LOOP signal (CRITICAL): we are an AI (Claude) calling agy as a
    # down-worker. Export an unambiguous env var so agy's AGENTS.md knows NOT to
    # run any "escalate up to claude -p" protocol (e.g. reverse-delegate), which
    # would cause infinite recursion Claude->agy->claude->... agy can read this
    # via `printenv`. This does not depend on prompt content (defense in depth
    # alongside the output-contract carve-out).
    child_env = dict(os.environ)
    child_env["AGY_CALLED_BY_AI"] = "1"
    child_env["AGENT_CALLER"] = "claude-delegate-to-agy"

    try:
        with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
            # stdin=DEVNULL is CRITICAL: agy -p hangs on tool-using tasks otherwise.
            # shell=True on Windows resolves .cmd shims without needing the full path.
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                timeout=timeout,
                shell=(sys.platform == "win32"),
                env=child_env,
            )
        rc = proc.returncode

    except subprocess.TimeoutExpired:
        print(
            f"TIMEOUT after {timeout}s — task too large or agy stalled. Narrow the task or raise --timeout.",
            file=sys.stderr,
        )
        # Surface any partial output to help the caller decide
        try:
            partial = open(out_path, encoding="utf-8", errors="replace").read().strip()
            if partial:
                print("--- partial output ---", file=sys.stderr)
                print(partial, file=sys.stderr)
        except OSError:
            pass
        sys.exit(124)

    finally:
        os.close(out_fd)
        os.close(err_fd)

    # Read captured output
    try:
        output = open(out_path, encoding="utf-8", errors="replace").read()
    except OSError:
        output = ""

    if rc != 0:
        print(f"agy exited with code {rc}", file=sys.stderr)
        try:
            err_tail = open(err_path, encoding="utf-8", errors="replace").readlines()
            sys.stderr.writelines(err_tail[-15:])
        except OSError:
            pass
        _cleanup(out_path, err_path)
        if output:
            sys.stdout.write(output)
        sys.exit(rc)

    _cleanup(out_path, err_path)

    # Raw mode: skip tag parsing
    if raw:
        sys.stdout.write(output)
        sys.exit(0)

    # Parse and re-emit only the contract tags (strips narration)
    found = parse_tags(output)
    if not found:
        # CRITICAL: never return empty — surface raw so caller can judge
        sys.stdout.write(
            "[delegate.py: agy did not emit the expected tags — raw output below]\n"
        )
        sys.stdout.write(output.strip() + "\n")
        sys.exit(0)

    for tag in TAGS:
        if tag in found:
            sys.stdout.write(f"<{tag}>{found[tag]}</{tag}>\n")


def _cleanup(*paths):
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


if __name__ == "__main__":
    main()
