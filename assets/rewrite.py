import asyncio
import aiohttp
import sys
import socket
import ipaddress
from urllib.parse import urlparse
from typing import List, Dict, Optional

API_KEY = "ECAD2FAC632924BC3A0DD86BE8F22719"
IP_API_BASE = "https://api.ip2location.io/"
WHOIS_API_BASE = "https://api.ip2whois.com/v2"

def get_flag_emoji(country_code: str) -> str:
    if not country_code or len(country_code) != 2 or country_code == "UN":
        return "🇺🇳"
    return "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in country_code.upper())

def extract_host_and_base_link(link: str):
    link = link.strip()
    if not link:
        return None, None
    try:
        parsed = urlparse(link)
        if parsed.scheme:
            host = parsed.hostname
            if host:
                return host.strip('[]'), link.split('#')[0]
    except Exception as e:
        print(f"[PARSE ERROR] Failed to parse link: {link[:50]}... -> {e}", file=sys.stderr)
    return None, None

def has_allowed_scheme(link: str) -> bool:
    allowed = ("ss://", "hy2://", "hysteria://", "hysteria2://", "tuic://")
    return link.strip().startswith(allowed)

def is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False

async def resolve_host(host: str) -> Optional[str]:
    if is_ip_address(host):
        return host

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, socket.gethostbyname, host)
    except socket.gaierror as e:
        print(f"[DNS ERROR] Could not resolve host '{host}': {e}", file=sys.stderr)
        return None
    except UnicodeError as e:
        print(f"[DNS ERROR] Invalid hostname '{host[:60]}...': {e}", file=sys.stderr)
        return None

def check_local_rules(host: str, ip: str) -> Optional[str]:
    host_lower = host.lower()
    if host_lower.endswith(".ir") or any(kw in host_lower for kw in ["dadnode", "samanehha", "bardiadev", "havij", "ikco"]):
        return "IR"
    if host_lower.endswith(".ru") or any(kw in host_lower for kw in ["team.ru", "videolinks.ru", "moktana", "bystrivpn"]):
        return "RU"
    if "cloudflare" in host_lower or "fastly" in host_lower or host_lower.endswith(".xyz") or "freesocks" in host_lower:
        return "US"

    if ip:
        try:
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj in ipaddress.ip_network("104.16.0.0/12") or ip_obj in ipaddress.ip_network("172.64.0.0/13"):
                return "US"
            if ip_obj in ipaddress.ip_network("188.114.96.0/20"):
                return "NL"
        except Exception:
            pass
    return None

async def fetch_ip_geolocation(session: aiohttp.ClientSession, ip: str) -> Optional[str]:
    url = f"{IP_API_BASE}?key={API_KEY}&ip={ip}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                data = await resp.json()
                country = data.get("country_code")
                if country and country != "-":
                    return country
            elif resp.status == 429:
                print(f"[COOL DOWN] IP2Location 429 hit for {ip}. Sleeping 2s...", file=sys.stderr)
                await asyncio.sleep(2)
    except Exception as e:
        print(f"[CONNECTION ERROR] IP2Location failed for {ip}: {e}", file=sys.stderr)
    return None

async def fetch_domain_whois(session: aiohttp.ClientSession, domain: str) -> Optional[str]:
    url = f"{WHOIS_API_BASE}?key={API_KEY}&domain={domain}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                if "error" in data:
                    print(f"[WHOIS ERROR] {domain}: {data['error'].get('error_message')}", file=sys.stderr)
                    return None
                registrant = data.get("registrant", {})
                country = registrant.get("country")
                if country and len(country) == 2:
                    return country
            elif resp.status == 429:
                print(f"[COOL DOWN] IP2WHOIS 429 hit for {domain}. Sleeping 2s...", file=sys.stderr)
                await asyncio.sleep(2)
    except Exception as e:
        print(f"[CONNECTION ERROR] IP2WHOIS failed for {domain}: {e}", file=sys.stderr)
    return None

async def get_country_code(
    session: aiohttp.ClientSession,
    ip: Optional[str],
    host: str,
    cache: Dict[str, str],
    semaphore: asyncio.Semaphore,
) -> str:
    cache_key = ip if ip else host
    if cache_key in cache:
        return cache[cache_key]

    local_country = check_local_rules(host, ip or "")
    if local_country:
        cache[cache_key] = local_country
        return local_country

    async with semaphore:
        country = None
        if ip:
            country = await fetch_ip_geolocation(session, ip)
        if not country and not is_ip_address(host):
            country = await fetch_domain_whois(session, host)
        if not country:
            country = "UN"
        cache[cache_key] = country
        return country

async def process_link(
    index: int,
    link: str,
    session: aiohttp.ClientSession,
    cache: Dict[str, str],
    semaphore: asyncio.Semaphore,
) -> Optional[str]:
    link = link.strip()
    if not link:
        return None

    host, base_link = extract_host_and_base_link(link)
    if not host or not base_link:
        return f"{link.split('#')[0]}#🇺🇳 Rose—{index:02d}"

    try:
        ip = await resolve_host(host)
        country = await get_country_code(session, ip, host, cache, semaphore)
    except Exception as e:
        print(f"[LINK ERROR] index {index}, host '{host[:60]}': {e}", file=sys.stderr)
        country = "UN"

    flag = get_flag_emoji(country)
    return f"{base_link}#{flag} Rose—{index:02d}"

async def rename_configs_async(config_list: List[str]) -> List[str]:
    filtered = [link for link in config_list if has_allowed_scheme(link)]
    cache: Dict[str, str] = {}
    semaphore = asyncio.Semaphore(3)
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[
            process_link(i, link, session, cache, semaphore)
            for i, link in enumerate(filtered, 1)
        ])
    return [r for r in results if r]

def main():
    input_file = "conf.txt"
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            configs = f.readlines()
        if not configs:
            print(f"Warning: {input_file} is empty.", file=sys.stderr)
        for config in asyncio.run(rename_configs_async(configs)):
            print(config)
    except FileNotFoundError:
        print(f"Error: {input_file} not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
