import asyncio  
import aiohttp  
import sys  
import socket  
import ipaddress
from urllib.parse import urlparse
from typing import List, Dict, Optional  
  
BACKUP_API_BASE = "http://ip-api.com/json"  
  
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
  
async def resolve_host(host: str) -> Optional[str]:
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass

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

async def fetch_location_with_retry(session: aiohttp.ClientSession, ip: str, host: str) -> Optional[str]:
    url = f"https://freeipapi.com/api/json/{ip}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                data = await resp.json()
                country = data.get("countryCode")
                if country and country != "-":
                    return country
    except Exception:
        pass
    return None

async def fetch_location_backup(session: aiohttp.ClientSession, ip: str, host: str) -> Optional[str]:  
    url = f"{BACKUP_API_BASE}/{ip}"  
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:  
            if resp.status == 200:
                data = await resp.json()  
                if data.get("status") == "success":
                    country = data.get("countryCode")  
                    if country and len(country) == 2:
                        return country  
            elif resp.status == 429:
                print(f"[COOL DOWN] Backup API 429 hit for {ip}. Sleeping 3s...", file=sys.stderr)
                await asyncio.sleep(3)
            return None  
    except Exception as e:
        print(f"[CONNECTION ERROR] Failed for IP {ip}: {e}", file=sys.stderr)
        return None  
  
async def get_country_code(  
    session: aiohttp.ClientSession,  
    ip: str,  
    host: str,  
    cache: Dict[str, str],  
    semaphore: asyncio.Semaphore,  
) -> str:  
    if ip in cache:  
        return cache[ip]  
        
    local_country = check_local_rules(host, ip)
    if local_country:
        cache[ip] = local_country
        return local_country

    async with semaphore:  
        country = await fetch_location_with_retry(session, ip, host)  
        if not country:  
            country = await fetch_location_backup(session, ip, host)
        if not country:  
            country = "UN"  
        cache[ip] = country  
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
        return f"{link.split('#')[0]}#🇺🇳UN  ROSE—{index:02d}"

    try:
        ip = await resolve_host(host)
        if not ip:
            country = check_local_rules(host, "") or "UN"
        else:
            country = await get_country_code(session, ip, host, cache, semaphore)
    except Exception as e:
        print(f"[LINK ERROR] index {index}, host '{host[:60]}': {e}", file=sys.stderr)
        country = "UN"

    flag = get_flag_emoji(country)
    return f"{base_link}#{flag}{country}  ROSE—{index:02d}"
  
async def rename_configs_async(config_list: List[str]) -> List[str]:  
    cache: Dict[str, str] = {}  
    semaphore = asyncio.Semaphore(2)  
    async with aiohttp.ClientSession() as session:  
        results = await asyncio.gather(*[  
            process_link(i, link, session, cache, semaphore)  
            for i, link in enumerate(config_list, 1)  
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
  
