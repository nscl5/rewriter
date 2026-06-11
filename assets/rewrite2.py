import asyncio
import aiohttp
import re
import sys
import socket
from typing import List, Dict, Optional

PRIMARY_API_BASE = "https://who.victoriacross.ir/json"
FALLBACK_API_BASE = "https://ipwho.is"
MAX_CONCURRENT_REQUESTS = 20
INPUT_FILE = "conf.txt"


def get_flag_emoji(country_code: str) -> str:
    if not country_code or len(country_code) != 2:
        return "❓"
    return "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in country_code.upper())


def extract_host_and_base_link(link: str):
    link = link.strip()
    if not link:
        return None, None
    match = re.search(r'@(.+?):(\d+)', link)
    if not match:
        print(f"Skipping invalid link: {link}", file=sys.stderr)
        return None, None
    return match.group(1).strip('[]'), link.split('#')[0]


async def resolve_host(host: str) -> Optional[str]:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, socket.gethostbyname, host)
    except socket.gaierror as e:
        print(f"DNS resolve failed for {host}: {e}", file=sys.stderr)
        return None


async def fetch_from_primary(session: aiohttp.ClientSession, ip: str, host: str) -> Optional[str]:
    url = f"{PRIMARY_API_BASE}/{ip}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            data = await resp.json()
        if data.get("status") == "success":
            country = data.get("metadata", {}).get("country")
            if country:
                return country
        print(f"Primary API: no country for {host} ({ip})", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Primary API error for {host} ({ip}): {e}", file=sys.stderr)
        return None


async def fetch_from_fallback(session: aiohttp.ClientSession, ip: str, host: str) -> Optional[str]:
    url = f"{FALLBACK_API_BASE}/{ip}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            data = await resp.json()
        country = data.get("country_code")
        if country:
            return country
        print(f"Fallback API: no country for {host} ({ip})", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Fallback API error for {host} ({ip}): {e}", file=sys.stderr)
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
    async with semaphore:
        country = await fetch_from_primary(session, ip, host)
        if not country:
            country = await fetch_from_fallback(session, ip, host)
        if not country:
            country = "xXx"
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
        return None
    ip = await resolve_host(host)
    country = "xXx" if not ip else await get_country_code(session, ip, host, cache, semaphore)
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
