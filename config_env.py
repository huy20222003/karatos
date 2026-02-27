import sys
import os
import re
from pathlib import Path

PROTECTED_KEYS = {
    "MEMORY_KEY",
    "MCP_CONFIG_PATH",
    "LOG_DIR",
    "LOG_LEVEL",
    "OLLAMA_HEADERS"
}

def parse_args():
    """
    Parses sys.argv for environment variable overrides.
    Returns a dictionary of key-value pairs, skipping protected keys.
    """
    overrides = {}
    args = sys.argv[1:]
    
    # Filter out --view and --help from being treated as env keys
    filtered_args = [a for a in args if a not in ("--view", "--help", "-h")]
    
    i = 0
    while i < len(filtered_args):
        arg = filtered_args[i]
        if arg.startswith("--"):
            key_part = arg[2:]
            if "=" in key_part:
                key, value = key_part.split("=", 1)
            else:
                key = key_part
                if i + 1 < len(filtered_args) and not filtered_args[i+1].startswith("--"):
                    value = filtered_args[i+1]
                    i += 1
                else:
                    value = "true"
            
            upper_key = key.upper()
            if upper_key in PROTECTED_KEYS:
                print(f"Warning: Access denied for protected key: {upper_key}")
            else:
                overrides[upper_key] = value
        i += 1
    return overrides

def view_values(target_keys=None, env_path=None):
    """
    Reads and prints current values from .env.
    """
    if env_path is None:
        env_path = Path(__file__).parent / ".env"
    
    path = Path(env_path)
    if not path.exists():
        print(f"Error: .env file not found at {path.absolute()}")
        return

    # Normalize target keys to uppercase
    search_keys = {k.upper() for k in target_keys} if target_keys else set()
    
    print(f"\n--- Current Values in {path.name} ---")
    
    found_any = False
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            # Match KEY=VALUE (ignoring comments)
            match = re.match(r'^([^#=]+)=(.*)$', stripped)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                
                # Show if:
                # 1. No target keys specified (show all public)
                # 2. Key is in target keys
                if (not search_keys and key not in PROTECTED_KEYS) or (key in search_keys):
                    display_value = "[REDACTED]" if key in PROTECTED_KEYS else value
                    status = "[PROTECTED]" if key in PROTECTED_KEYS else ""
                    print(f"  {key} = {display_value} {status}")
                    found_any = True
    
    if not found_any and search_keys:
        print("  No matching keys found.")
    print("-" * 30 + "\n")

def update_env_file(overrides, env_path=None):
    """
    Updates the .env file with provided overrides.
    Preserves comments and formatting where possible.
    """
    if env_path is None:
        env_path = Path(__file__).parent / ".env"
    
    path = Path(env_path)
    if not path.exists():
        print(f"Error: .env file not found at {path.absolute()}")
        return False

    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        # Match KEY=VALUE (ignoring comments)
        match = re.match(r'^([^#=]+)=(.*)$', stripped)
        
        if match:
            key = match.group(1).strip()
            # Double check protection during write
            if key in overrides and key not in PROTECTED_KEYS:
                new_lines.append(f"{key}={overrides[key]}\n")
                updated_keys.add(key)
                print(f"Updated: {key}")
                continue
        
        new_lines.append(line)

    # Append new keys that weren't found in the file
    for key, value in overrides.items():
        if key not in updated_keys and key not in PROTECTED_KEYS:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")
            print(f"Added: {key}")

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    return True

def show_help(env_path=None):
    """
    Lists all available keys from the .env file, excluding protected ones.
    """
    if env_path is None:
        env_path = Path(__file__).parent / ".env"
        
    path = Path(env_path)
    if not path.exists():
        print(f"Error: .env file not found at {path.absolute()}")
        return

    print(f"\nAvailable parameters in {path.name} (Public):")
    print("-" * 30)
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            # Match KEY=VALUE (ignoring comments)
            match = re.match(r'^([^#=]+)=', stripped)
            if match:
                key = match.group(1).strip()
                if key not in PROTECTED_KEYS:
                    print(f"  --{key}")
    
    print("-" * 30)
    print("Features:")
    print("  - Case-insensitive: --ollama_model_name works same as --OLLAMA_MODEL_NAME")
    print("  - View mode: Use --view to see current values without changing them")
    print("\nUsage:")
    print("  python config_env.py --KEY VALUE       (Set value)")
    print("  python config_env.py --KEY --view      (View specific value)")
    print("  python config_env.py --view            (View all public values)\n")

def main():
    # Robust resolution: target the .env file in the same directory as this script
    env_path = Path(__file__).parent / ".env"

    if "--help" in sys.argv or "-h" in sys.argv:
        show_help(env_path)
        return

    if "--view" in sys.argv:
        # Get requested keys (anything starting with -- that isn't --view)
        target_keys = [a[2:] for a in sys.argv[1:] if a.startswith("--") and a != "--view"]
        view_values(target_keys, env_path)
        return

    overrides = parse_args()
    if not overrides:
        print("No overrides provided. Use --help to see available parameters.")
        return

    if update_env_file(overrides, env_path):
        print(f"Successfully updated {env_path.absolute()}")
    else:
        print("Failed to update .env file.")

if __name__ == "__main__":
    main()
