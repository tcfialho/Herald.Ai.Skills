#!/usr/bin/env python3
"""
SonarCloud Authentication — Selenium WebDriver (cross-browser)

Usage:
  python authenticate.py check          # Check if token exists and is valid
  python authenticate.py login          # Open browser, authenticate, generate token
  python authenticate.py login --name X # Custom token name

Output: JSON to stdout
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    sys.stderr.reconfigure(line_buffering=True, encoding="utf-8")

SONAR_BASE = "https://sonarcloud.io"
SONAR_API = f"{SONAR_BASE}/api"
TOKEN_DIR = Path.home() / ".sonarcloud"
TOKEN_FILE = TOKEN_DIR / "token"
LOGGED_IN_PATTERNS = [
    "sonarcloud.io/projects",
    "sonarcloud.io/account",
    "sonarcloud.io/dashboard",
    "sonarcloud.io/organizations",
]


def load_token():
    for var in ("SONAR_TOKEN", "SONARCLOUD_TOKEN", "SONAR_CLOUD"):
        token = os.environ.get(var, "").strip()
        if token:
            return token, "env"
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token, "file"
    return None, None


def save_token(token):
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")


def validate_token(token):
    req = urllib.request.Request(f"{SONAR_API}/authentication/validate")
    cred = base64.b64encode(f"{token}:".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
        return data.get("valid", False)
    except Exception:
        return False


def ensure_selenium():
    try:
        import selenium  # noqa: F401
        return True
    except ImportError:
        sys.stderr.write("Instalando selenium...\n")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "selenium", "--quiet"],
            timeout=120,
        )
        return True


def detect_and_create_driver():
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium import webdriver

    browsers = [
        ("Edge", webdriver.Edge, EdgeOptions),
        ("Chrome", webdriver.Chrome, ChromeOptions),
        ("Firefox", webdriver.Firefox, FirefoxOptions),
    ]

    no_first_run = ["--no-first-run", "--disable-default-apps"]

    for name, driver_cls, opts_cls in browsers:
        try:
            opts = opts_cls()
            if name != "Firefox":
                for flag in no_first_run:
                    opts.add_argument(flag)
            driver = driver_cls(options=opts)
            sys.stderr.write(f"Browser detectado: {name}\n")
            return driver, name
        except Exception:
            continue

    return None, None


def is_sonar_login_page(url):
    return "sonarcloud.io/login" in url or "sonarcloud.io/sessions/new" in url


def auto_click_azure_button(driver):
    from selenium.webdriver.common.by import By

    for _ in range(6):
        try:
            btn = driver.find_element(By.XPATH, "//button[contains(text(),'Azure DevOps')]")
            btn.click()
            return True
        except Exception:
            pass
        try:
            btn = driver.find_element(By.XPATH, "//button[.//img[@alt='Azure DevOps']]")
            btn.click()
            return True
        except Exception:
            pass
        time.sleep(2)
    return False


def wait_for_login(driver, timeout=180):
    for i in range(timeout // 2):
        time.sleep(2)
        try:
            url = driver.current_url
            if any(p in url for p in LOGGED_IN_PATTERNS):
                return True
        except Exception:
            pass
        if i % 15 == 14:
            sys.stderr.write(f"  Aguardando login... {(i+1)*2}s\n")
    return False


def extract_sonar_cookies(driver):
    all_cookies = driver.get_cookies()
    return {c["name"]: c["value"] for c in all_cookies if "sonarcloud" in c.get("domain", "")}


def generate_sonar_token(cookies, token_name):
    jwt = cookies.get("JWT-SESSION")
    xsrf = cookies.get("XSRF-TOKEN", "")
    if not jwt:
        return None, f"JWT-SESSION ausente. Cookies: {list(cookies.keys())}"

    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    unique_name = f"{token_name}-{int(time.time())}"

    req = urllib.request.Request(
        f"{SONAR_API}/user_tokens/generate",
        data=f"name={unique_name}".encode(),
        method="POST",
    )
    req.add_header("Cookie", cookie_str)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("X-XSRF-TOKEN", xsrf)

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200] if e.fp else ""
        return None, f"HTTP {e.code}: {body}"

    return data.get("token"), None


def do_check():
    token, source = load_token()
    if not token:
        return {"authenticated": False, "source": None}

    valid = validate_token(token)
    return {"authenticated": valid, "source": source if valid else None}


def do_login(token_name="cursor-sonar"):
    ensure_selenium()
    driver, browser_name = detect_and_create_driver()
    if not driver:
        return {"authenticated": False, "error": "Nenhum browser encontrado (Edge, Chrome, Firefox)"}

    try:
        sys.stderr.write("Navegando para SonarCloud...\n")
        driver.get(f"{SONAR_BASE}/sessions/new")
        time.sleep(5)

        current = driver.current_url
        if is_sonar_login_page(current):
            sys.stderr.write("Tela de login. Auto-clicando Azure DevOps...\n")
            auto_click_azure_button(driver)
            time.sleep(3)

        sys.stderr.write("Aguardando autenticacao no browser...\n")
        if not wait_for_login(driver):
            return {"authenticated": False, "error": "Timeout aguardando login (180s)"}

        sys.stderr.write("Login detectado! Gerando token...\n")
        cookies = extract_sonar_cookies(driver)
        token, err = generate_sonar_token(cookies, token_name)

        if not token:
            return {"authenticated": False, "error": err}

        if not validate_token(token):
            return {"authenticated": False, "error": "Token gerado mas nao validou"}

        save_token(token)
        return {
            "authenticated": True,
            "browser": browser_name,
            "token_file": str(TOKEN_FILE),
        }
    finally:
        driver.quit()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    args = sys.argv[2:]

    token_name = "cursor-sonar"
    for i, arg in enumerate(args):
        if arg == "--name" and i + 1 < len(args):
            token_name = args[i + 1]

    if mode == "check":
        result = do_check()
    elif mode == "login":
        result = do_login(token_name)
    else:
        result = {"error": f"Modo desconhecido: {mode}. Use 'check' ou 'login'."}

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
