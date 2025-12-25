import asyncio
import aiohttp
import re
import json
import sys
import socket
from typing import List, Dict, Optional

CLOUDFLARE_API_BASE = "https://app.nscl.ir"
USE_FALLBACK_API = True
MAX_CONCURRENT_REQUESTS = 20
INPUT_FILE = "conf.txt"

def get_flag_emoji(country_code: str) -> str:
    if not country_code or len(country_code) != 2:
        return "❓"
    country_code = country_code.upper()
    return "".join(chr(0x1F1E6 + ord(char) - ord('A')) for char in country_code)


def extract_host_and_base_link(link: str):
    link = link.strip()
    if not link:
        return None, None

    match = re.search(r'@(.+?):(\d+)', link)
    if not match:
        print(f"Skipping invalid link (Regex failed): {link}", file=sys.stderr)
        return None, None

    host = match.group(1).strip('[]')
    base_link = link.split('#')[0]
    return host, base_link


async def resolve_host(host: str) -> Optional[str]:
    loop = asyncio.get_running_loop()
    try:
        ip_address = await loop.run_in_executor(None, socket.gethostbyname, host)
        return ip_address
    except socket.gaierror as e:
        print(f"Failed to resolve domain {host}: {e}", file=sys.stderr)
        return None


async def fetch_country_from_cloudflare(
    session: aiohttp.ClientSession,
    ip_address: str,
    host: str
) -> Optional[str]:
    url = f"{CLOUDFLARE_API_BASE}/?ip={ip_address}"
    try:
        async with session.get(url, timeout=10) as resp:
            resp.raise_for_status()
            data = await resp.json()

        cf = data.get("cf", {})
        country_code = cf.get("country")
        if not country_code:
            print(
                f"Cloudflare API returned no country for {host} ({ip_address})",
                file=sys.stderr,
            )
            return None

        return country_code
    except aiohttp.ClientResponseError as e:
        print(
            f"Cloudflare API HTTP error for {host} ({ip_address}): {e.status} {e.message}",
            file=sys.stderr,
        )
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(
            f"Cloudflare API network error for {host} ({ip_address}): {e}",
            file=sys.stderr,
        )
    except json.JSONDecodeError:
        print(
            f"Cloudflare API JSON parse error for {host} ({ip_address})",
            file=sys.stderr,
        )
    except Exception as e:
        print(
            f"Cloudflare API unexpected error for {host} ({ip_address}): {e}",
            file=sys.stderr,
        )

    return None


async def fetch_country_from_fallback(
    session: aiohttp.ClientSession,
    ip_address: str,
    host: str
) -> Optional[str]:
    url = f"http://ip-api.com/json/{ip_address}"
    try:
        async with session.get(url, timeout=10) as resp:
            resp.raise_for_status()
            data = await resp.json()

        status = data.get("status")
        if status != "success":
            print(
                f"Fallback API error for {host} ({ip_address}): {data.get('message', 'unknown error')}",
                file=sys.stderr,
            )
            return None

        country_code = data.get("countryCode")
        return country_code
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(
            f"Fallback API network error for {host} ({ip_address}): {e}",
            file=sys.stderr,
        )
    except json.JSONDecodeError:
        print(
            f"Fallback API JSON parse error for {host} ({ip_address})",
            file=sys.stderr,
        )
    except Exception as e:
        print(
            f"Fallback API unexpected error for {host} ({ip_address}): {e}",
            file=sys.stderr,
        )

    return None


async def get_country_code(
    session: aiohttp.ClientSession,
    ip_address: str,
    host: str,
    cache: Dict[str, str],
    semaphore: asyncio.Semaphore,
) -> str:

    if ip_address in cache:
        return cache[ip_address]

    async with semaphore:
        country_code = await fetch_country_from_cloudflare(session, ip_address, host)

        if not country_code and USE_FALLBACK_API:
            country_code = await fetch_country_from_fallback(session, ip_address, host)

        if not country_code:
            country_code = "xXx"

        cache[ip_address] = country_code
        return country_code


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

    # DNS
    ip_address = await resolve_host(host)
    if not ip_address:
        country_code = "xXx"
    else:
        country_code = await get_country_code(
            session=session,
            ip_address=ip_address,
            host=host,
            cache=cache,
            semaphore=semaphore,
        )

    flag = get_flag_emoji(country_code)
    new_name = f"{flag}{country_code}  ROSE—{index:02d}"
    return f"{base_link}#{new_name}"


async def rename_ss_configs_async(config_list: List[str]) -> List[str]:
    renamed_list: List[str] = []
    cache: Dict[str, str] = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for index, link in enumerate(config_list, 1):
            task = process_link(
                index=index,
                link=link,
                session=session,
                cache=cache,
                semaphore=semaphore,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

    for res in results:
        if res:
            renamed_list.append(res)

    return renamed_list


def main():
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            original_configs = f.readlines()

        if not original_configs:
            print(f"Warning: {INPUT_FILE} is empty.", file=sys.stderr)

        new_configs = asyncio.run(rename_ss_configs_async(original_configs))

        for config in new_configs:
            print(config)

    except FileNotFoundError:
        print(f"Error: {INPUT_FILE} not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
