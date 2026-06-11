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

def check_local_rules(host: str, ip: str) -> Optional[str]:
    host_lower = host.lower()
    if host_lower.endswith(".ir") or "dadnode" in host_lower or "samanehha" in host_lower or "bardiadev" in host_lower:
        return "IR"
    if host_lower.endswith(".ru") or "team.ru" in host_lower or "videolinks.ru" in host_lower:
        return "RU"
    if "cloudflare" in host_lower or "fastly" in host_lower or host_lower.endswith(".xyz"):
        return "US"
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
                await asyncio.sleep(2)
            print(f"[API ERROR] Status {resp.status} for IP {ip} ({host})", file=sys.stderr)
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
        
    ip = await resolve_host(host)  
    if not ip:  
        print(f"[DNS FAILED] Index {index:02d}: Cannot resolve {host}. Setting to UN.", file=sys.stderr)
        country = "UN"  
    else:  
        country = await get_country_code(session, ip, host, cache, semaphore)  
        
    flag = get_flag_emoji(country)  
    return f"{base_link}#{flag}{country}  ROSE—{index:02d}"  
  
async def rename_configs_async(config_list: List[str]) -> List[str]:  
    cache: Dict[str, str] = {}  
    semaphore = asyncio.Semaphore(3)  
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
