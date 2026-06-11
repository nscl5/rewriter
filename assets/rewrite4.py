import asyncio  
import aiohttp  
import sys  
import socket  
import json
import urllib.request
from urllib.parse import urlparse
from typing import List, Dict, Optional  
  
PRIMARY_API_BASE = "https://who.victoriacross.ir/json"  
FALLBACK_API_BASE = "https://ipwho.is"  
THIRD_API_BASE = "https://ipapi.co"  # Added as a robust third layer 🤪
MAX_CONCURRENT_REQUESTS = 5  
INPUT_FILE = "conf.txt"  
  
  
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
    loop = asyncio.get_running_loop()  
    try:  
        return await loop.run_in_executor(None, socket.gethostbyname, host)  
    except socket.gaierror as e:  
        print(f"[DNS ERROR] Could not resolve host '{host}': {e}", file=sys.stderr)  
        return None  
  
  
async def fetch_from_primary(session: aiohttp.ClientSession, ip: str, host: str) -> Optional[str]:  
    url = f"{PRIMARY_API_BASE}/{ip}"  
    try:  
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:  
            if resp.status == 200:
                data = await resp.json()  
                if data.get("status") == "success":  
                    country = data.get("metadata", {}).get("country")  
                    if country:  
                        return country  
            elif resp.status == 429:
                await asyncio.sleep(2)
            print(f"[API ERROR] Primary API returned status {resp.status} for IP {ip} ({host})", file=sys.stderr)
            return None  
    except Exception as e:  
        print(f"[API TIMEOUT/ERROR] Primary API failed for IP {ip} ({host}): {e}", file=sys.stderr)  
        return None  
  
  
async def fetch_from_fallback(session: aiohttp.ClientSession, ip: str, host: str) -> Optional[str]:  
    url = f"{FALLBACK_API_BASE}/{ip}"  
    try:  
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:  
            if resp.status == 200:
                data = await resp.json()  
                if data.get("success") is True or "country_code" in data:
                    country = data.get("country_code")  
                    if country:  
                        return country  
            elif resp.status == 429:
                await asyncio.sleep(2)
            print(f"[API ERROR] Fallback API returned status {resp.status} for IP {ip} ({host})", file=sys.stderr)
            return None  
    except Exception as e:  
        print(f"[API TIMEOUT/ERROR] Fallback API failed for IP {ip} ({host}): {e}", file=sys.stderr)  
        return None  


def fetch_from_third_layer_sync(ip: str) -> Optional[str]:
    url = f"{THIRD_API_BASE}/{ip}/json/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                res_body = response.read().decode('utf-8')
                data = json.loads(res_body)
                country = data.get("country")
                if country and "error" not in data:
                    return country
    except Exception:
        pass
    return None


async def fetch_from_third_layer(ip: str) -> Optional[str]:  
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fetch_from_third_layer_sync, ip)
  
  
async def get_country_code(  
    session: aiohttp.ClientSession,  
    ip: str,  
    host: str,  
    cache: Dict[str, str],  
    semaphore: asyncio.Semaphore,  
) -> str:  
    if ip in cache:  
        return cache[ip]  
    async with semaphore:  
        country = await fetch_from_primary(session, ip, host)  
        if not country:  
            country = await fetch_from_fallback(session, ip, host)  
        if not country:  
            country = await fetch_from_third_layer(ip)
        if not country:  
            print(f"[LOCATION FAILED] All APIs failed to detect country for IP {ip} ({host}). Setting to UN.", file=sys.stderr)
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
        print(f"[CONFIG SKIPPED] Index {index:02d}: Link structure is invalid.", file=sys.stderr)
        return f"{link.split('#')[0]}#🇺🇳UN  ROSE—{index:02d}"  
        
    ip = await resolve_host(host)  
    if not ip:  
        print(f"[CONFIG UN] Index {index:02d}: DNS resolution failed for '{host}'. Setting to UN.", file=sys.stderr)
        country = "UN"  
    else:  
        country = await get_country_code(session, ip, host, cache, semaphore)  
        
    flag = get_flag_emoji(country)  
    return f"{base_link}#{flag}{country}  ROSE—{index:02d}"  
  
  
async def rename_configs_async(config_list: List[str]) -> List[str]:  
    cache: Dict[str, str] = {}  
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)  
    async with aiohttp.ClientSession() as session:  
        results = await asyncio.gather(*[  
            process_link(i, link, session, cache, semaphore)  
            for i, link in enumerate(config_list, 1)  
        ])  
    return [r for r in results if r]  
  
  
def main():  
    try:  
        with open(INPUT_FILE, "r", encoding="utf-8") as f:  
            configs = f.readlines()  
        if not configs:  
            print(f"Warning: {INPUT_FILE} is empty.", file=sys.stderr)  
        for config in asyncio.run(rename_configs_async(configs)):  
            print(config)  
    except FileNotFoundError:  
        print(f"Error: {INPUT_FILE} not found.", file=sys.stderr)  
        sys.exit(1)  
    except Exception as e:  
        print(f"Unexpected error: {e}", file=sys.stderr)  
        sys.exit(1)  
  
  
if __name__ == "__main__":  
    main()
