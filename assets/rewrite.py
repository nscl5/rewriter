import requests
import re
import json
import sys

def get_flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return "❓"
    country_code = country_code.upper()
    return "".join(chr(0x1F1E6 + ord(char) - ord('A')) for char in country_code)

def rename_ss_configs(config_list):
    renamed_list = []
    
    for index, link in enumerate(config_list, 1):
        link = link.strip()
        if not link:
            continue
            
        match = re.search(r'@(.+?):(\d+)#', link)
        if not match:
            print(f"Skipping invalid link: {link}", file=sys.stderr)
            continue
            
        host = match.group(1).strip('[]')
        base_link = link.split('#')[0]
        
        try:
            response = requests.get(f'http://ip-api.com/json/{host}?fields=status,countryCode')
            response.raise_for_status()
            data = response.json()
            
            country_code = "XX"
            if data.get('status') == 'success':
                country_code = data.get('countryCode', 'XX')
            
            flag = get_flag_emoji(country_code)
            new_name = f"{flag} {country_code} - {index:02d}"
            renamed_list.append(f"{base_link}#{new_name}")

        except Exception as e:
            print(f"API Error for host {host}: {e}", file=sys.stderr)
            flag = "❓"
            new_name = f"{flag} Unknown - {index:02d}"
            renamed_list.append(f"{base_link}#{new_name}")

    return renamed_list

if __name__ == "__main__":
    try:
        with open('conf.txt', 'r') as f:
            original_configs = f.readlines()
        
        new_configs = rename_ss_configs(original_configs)
        
        for config in new_configs:
            print(config)

    except FileNotFoundError:
        print("Error: conf.txt file not found.", file=sys.stderr)
        sys.exit(1)
