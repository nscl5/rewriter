import requests
import re
import json
import sys
import time

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
        
        # Regex finds host:port, works with or without a '#' anchor
        match = re.search(r'@(.+?):(\d+)', link)
        
        if not match:
            print(f"Skipping invalid link (Regex failed): {link}", file=sys.stderr)
            continue
            
        host = match.group(1).strip('[]')
        base_link = link.split('#')[0]
        
        try:
            api_url = f'http://ipwho.is/{host}'
            
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            country_code = "XX" # Default
            
            # Check if API request was successful
            if data.get('success'):
                country_code = data.get('country_code', 'XX')
            else:
                api_message = data.get('message', 'Unknown API error')
                print(f"API Error for {host}: {api_message}", file=sys.stderr)

        except requests.RequestException as e:
            print(f"HTTP Error for host {host}: {e}", file=sys.stderr)
            country_code = "XX"
        except json.JSONDecodeError:
            print(f"Failed to parse JSON response for host {host}", file=sys.stderr)
            country_code = "XX"
        
        flag = get_flag_emoji(country_code)
        new_name = f"{flag} {country_code} - {index:02d}"
        renamed_list.append(f"{base_link}#{new_name}")

        # --- Rate Limit Change ---
        # Reduced sleep time, as this API is much more generous
        time.sleep(0.5) 

    return renamed_list

if __name__ == "__main__":
    input_file = 'conf.txt'
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            original_configs = f.readlines()
        
        if not original_configs:
            print(f"Warning: {input_file} is empty.", file=sys.stderr)
        
        new_configs = rename_ss_configs(original_configs)
        
        for config in new_configs:
            print(config)

    except FileNotFoundError:
        print(f"Error: {input_file} not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
