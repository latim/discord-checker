import os
import sys

if sys.platform == 'win32':
    os.system('chcp 65001 > nul')

import random
import string
import itertools
import threading
import time
import asyncio
from queue import Queue

try:
    import requests
except ImportError:
    print("ERRO: a biblioteca 'requests' não está instalada.")
    print("Rode:  pip install requests")
    input("\nPressione Enter para sair...")
    sys.exit(1)

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    print("ERRO: a biblioteca 'colorama' não está instalada.")
    print("Rode:  pip install colorama")
    input("\nPressione Enter para sair...")
    sys.exit(1)

try:
    import aiohttp
    from aiohttp_socks import ProxyConnector
    from python_socks import ProxyError as _SocksProxyError
    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False

TURBO_THRESHOLD = 50
USERNAME_URL = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"

if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_path(filename):
    return os.path.join(SCRIPT_DIR, filename)

def load_proxies(filename="proxies.txt"):
    """
    Suporta blocos marcados por tipo, ex:

        ## http
        1.2.3.4:8080
        5.6.7.8:3128

        ## socks5
        9.9.9.9:1080

    Linhas sem marcador de bloco são tratadas como http (compatibilidade
    com listas antigas). Linhas começando com # (fora de um marcador ##)
    são ignoradas como comentário.
    Retorna lista de dicts prontos pra passar em requests(proxies=...).
    """
    path = get_path(filename)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "# um proxy por linha, agrupados em blocos por tipo:\n"
                "## http\n"
                "# ip:porta\n\n"
                "## socks4\n"
                "# ip:porta\n\n"
                "## socks5\n"
                "# ip:porta\n"
            )
        return []

    proxies = []
    current_scheme = "http"
    for raw_line in open(path, encoding="utf-8"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("##"):
            tag = line.lstrip("#").strip().lower()
            if tag in ("http", "socks4", "socks5"):
                current_scheme = tag
            continue
        if line.startswith("#"):
            continue

        raw_entry = line
        scheme = current_scheme
        if "://" in raw_entry:
            scheme, raw_entry = raw_entry.split("://", 1)
            scheme = scheme.strip().lower()
            if scheme not in ("http", "socks4", "socks5"):
                scheme = "http"

        parts = raw_entry.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            url = f"{scheme}://{user}:{password}@{host}:{port}"
        elif "@" in raw_entry:
            url = f"{scheme}://{raw_entry}"
        else:
            url = f"{scheme}://{raw_entry}"

        proxies.append({
            "http": url,
            "https": url,
            "_raw": url,
            "_scheme": scheme,
        })
    return proxies


CHARSETS = {
    "C": "bcdfghjklmnpqrstvwxyz",
    "V": "aeiou",
    "D": "0123456789",
    "L": "abcdefghijklmnopqrstuvwxyz",
    "Q": "abcdefghijklmnopqrstuvwxyz0123456789",
    "_": "_",
}

def parse_pattern(fmt):
    tokens = []
    i = 0
    while i < len(fmt):
        if fmt[i] == "[":
            end = fmt.index("]", i)
            inner = fmt[i + 1 : end]
            if len(inner) == 1:
                tokens.append(("lit", inner))
            else:
                tokens.append(("custom", inner))
            i = end + 1
        else:
            ch = fmt[i].upper()
            if ch in CHARSETS:
                tokens.append(("key", ch))
            else:
                tokens.append(("lit", fmt[i]))
            i += 1
    return tokens

def resolve_token(token):
    kind, val = token
    if kind == "key":
        return random.choice(CHARSETS[val])
    if kind == "custom":
        return random.choice(val)
    return val

def gen_from_pattern(fmt):
    return "".join(resolve_token(t) for t in parse_pattern(fmt))

def make_examples(fmt, n=2):
    return ", ".join(gen_from_pattern(fmt) for _ in range(n))

def all_combinations(fmt):
    tokens = parse_pattern(fmt)
    pools = []
    for kind, val in tokens:
        if kind == "key":
            pools.append(list(CHARSETS[val]))
        elif kind == "custom":
            pools.append(list(val))
        else:
            pools.append([val])
    for combo in itertools.product(*pools):
        yield "".join(combo)

def combo_count(fmt):
    tokens = parse_pattern(fmt)
    total = 1
    for kind, val in tokens:
        if kind == "key":
            total *= len(CHARSETS[val])
        elif kind == "custom":
            total *= len(val)
    return total

KEY_NAMES = {
    "C": "consoante",
    "V": "vogal",
    "D": "dígito",
    "L": "letra",
    "Q": "letra ou dígito",
    "_": "underscore",
}

def validate_pattern(fmt):
    """Retorna None se o padrão é válido, ou uma mensagem de erro em português."""
    if not fmt:
        return "O padrão não pode ser vazio."
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == "[":
            end = fmt.find("]", i + 1)
            if end == -1:
                return "Faltou fechar um colchete: todo [ precisa de um ] depois."
            inner = fmt[i + 1:end]
            if not inner:
                return "Tem um [] vazio. Coloque algo dentro, ex: [m] ou [ms]."
            if "[" in inner:
                return "Não dá pra colocar um colchete dentro de outro."
            i = end + 1
        elif ch == "]":
            return "Tem um ] sobrando, sem um [ antes dele."
        else:
            i += 1
    return None

def describe_pattern(fmt):
    """Traduz o padrão pra português. Ex: CV[m] -> consoante + vogal + 'm' fixo."""
    partes = []
    for kind, val in parse_pattern(fmt):
        if kind == "key":
            partes.append(KEY_NAMES[val])
        elif kind == "custom":
            partes.append("um destes: " + ", ".join(val))
        else:
            partes.append(f"'{val}' fixo")
    return " + ".join(partes)

def show_pattern_help():
    print(f"\n  {Fore.CYAN}Como montar o padrão{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Cada símbolo vira UM caractere do username. "
          f"Ex: {Fore.YELLOW}CVC{Fore.WHITE} = consoante + vogal + consoante.\n")
    print(f"    {Fore.YELLOW}C{Fore.WHITE}      consoante         (b, c, d, f, g...)")
    print(f"    {Fore.YELLOW}V{Fore.WHITE}      vogal             (a, e, i, o, u)")
    print(f"    {Fore.YELLOW}L{Fore.WHITE}      letra qualquer    (a até z)")
    print(f"    {Fore.YELLOW}D{Fore.WHITE}      dígito            (0 até 9)")
    print(f"    {Fore.YELLOW}Q{Fore.WHITE}      letra ou dígito")
    print(f"    {Fore.YELLOW}_{Fore.WHITE}      underscore")
    print(f"    {Fore.YELLOW}[x]{Fore.WHITE}    caractere fixo    ([m] = sempre a letra m)")
    print(f"    {Fore.YELLOW}[abc]{Fore.WHITE}  um destes         ([ms] = m ou s, sorteia um)")

    print(f"\n  {Fore.CYAN}Exemplos:{Style.RESET_ALL}")
    exemplos = [
        ("CVCVC",      "consoante e vogal alternando"),
        ("LLLDD",      "3 letras + 2 números"),
        ("LL_LL",      "2 letras, underscore, 2 letras"),
        ("[m][s]LLDD", "começa com ms + 2 letras + 2 números"),
        ("[ab]LLLL",   "começa com a ou b + 4 letras"),
    ]
    for pat, desc in exemplos:
        print(f"    {Fore.YELLOW}{pat:<12}{Fore.WHITE}{desc:<38}{Fore.LIGHTBLACK_EX}ex: {make_examples(pat, 3)}{Style.RESET_ALL}")

    print(f"\n  {Fore.LIGHTBLACK_EX}Dica: C, V, D, L e Q (maiúsculas ou minúsculas) são sempre símbolos. "
          f"Se quiser essas letras FIXAS no nome, coloque entre colchetes: [c] [v] [d] [l] [q].{Style.RESET_ALL}")

def ask_custom_pattern():
    while True:
        fmt = input(f"\n  {Fore.YELLOW}→ Digite o padrão (ex: CVCVC | ? = ajuda): {Style.RESET_ALL}").strip()
        if fmt == "?":
            show_pattern_help()
            continue
        erro = validate_pattern(fmt)
        if erro:
            print(f"  {Fore.RED}[erro]{Style.RESET_ALL} {erro}")
            continue
        print(f"\n  {Fore.MAGENTA}[i] Esse padrão vira: {describe_pattern(fmt)}{Style.RESET_ALL}")
        print(f"  {Fore.MAGENTA}[i] Exemplos: {make_examples(fmt, 5)}{Style.RESET_ALL}")
        ok = input(f"  {Fore.YELLOW}Está certo? (Enter = sim, n = digitar de novo): {Style.RESET_ALL}").strip().lower()
        if ok not in ("n", "nao", "não"):
            return fmt

BUILTIN = [
    ("CVCVC",        "CVCVC",        "Consonant-vowel pattern"),
    ("LL_LL",        "LL_LL",        "Letters underscore letters"),
    ("LLLDD",        "LLLDD",        "3 letters + 2 digits"),
    ("DDLLL",        "DDLLL",        "2 digits + 3 letters"),
    ("LLDLL",        "LLDLL",        "Letters-digit-letters"),
    ("QQQQQ",        "QQQQQ",        "5 alphanumeric chars"),
    ("CVDCV",        "CVDCV",        "Vowel-consonant with digit"),
]

print_lock = threading.Lock()
found_lock = threading.Lock()
found_available = False
check_delay = 0.15
fingerprint = None

proxies_list   = []
proxy_lock     = threading.Lock()
proxy_cycle    = None
dead_proxies   = set()
proxy_rl_until = {}

stats_lock = threading.Lock()
stats = {"checked": 0, "available": 0, "taken": 0, "errors": 0}
_last_render_time = [0.0]
MIN_RENDER_INTERVAL = 0.08

def set_console_title(title):
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)
            return
        except Exception:
            pass
    try:
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()
    except Exception:
        pass

def print_permanent(line):
    """Limpa a linha 'ao vivo' e imprime uma linha que fica de vez no histórico."""
    with print_lock:
        sys.stdout.write("\r\033[K")
        print(line)

def render_live(name, taken, err):
    """Sobrescreve a linha 'ao vivo' (uma checagem de cada vez), com throttle."""
    now = time.time()
    with print_lock:
        if now - _last_render_time[0] < MIN_RENDER_INTERVAL:
            return
        _last_render_time[0] = now
        if taken is True:
            line = f"  {Fore.RED}[-] INDISPONÍVEL {Fore.LIGHTBLACK_EX}│ {Fore.WHITE}{name:<15}{Style.RESET_ALL}"
        else:
            line = f"  {Fore.YELLOW}[!] ERRO         {Fore.LIGHTBLACK_EX}│ {Fore.YELLOW}{name:<15} {Fore.LIGHTBLACK_EX}({err}){Style.RESET_ALL}"
        sys.stdout.write("\r\033[K" + line)
        sys.stdout.flush()

def title_updater(stop_event):
    last_checked = 0
    last_time = time.time()
    set_console_title("Discord Checker | iniciando...")
    while not stop_event.is_set():
        stop_event.wait(0.5)
        with stats_lock:
            checked = stats["checked"]
            available = stats["available"]
        now = time.time()
        elapsed = now - last_time
        rate = (checked - last_checked) / elapsed if elapsed > 0 else 0.0
        last_checked = checked
        last_time = now
        set_console_title(f"Discord Checker | {checked:,} verificados | {rate:.0f}/s | {available} disponível(is)")
    with stats_lock:
        checked = stats["checked"]
        available = stats["available"]
    set_console_title(f"Discord Checker | finalizado | {checked:,} verificados | {available} disponível(is)")

def get_next_proxy():
    """
    Round-robin thread-safe pelos proxies vivos e fora de cooldown.
    Retorna (proxy_dict_ou_None, wait_seconds).
    wait_seconds > 0 significa "todos ocupados/em cooldown, espera esse tanto".
    wait_seconds == -1.0 significa "todos os proxies estão mortos".
    """
    if not proxies_list:
        return None, -1.0

    now = time.time()
    with proxy_lock:
        if len(dead_proxies) >= len(proxies_list):
            return None, -1.0

        attempts = 0
        best_wait = None
        while attempts < len(proxies_list):
            p = next(proxy_cycle)
            if p["_raw"] in dead_proxies:
                attempts += 1
                continue
            until = proxy_rl_until.get(p["_raw"], 0)
            if until <= now:
                return p, 0.0
            wait = until - now
            if best_wait is None or wait < best_wait:
                best_wait = wait
            attempts += 1
    return None, (best_wait or 1.0)

def mark_proxy_dead(proxy):
    if proxy:
        with proxy_lock:
            dead_proxies.add(proxy["_raw"])

def mark_proxy_rl(proxy, retry_after):
    if proxy:
        until = time.time() + retry_after + 0.5
        with proxy_lock:
            proxy_rl_until[proxy["_raw"]] = until

def get_fingerprint():
    """
    O client oficial do Discord busca isso em /experiments antes de checar
    username na tela de registro, e manda no header X-Fingerprint em toda
    request seguinte. Sem isso, o tráfego fica mais fácil de identificar
    como automação e o rate-limit costuma vir mais rápido/agressivo.
    Obtém usando os proxies disponíveis.
    """
    if not proxies_list:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    for p in proxies_list:
        proxy_dict = {"http": p["http"], "https": p["https"]}
        try:
            r = requests.get(
                "https://discord.com/api/v9/experiments",
                headers=headers,
                proxies=proxy_dict,
                timeout=6,
            )
            if r.status_code == 200:
                fp = r.json().get("fingerprint")
                if fp:
                    return fp
        except Exception:
            continue
    return None

def save_and_print(name, taken, err):
    with stats_lock:
        stats["checked"] += 1
        if taken is False:
            stats["available"] += 1
        elif taken is True:
            stats["taken"] += 1
        else:
            stats["errors"] += 1

    if taken is False:
        print_permanent(f"  {Fore.GREEN}{Style.BRIGHT}[+] DISPONÍVEL  {Fore.LIGHTBLACK_EX}│ {Fore.GREEN}{name:<15}{Style.RESET_ALL}")
        try:
            with open(get_path("found.txt"), "a", encoding="utf-8") as f:
                f.write(name + "\n")
        except Exception:
            pass
    else:
        render_live(name, taken, err)

def check_username(username, retries=3):
    """
    Endpoint público usado pela própria tela de registro do Discord
    pra checar disponibilidade de username. Não precisa de token/login.
    """
    if found_available:
        return None, "cancelado"
    url = USERNAME_URL
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if fingerprint:
        headers["X-Fingerprint"] = fingerprint

    attempt = 0
    while attempt <= retries:
        proxy, wait = get_next_proxy()
        
        if wait == -1.0:
            return None, "todos os proxies estão mortos"

        if wait > 0:
            time.sleep(wait)
            continue

        if not proxy:
            continue

        proxy_dict = {"http": proxy["http"], "https": proxy["https"]}

        try:
            r = requests.post(
                url, json={"username": username}, headers=headers,
                proxies=proxy_dict, timeout=8,
            )

            if r.status_code == 200:
                data = r.json()
                return data.get("taken"), None

            if r.status_code == 429:
                try:
                    retry_after = r.json().get("retry_after", 5.0)
                except Exception:
                    retry_after = 5.0
                mark_proxy_rl(proxy, retry_after)
                continue

            if r.status_code == 403:
                mark_proxy_dead(proxy)
                continue

            attempt += 1
            continue

        except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
            mark_proxy_dead(proxy)
            continue

        except Exception:
            attempt += 1
            continue

    return None, "esgotou tentativas de requisição"

def worker(q):
    global found_available
    while True:
        if found_available:
            break
        try:
            name = q.get(timeout=0.2)
        except Exception:
            if q.empty():
                break
            continue
        if name is None:
            break

        if found_available:
            q.task_done()
            break

        taken, err = check_username(name)

        if found_available:
            q.task_done()
            break

        save_and_print(name, taken, err)


        if err == "todos os proxies estão mortos":
            with print_lock:
                print(Fore.RED + "\n[CRÍTICO] Todos os proxies estão mortos. Parando o checker.")
            found_available = True
            while not q.empty():
                try:
                    q.get_nowait()
                    q.task_done()
                except Exception:
                    pass
            q.task_done()
            break
        time.sleep(check_delay)
        q.task_done()

_async_sessions = {}

def _get_async_session(proxy):
    """Uma sessão por proxy: reaproveita a conexão/TLS e evita handshake a cada checagem."""
    raw = proxy["_raw"]
    s = _async_sessions.get(raw)
    if s is None or s.closed:
        connector = ProxyConnector.from_url(raw)
        s = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=8))
        _async_sessions[raw] = s
    return s

async def check_username_async(username, retries=3):
    if found_available:
        return None, "cancelado"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if fingerprint:
        headers["X-Fingerprint"] = fingerprint

    attempt = 0
    while attempt <= retries:
        proxy, wait = get_next_proxy()
        if wait == -1.0:
            return None, "todos os proxies estão mortos"
        if wait > 0:
            await asyncio.sleep(wait)
            continue
        if not proxy:
            continue

        try:
            session = _get_async_session(proxy)
            async with session.post(USERNAME_URL, json={"username": username}, headers=headers) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    return data.get("taken"), None
                if r.status == 429:
                    try:
                        retry_after = (await r.json(content_type=None)).get("retry_after", 5.0)
                    except Exception:
                        retry_after = 5.0
                    mark_proxy_rl(proxy, retry_after)
                    continue
                if r.status == 403:
                    mark_proxy_dead(proxy)
                    continue
                attempt += 1
                continue
        except (asyncio.TimeoutError, aiohttp.ClientProxyConnectionError,
                aiohttp.ClientConnectorError, _SocksProxyError, OSError):
            mark_proxy_dead(proxy)
            continue
        except Exception:
            attempt += 1
            continue

    return None, "esgotou tentativas de requisição"

async def _async_worker(it):
    global found_available
    while not found_available:
        try:
            name = next(it)
        except StopIteration:
            return
        taken, err = await check_username_async(name)
        if found_available:
            return
        save_and_print(name, taken, err)
        if err == "todos os proxies estão mortos":
            with print_lock:
                print(Fore.RED + "\n[CRÍTICO] Todos os proxies estão mortos. Parando o checker.")
            found_available = True
            return
        if check_delay:
            await asyncio.sleep(check_delay)

async def _run_async(usernames, concurrency):
    concurrency = max(1, min(concurrency, len(proxies_list) - len(dead_proxies)))
    it = iter(usernames)
    workers = [asyncio.create_task(_async_worker(it)) for _ in range(concurrency)]
    try:
        await asyncio.gather(*workers)
    finally:
        for w in workers:
            w.cancel()
        for s in list(_async_sessions.values()):
            await s.close()
        _async_sessions.clear()
        await asyncio.sleep(0.25)

def run_with_threads(usernames, num_threads):
    global fingerprint
    turbo = num_threads > TURBO_THRESHOLD
    if turbo and not HAS_ASYNC:
        print(f"  {Fore.RED}[erro]{Style.RESET_ALL} Modo turbo precisa de aiohttp e aiohttp_socks.")
        print("  Rode:  pip install aiohttp aiohttp_socks\n")
        input("Pressione Enter para sair...")
        sys.exit(1)

    if fingerprint is None:
        fingerprint = get_fingerprint()
        with print_lock:
            if fingerprint:
                print(Fore.CYAN + f"  [ok] fingerprint obtido ({fingerprint[:20]}...)\n")
            else:
                print(Fore.YELLOW + "  [!] não consegui obter fingerprint, seguindo sem ele\n")

    with stats_lock:
        stats["checked"] = 0
        stats["available"] = 0
        stats["taken"] = 0
        stats["errors"] = 0

    os.system('cls' if os.name == 'nt' else 'clear')

    title_stop = threading.Event()
    title_thread = threading.Thread(target=title_updater, args=(title_stop,), daemon=True)
    title_thread.start()

    try:
        if turbo:
            asyncio.run(_run_async(usernames, num_threads))
        else:
            q = Queue(maxsize=num_threads * 4)
            threads = []
            for _ in range(num_threads):
                t = threading.Thread(target=worker, args=(q,), daemon=True)
                t.start()
                threads.append(t)

            for name in usernames:
                if found_available:
                    break
                q.put(name)

            q.join()

            for _ in threads:
                q.put(None)
            for t in threads:
                t.join()
    finally:
        title_stop.set()
        title_thread.join(timeout=1.0)
        with print_lock:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
        with stats_lock:
            print(f"  {Fore.CYAN}Verificados: {stats['checked']:,}  {Fore.LIGHTBLACK_EX}│  "
                  f"{Fore.GREEN}Disponíveis: {stats['available']}  {Fore.LIGHTBLACK_EX}│  "
                  f"{Fore.WHITE}Indisponíveis: {stats['taken']}  {Fore.LIGHTBLACK_EX}│  "
                  f"{Fore.YELLOW}Erros: {stats['errors']}{Style.RESET_ALL}")

def ask_generation_mode(fmt):
    print(f"\n  {Fore.CYAN}Modo de Geração:{Style.RESET_ALL}")
    print(f"    {Fore.WHITE}[1] Amostra aleatória (gerar N nomes)")
    print(f"    {Fore.WHITE}[2] Todas as combinações possíveis (exaustivo)\n")
    mode = input(f"  {Fore.YELLOW}Escolha o Modo: {Style.RESET_ALL}").strip()

    if mode == "2":
        total = combo_count(fmt)
        print(f"\n  {Fore.MAGENTA}[i] Este padrão possui {total:,} combinações possíveis.{Style.RESET_ALL}")
        confirm = input(f"  {Fore.YELLOW}Confirmar geração? (y/n): {Style.RESET_ALL}").strip().lower()
        if confirm != "y":
            print(f"  {Fore.RED}Cancelado.{Style.RESET_ALL}")
            sys.exit(0)
        usernames = list(all_combinations(fmt))
    else:
        try:
            count = int(input(f"  {Fore.YELLOW}Quantos nomes gerar? {Style.RESET_ALL}"))
        except ValueError:
            count = 100
        usernames = [gen_from_pattern(fmt) for _ in range(count)]

    return apply_ordering(usernames)

def apply_ordering(usernames):
    print(f"\n  {Fore.CYAN}Ordenação dos nomes:{Style.RESET_ALL}")
    print(f"    {Fore.WHITE}[1] Totalmente aleatório")
    print(f"    {Fore.WHITE}[2] Aleatório (sem duplicados)")
    print(f"    {Fore.WHITE}[3] Ordem alfabética\n")
    order = input(f"  {Fore.YELLOW}Escolha a Ordem: {Style.RESET_ALL}").strip()

    if order == "2":
        usernames = list(dict.fromkeys(usernames))
        random.shuffle(usernames)
    elif order == "3":
        usernames = sorted(set(usernames))
    else:
        random.shuffle(usernames)

    return usernames

def ask_threads():
    global check_delay
    print(f"\n  {Fore.CYAN}Configuração de Threads:{Style.RESET_ALL}")
    try:
        n = input(f"    {Fore.WHITE}Conexões simultâneas [1-1000] (até {TURBO_THRESHOLD} = threads, acima = turbo async, 1 proxy por checagem): {Style.RESET_ALL}").strip()
        n = int(n) if n else 3
        n = max(1, min(n, 1000))
    except ValueError:
        n = 3

    print(f"\n  {Fore.CYAN}Delay de Checagem:{Style.RESET_ALL}")
    d = input(f"    {Fore.WHITE}Delay entre requisições por thread em segundos (padrão: 0.3): {Style.RESET_ALL}").strip()
    if d:
        try:
            check_delay = max(0.0, float(d.replace(",", ".")))
        except ValueError:
            check_delay = 0.3

    return n


def show_banner():
    titulo = "Discord Username Checker"
    print(f"\n  {Fore.CYAN}{Style.BRIGHT}{titulo}{Style.RESET_ALL}")
    print(f"  {Fore.LIGHTBLACK_EX}{'─' * len(titulo)}{Style.RESET_ALL}")
    print(f"  {Fore.LIGHTBLACK_EX}{'by dex':>{len(titulo)}}{Style.RESET_ALL}")

def run():
    global proxies_list, proxy_cycle, dead_proxies, found_available

    dead_proxies = set()
    found_available = False

    proxies_list = load_proxies("proxies.txt")
    if not proxies_list:
        print(f"  {Fore.RED}[erro]{Style.RESET_ALL} O arquivo proxies.txt está vazio ou não existe.")
        print("  Este script foi configurado para funcionar APENAS com proxies.")
        print("  Insira seus proxies no arquivo proxies.txt (um por linha) e execute novamente.\n")
        input("Pressione Enter para sair...")
        sys.exit(1)

    has_socks = any(p["_scheme"] in ("socks4", "socks5") for p in proxies_list)
    if has_socks:
        try:
            import socks
        except ImportError:
            print(f"  {Fore.RED}[erro]{Style.RESET_ALL} Você tem proxies socks4/socks5 no proxies.txt mas falta a biblioteca pysocks.")
            print(f"  Rode:  pip install \"requests[socks]\"\n")
            input("Pressione Enter para sair...")
            sys.exit(1)

    proxy_cycle = itertools.cycle(proxies_list)
    counts = {}
    for p in proxies_list:
        counts[p["_scheme"]] = counts.get(p["_scheme"], 0) + 1
    resumo = ", ".join(f"{v} {k}" for k, v in counts.items())
    print(f"  {Fore.CYAN}[ok]{Style.RESET_ALL} {len(proxies_list)} proxies carregados ({resumo})\n")

    if len(sys.argv) == 3:
        try:
            fmt   = sys.argv[2]
            count = int(sys.argv[1])
            usernames = apply_ordering([gen_from_pattern(fmt) for _ in range(count)])
            threads   = ask_threads()
            print(f"\nChecking {len(usernames)} usernames with {threads} thread(s)...\n")
            run_with_threads(usernames, threads)
            return
        except Exception as e:
            print(f"Bad args: {e}")
            sys.exit(1)

    while True:
        print(f"\n  {Fore.CYAN}Padrão de Username:{Style.RESET_ALL}")
        print(f"    {Fore.WHITE}[1] Padrão personalizado (ex: CVCVC, LLLDD)")
        print(f"    {Fore.WHITE}[2] Ajuda (como usar e entender o CVCVC)")
        opcao_padrao = input(f"\n  {Fore.YELLOW}Escolha uma opção [1-2] (padrão: 1): {Style.RESET_ALL}").strip()
        if opcao_padrao == "2":
            show_pattern_help()
            input(f"\n  {Fore.YELLOW}Pressione Enter para voltar ao menu...{Style.RESET_ALL}")
            continue
        break

    fmt = ask_custom_pattern()
    usernames = ask_generation_mode(fmt)

    threads = ask_threads()
    print(f"\n  {Fore.CYAN}Iniciando checagem de {len(usernames)} usernames com {threads} thread(s)...{Style.RESET_ALL}\n")
    
    run_with_threads(usernames, threads)
    
    print(f"\n  {Fore.GREEN}Checagem finalizada!{Style.RESET_ALL}")
    if proxies_list:
        alive = len(proxies_list) - len(dead_proxies)
        print(f"  {Fore.CYAN}Proxies: {alive}/{len(proxies_list)} ainda vivos{Style.RESET_ALL}")

if __name__ == "__main__":
    while True:
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
            show_banner()
            run()
            
            print("\n" + "="*50)
            print(f"{Fore.GREEN}Execução finalizada com sucesso!")
            print("="*50)
            opcao = input("\nDigite 'r' para reiniciar e voltar ao início, ou qualquer outra tecla para sair: ").strip().lower()
            if opcao != 'r':
                print("Saindo...")
                break
        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}[!] Processo interrompido via Ctrl+C pelo usuário.")
            opcao = input(f"Deseja voltar ao início? (y/n): ").strip().lower()
            if opcao not in ('y', 's', 'sim'):
                print("Saindo...")
                break
        except SystemExit:
            break
        except Exception:
            import traceback
            print("\nOcorreu um erro inesperado:\n")
            traceback.print_exc()
            opcao = input("\nDeseja tentar reiniciar? (y/n): ").strip().lower()
            if opcao not in ('y', 's', 'sim'):
                break
