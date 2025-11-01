import requests
import re
import json
import sys
import time
import socket

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
        
        match = re.search(r'@(.+?):(\d+)', link)
        
        if not match:
            print(f"Skipping invalid link (Regex failed): {link}", file=sys.stderr)
            continue
            
        host = match.group(1).strip('[]')
        base_link = link.split('#')[0]
        
        try:
            # --- START: DNS Resolution ---
            # Try to resolve the host to an IP address
            # This will work for domains and also accept existing IPs
            try:
                ip_address = socket.gethostbyname(host)
            except socket.gaierror as e:
                # gaierror = Get Address Info Error (e.g., domain not found)
                print(f"Failed to resolve domain {host}: {e}", file=sys.stderr)
                country_code = "xXx" # Set to unknown
                flag = get_flag_emoji(country_code)
                new_name = f"{flag}{country_code}  ROSE—{index:02d}"
                renamed_list.append(f"{base_link}#{new_name}")
                continue # Skip to the next link in the loop
            # --- END: DNS Resolution ---

            # Now, we use the resolved ip_address to call the API
            api_url = f'http://ipwho.is/{ip_address}'
            
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            country_code = "xXx"
            
            if data.get('success'):
                country_code = data.get('country_code', 'xXx')
            else:
                api_message = data.get('message', 'Unknown API error')
                # We print the original host name in error for clarity
                print(f"API Error for {host} ({ip_address}): {api_message}", file=sys.stderr)

        except requests.RequestException as e:
            print(f"HTTP Error for host {host} ({ip_address}): {e}", file=sys.stderr)
            country_code = "xXx"
        except json.JSONDecodeError:
            print(f"Failed to parse JSON response for host {host}", file=sys.stderr)
            country_code = "xXx"
        
        flag = get_flag_emoji(country_code)
        new_name = f"{flag}{country_code}  ROSE—{index:02d}"
        renamed_list.append(f"{base_link}#{new_name}")

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
        
        # This will print the final list to stdout
        for config in new_configs:
            print(config)

    except FileNotFoundError:
        print(f"Error: {input_file} not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
