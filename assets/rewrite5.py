import asyncio  
import sys  
import socket  
import os
import geoip2.database
from urllib.parse import urlparse
from typing import List, Optional  
  
INPUT_FILE = "conf.txt"  
DB_PATH = "assets/GeoLite2-Country.mmdb"  
  
  
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
  
  
def lookup_geoip_offline(reader: geoip2.database.Reader, ip: str, host: str) -> str:
    try:
        response = reader.country(ip)
        country = response.country.iso_code
        if country:
            return country
    except geoip2.errors.AddressNotFoundError:
        print(f"[NOT FOUND] IP {ip} ({host}) not found in offline database.", file=sys.stderr)
    except Exception as e:
        print(f"[DB ERROR] Offline lookup failed for IP {ip} ({host}): {e}", file=sys.stderr)
    return "UN"
  
  
async def process_link(  
    index: int,  
    link: str,  
    reader: geoip2.database.Reader,  
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
        country = lookup_geoip_offline(reader, ip, host)  
        
    flag = get_flag_emoji(country)  
    return f"{base_link}#{flag}{country}  ROSE—{index:02d}"  
  
  
async def rename_configs_async(config_list: List[str]) -> List[str]:  
    if not os.path.exists(DB_PATH):
        print(f"[CRITICAL ERROR] GeoIP Database not found at {DB_PATH}!", file=sys.stderr)
        sys.exit(1)
        
    with geoip2.database.Reader(DB_PATH) as reader:
        results = await asyncio.gather(*[  
            process_link(i, link, reader)  
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
