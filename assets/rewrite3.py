import asyncio
import aiohttp
import ipaddress
import socket
import sys
from typing import Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

PRIMARY_API_BASE = "https://who.victoriacross.ir/json"
FALLBACK_API_BASE = "https://ipwho.is"
MAX_CONCURRENT_REQUESTS = 20
INPUT_FILE = "conf.txt"

TLD_FALLBACK = {
    "ru": "RU",
    "de": "DE",
    "fr": "FR",
    "nl": "NL",
    "uk": "GB",
    "co.uk": "GB",
    "us": "US",
    "ca": "CA",
    "jp": "JP",
    "sg": "SG",
    "hk": "HK",
    "kr": "KR",
    "tr": "TR",
    "it": "IT",
    "es": "ES",
    "pl": "PL",
}


def get_flag_emoji(country_code: str) -> str:
    if not country_code or len(country_code) != 2:
        return "❓"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country_code.upper())


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def extract_host(link: str) -> Optional[str]:
    try:
        scheme = link.split("://", 1)[0].lower()

        if scheme not in {"ss", "vless", "trojan", "hy2", "hysteria2"}:
            return None

        parsed = urlsplit(link)
        return parsed.hostname
    except Exception:
        return None


def replace_fragment(link: str, fragment: str) -> str:
    parsed = urlsplit(link)
    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.query,
        fragment
    ))


async def resolve_host(host: str) -> Optional[str]:
    if is_ip(host):
        return host

    loop = asyncio.get_running_loop()

    try:
        infos = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        )

        for info in infos:
            ip = info[4][0]
            if ip:
                return ip

    except Exception as e:
        print(f"DNS failed for {host}: {e}", file=sys.stderr)

    return None


def guess_country_from_domain(host: str) -> Optional[str]:
    host = host.lower()

    for suffix, cc in sorted(TLD_FALLBACK.items(), key=lambda x: len(x[0]), reverse=True):
        if host.endswith("." + suffix) or host == suffix:
            return cc

    return None


async def fetch_primary(session: aiohttp.ClientSession, ip: str) -> Optional[str]:
    try:
        async with session.get(
            f"{PRIMARY_API_BASE}/{ip}",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                return None

            data = await resp.json()

            if data.get("status") == "success":
                cc = data.get("metadata", {}).get("country")
                if cc:
                    return cc.upper()

    except Exception:
        pass

    return None


async def fetch_fallback(session: aiohttp.ClientSession, ip: str) -> Optional[str]:
    try:
        async with session.get(
            f"{FALLBACK_API_BASE}/{ip}",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                return None

            data = await resp.json()

            if data.get("success") is True:
                cc = data.get("country_code")
                if cc:
                    return cc.upper()

    except Exception:
        pass

    return None


async def get_country_code(
    session: aiohttp.ClientSession,
    host: str,
    cache: Dict[str, str],
    semaphore: asyncio.Semaphore,
) -> str:

    ip = await resolve_host(host)

    cache_key = ip or host

    if cache_key in cache:
        return cache[cache_key]

    async with semaphore:

        country = None

        if ip:
            for _ in range(3):
                country = await fetch_primary(session, ip)
                if country:
                    break

            if not country:
                for _ in range(3):
                    country = await fetch_fallback(session, ip)
                    if country:
                        break

        if not country:
            country = guess_country_from_domain(host)

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

    host = extract_host(link)

    if not host:
        print(f"Skipping unsupported config: {link[:60]}", file=sys.stderr)
        return None

    country = await get_country_code(
        session=session,
        host=host,
        cache=cache,
        semaphore=semaphore,
    )

    flag = get_flag_emoji(country)

    new_name = f"{flag}{country}  ROSE—{index:02d}"

    return replace_fragment(link, new_name)


async def rename_configs_async(config_list: List[str]) -> List[str]:
    cache: Dict[str, str] = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(
        headers={"User-Agent": "ROSE-Renamer/2.0"}
    ) as session:

        results = await asyncio.gather(*[
            process_link(
                i,
                link,
                session,
                cache,
                semaphore
            )
            for i, link in enumerate(config_list, start=1)
        ])

    return [r for r in results if r]


def main():
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            configs = f.readlines()

        output = asyncio.run(rename_configs_async(configs))

        for item in output:
            print(item)

    except FileNotFoundError:
        print(f"Error: {INPUT_FILE} not found", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
