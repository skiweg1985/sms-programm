#!/usr/bin/env python3
"""
SMS sending via Teltonika Router
Uses the router's REST API to send SMS messages.
"""

import requests
import json
import sys
import os
import argparse
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
import urllib3

# YAML-Support
try:
    import yaml
except ImportError:
    print("✗ Error: PyYAML is not installed. Install it with: pip install pyyaml")
    sys.exit(1)

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def split_at_word_boundary(text: str, max_length: int) -> tuple[str, str]:
    """
    Splits text at a word boundary if possible.
    
    Args:
        text: Text to split
        max_length: Maximum length of the first part
    
    Returns:
        Tuple (first_part, rest)
    """
    if len(text) <= max_length:
        return text, ""
    
    # Search for word boundaries (spaces, line breaks, tabs)
    # Go backwards from max_length to find the best split point
    best_split = max_length
    
    # Search for spaces, line breaks, tabs
    for i in range(max_length, max(0, max_length - 20), -1):
        if i < len(text) and text[i] in (' ', '\n', '\t', '\r'):
            best_split = i + 1  # Cut after the separator
            break
    
    # If no space found, search for other separators
    if best_split == max_length:
        for i in range(max_length, max(0, max_length - 10), -1):
            if i < len(text) and text[i] in ('.', ',', ';', ':', '!', '?', '-', '–', '—'):
                best_split = i + 1
                break
    
    # If still nothing found, hard split (only if really necessary)
    if best_split == max_length:
        best_split = max_length
    
    return text[:best_split].rstrip(), text[best_split:].lstrip()


def split_sms_message(message: str, max_length: int = 160, add_numbering: bool = True) -> List[str]:
    """
    Splits a long SMS message into multiple parts.
    Only splits at word boundaries to avoid splitting words.
    
    Args:
        message: Message to split
        max_length: Maximum length per SMS (default: 160 characters)
        add_numbering: If True, adds numbering (e.g. "1/3: ", "2/3: ", "3/3: ")
    
    Returns:
        List of message parts (with numbering if enabled)
    """
    if not message:
        return [""]
    
    if len(message) <= max_length:
        return [message]
    
    if add_numbering:
        # Estimate number of parts
        estimated_parts = (len(message) + max_length - 1) // max_length
        
        # Calculate maximum length of numbering prefix
        # For up to 999 parts: "999/999: " = 9 characters
        max_numbering_length = len(f"{estimated_parts}/{estimated_parts}: ")
        
        # Reduce available length by numbering
        available_length = max_length - max_numbering_length
        
        # Split message at word boundaries
        parts = []
        remaining_text = message
        
        while remaining_text:
            if len(remaining_text) <= available_length:
                # Rest fits in one part
                parts.append(remaining_text)
                break
            
            # Split at word boundary
            part, remaining_text = split_at_word_boundary(remaining_text, available_length)
            if part:
                parts.append(part)
            else:
                # Fallback: If no word found, hard split
                parts.append(remaining_text[:available_length])
                remaining_text = remaining_text[available_length:].lstrip()
        
        # Now we know the actual number of parts
        total_parts = len(parts)
        
        # Update available length with actual numbering length
        actual_numbering_length = len(f"{total_parts}/{total_parts}: ")
        actual_available_length = max_length - actual_numbering_length
        
        # If actual numbering is longer, we need to re-split the parts
        if actual_numbering_length > max_numbering_length:
            # Re-split with correct length
            parts = []
            remaining_text = message
            while remaining_text:
                if len(remaining_text) <= actual_available_length:
                    parts.append(remaining_text)
                    break
                part, remaining_text = split_at_word_boundary(remaining_text, actual_available_length)
                if part:
                    parts.append(part)
                else:
                    parts.append(remaining_text[:actual_available_length])
                    remaining_text = remaining_text[actual_available_length:].lstrip()
            total_parts = len(parts)
        
        # Add numbering to each part
        numbered_parts = []
        for i, part in enumerate(parts, 1):
            numbered_part = f"{i}/{total_parts}: {part}"
            
            # Safety check: If SMS is too long
            if len(numbered_part) > max_length:
                # If still too long, remove trailing spaces or split again
                prefix = f"{i}/{total_parts}: "
                remaining_length = max_length - len(prefix)
                if remaining_length > 0:
                    # Split part again at word boundary
                    sub_part, _ = split_at_word_boundary(part, remaining_length)
                    numbered_parts.append(f"{prefix}{sub_part}")
                    # Rest will be handled in next iteration (should not occur)
                else:
                    # Fallback: Use part without numbering (should not occur)
                    numbered_parts.append(part)
            else:
                numbered_parts.append(numbered_part)
        
        return numbered_parts
    else:
        # No numbering - split at word boundaries
        parts = []
        remaining_text = message
        while remaining_text:
            if len(remaining_text) <= max_length:
                parts.append(remaining_text)
                break
            part, remaining_text = split_at_word_boundary(remaining_text, max_length)
            if part:
                parts.append(part)
            else:
                # Fallback: Hard split
                parts.append(remaining_text[:max_length])
                remaining_text = remaining_text[max_length:].lstrip()
        return parts


def normalize_phone_number(phone_number: str) -> str:
    """
    Normalizes a phone number for the router.
    
    Converts:
    - +49... → 0049... (router has issues with +)
    - +43... → 0043... (Austria)
    - +41... → 0041... (Switzerland)
    - +1... → 001... (USA/Canada)
    - Other countries: +XX... → 00XX...
    
    Args:
        phone_number: Phone number in any format
    
    Returns:
        Normalized phone number (only + converted to 00)
    """
    if not phone_number:
        return phone_number
    
    # Remove spaces, dashes and other formatting characters
    normalized = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("/", "").replace(".", "")
    
    # Convert +XX to 00XX (for all countries)
    if normalized.startswith("+"):
        # Find country code (1-3 digits after +)
        import re
        match = re.match(r'^\+(\d{1,3})(.*)$', normalized)
        if match:
            country_code = match.group(1)
            rest = match.group(2)
            normalized = "00" + country_code + rest
        else:
            # If no match, remove the +
            normalized = normalized[1:]
    
    return normalized


class TRB245SMS:
    """Class for sending SMS via Teltonika router"""
    
    def __init__(self, router_url: str, username: str, password: str):
        """
        Initializes the SMS class
        
        Args:
            router_url: Router URL (e.g. "http://rt-sms-01.opus.local")
            username: Username for authentication
            password: Password for authentication
        """
        self.router_url = router_url.rstrip('/')
        self.username = username
        self.password = password
        self.token = None
        self.token_expires_at = None
        self.session = requests.Session()
        # Token cache file based on router URL
        cache_name = router_url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')
        self.token_cache_file = Path.home() / f".trb245_token_{cache_name}.json"
    
    def load_token_from_cache(self) -> bool:
        """
        Loads token from cache if it is still valid
        
        Returns:
            True if valid token was loaded, False otherwise
        """
        if not self.token_cache_file.exists():
            return False
        
        try:
            with open(self.token_cache_file, 'r') as f:
                cache_data = json.load(f)
            
            token = cache_data.get("token")
            expires_at = cache_data.get("expires_at")
            
            if not token or not expires_at:
                return False
            
            # Check if token is still valid (with 10 second buffer)
            current_time = time.time()
            if current_time < expires_at - 10:
                self.token = token
                self.token_expires_at = expires_at
                # Set token in session header
                self.session.headers.update({
                    "Authorization": f"Bearer {self.token}"
                })
                # Set cookie
                from urllib.parse import urlparse
                parsed_url = urlparse(self.router_url)
                domain = parsed_url.netloc.split(':')[0]
                from requests.cookies import create_cookie
                cookie = create_cookie(
                    name="sysauth",
                    value=self.token,
                    domain=domain
                )
                self.session.cookies.set_cookie(cookie)
                remaining = int(expires_at - current_time)
                print(f"✓ Using valid token from cache (valid for {remaining}s)")
                return True
            else:
                # Token expired, delete cache
                self.token_cache_file.unlink()
                return False
        except (json.JSONDecodeError, IOError, KeyError):
            return False
    
    def save_token_to_cache(self, token: str, expires_seconds: int):
        """
        Saves token to cache with expiration time
        
        Args:
            token: The token
            expires_seconds: Validity duration in seconds
        """
        try:
            expires_at = time.time() + expires_seconds
            cache_data = {
                "token": token,
                "expires_at": expires_at,
                "expires_seconds": expires_seconds,
                "cached_at": time.time()
            }
            with open(self.token_cache_file, 'w') as f:
                json.dump(cache_data, f)
            # Set file permissions to 600 (readable/writable by user only)
            os.chmod(self.token_cache_file, 0o600)
        except IOError:
            pass  # Ignore save errors
    
    def is_token_valid(self) -> bool:
        """
        Checks if a valid token is present
        
        Returns:
            True if token is present and valid, False otherwise
        """
        if not self.token:
            return False
        
        if self.token_expires_at:
            return time.time() < self.token_expires_at - 10  # 10 second buffer
        else:
            # If no expiration time stored, try loading from cache
            return self.load_token_from_cache()
    
    def authenticate(self, force: bool = False) -> bool:
        """
        Authenticates with router and obtains a token
        Uses REST API: POST /api/login
        Uses valid token from cache if available
        
        Args:
            force: If True, gets a new token even if a valid one exists
        
        Returns:
            True if successful, False otherwise
        """
        # First check if a valid token is in cache
        if not force:
            if self.load_token_from_cache():
                return True
        
        # Ensure we use HTTPS
        if not self.router_url.startswith('http'):
            self.router_url = f"https://{self.router_url}"
        elif self.router_url.startswith('http://'):
            # Convert HTTP to HTTPS
            self.router_url = self.router_url.replace('http://', 'https://')
        
        login_url = f"{self.router_url}/api/login"
        
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            # Disable SSL certificate verification (if self-signed)
            response = self.session.post(
                login_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
                verify=False  # Disable SSL verification for local routers
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Token extraction: Response has structure {"success": true, "data": {"token": "...", "expires": 299}}
            expires_seconds = 299  # Default expiration
            if "data" in data and isinstance(data["data"], dict):
                if "token" in data["data"]:
                    self.token = data["data"]["token"]
                    expires_seconds = data["data"].get("expires", 299)
            elif "token" in data:
                self.token = data["token"]
                expires_seconds = data.get("expires", 299)
            elif "result" in data:
                self.token = data["result"]
            elif "sysauth" in response.cookies:
                self.token = response.cookies["sysauth"]
            else:
                # Check all cookies
                for cookie in response.cookies:
                    if "auth" in cookie.name.lower() or "token" in cookie.name.lower():
                        self.token = cookie.value
                        break
            
            if self.token:
                # Calculate expiration time
                self.token_expires_at = time.time() + expires_seconds
                
                # Set token in Authorization header (main method for REST API)
                self.session.headers.update({
                    "Authorization": f"Bearer {self.token}"
                })
                # Also set token as cookie (if needed)
                # Extract domain from URL
                from urllib.parse import urlparse
                parsed_url = urlparse(self.router_url)
                domain = parsed_url.netloc.split(':')[0]  # Remove port if present
                # Create cookie object
                from requests.cookies import create_cookie
                cookie = create_cookie(
                    name="sysauth",
                    value=self.token,
                    domain=domain
                )
                self.session.cookies.set_cookie(cookie)
                
                # Save token to cache
                self.save_token_to_cache(self.token, expires_seconds)
                
                print(f"✓ Authentication successful (token valid for {expires_seconds}s)")
                return True
            else:
                print(f"✗ Authentication failed: No token in response")
                print(f"  Response: {data}")
                return False
                
        except requests.exceptions.SSLError as e:
            print(f"✗ SSL error: {e}")
            print(f"  Trying with SSL verification disabled...")
            # Already tried with verify=False, so it's a different problem
            return False
        except requests.exceptions.RequestException as e:
            print(f"✗ Authentication error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Response status: {e.response.status_code}")
                try:
                    print(f"  Response: {e.response.json()}")
                except:
                    print(f"  Response text: {e.response.text[:200]}")
            return False
        except (json.JSONDecodeError, ValueError) as e:
            print(f"✗ Error: Response is not valid JSON: {e}")
            return False
        
        return False
    
    def get_modems(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves list of available modems via /api/modems/status
        
        Returns:
            Dictionary with modem information or None on error
        """
        # Check if token is present and valid
        if not self.is_token_valid():
            if not self.authenticate():
                return None
        
        # Ensure we use HTTPS
        if not self.router_url.startswith('https'):
            if self.router_url.startswith('http://'):
                self.router_url = self.router_url.replace('http://', 'https://')
            else:
                self.router_url = f"https://{self.router_url}"
        
        modems_url = f"{self.router_url}/api/modems/status"
        
        try:
            response = self.session.get(
                modems_url,
                headers={"Content-Type": "application/json"},
                timeout=10,
                verify=False
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"✗ Error retrieving modems: {e}")
            return None
    
    def send_sms(
        self, 
        phone_number: str, 
        message: str, 
        modem: Optional[str] = "1-1.4",
        split_long_messages: bool = True,
        max_sms_length: int = 160
    ) -> Dict[str, Any]:
        """
        Sends an SMS message. Automatically splits long messages into multiple SMS.
        
        Args:
            phone_number: Recipient phone number (e.g. "+491234567890" or "01511234567")
            message: Message to send
            modem: Modem ID (default: "1-1.4" for Primary)
            split_long_messages: If True, messages > 160 characters are automatically split
            max_sms_length: Maximum length per SMS (default: 160 characters)
        
        Returns:
            Dictionary with router response
        """
        # Normalize phone number (converts +49 to 0049, etc.)
        phone_number = normalize_phone_number(phone_number)
        
        # Check if token is present and valid
        if not self.is_token_valid():
            if not self.authenticate():
                return {"success": False, "error": "Authentication failed"}
        
        # Split long messages if desired
        if split_long_messages and len(message) > max_sms_length:
            # Split message with numbering (e.g. "1/3: ", "2/3: ", "3/3: ")
            message_parts = split_sms_message(message, max_sms_length, add_numbering=True)
            total_parts = len(message_parts)
            print(f"ℹ Message is {len(message)} characters long and will be split into {total_parts} SMS")
            print(f"  Each SMS contains numbering (e.g. '1/{total_parts}: ', '2/{total_parts}: ', etc.)")
            
            # Send all parts
            all_results = []
            total_sms_used = 0
            all_successful = True
            
            for i, part in enumerate(message_parts, 1):
                print(f"  Sending part {i}/{total_parts} ({len(part)} characters, starts with '{part[:10]}...')")
                result = self._send_single_sms(phone_number, part, modem)
                all_results.append(result)
                
                if result.get("success"):
                    sms_used = result.get("data", {}).get("sms_used", 0)
                    total_sms_used += sms_used
                else:
                    all_successful = False
                    errors = result.get("errors", [])
                    error_msg = "; ".join([e.get("error", "Unknown error") for e in errors])
                    print(f"  ✗ Part {i}/{total_parts} failed: {error_msg}")
                    # Abort on error
                    return {
                        "success": False,
                        "error": f"Error sending part {i}/{total_parts}: {error_msg}",
                        "parts_sent": i - 1,
                        "total_parts": total_parts
                    }
            
            print(f"✓ All {total_parts} SMS parts sent successfully! (Total: {total_sms_used} SMS)")
            return {
                "success": True,
                "data": {
                    "sms_used": total_sms_used,
                    "parts": total_parts,
                    "message_length": len(message)
                },
                "parts": all_results
            }
        else:
            # SMS sending (splitting not required or disabled)
            return self._send_single_sms(phone_number, message, modem)
    
    def _send_single_sms(
        self,
        phone_number: str,
        message: str,
        modem: str
    ) -> Dict[str, Any]:
        """
        Sends a single SMS message (internal method).
        
        Args:
            phone_number: Normalized phone number
            message: Message to send
            modem: Modem ID
        
        Returns:
            Dictionary with router response
        """
        # Endpoint for SMS sending (REST API)
        # Ensure we use HTTPS
        if not self.router_url.startswith('https'):
            if self.router_url.startswith('http://'):
                self.router_url = self.router_url.replace('http://', 'https://')
            else:
                self.router_url = f"https://{self.router_url}"
        
        send_url = f"{self.router_url}/api/messages/actions/send"
        
        # Modem is required - use "1-1.4" as default (Primary)
        if not modem:
            modem = "1-1.4"
        
        payload = {
            "data": {
                "number": phone_number,
                "message": message,
                "modem": modem
            }
        }
        
        try:
            response = self.session.post(
                send_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
                verify=False  # Disable SSL verification
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("success"):
                sms_used = result.get("data", {}).get("sms_used", "unknown")
                # Only output for single SMS (multi-part is output above)
                if len(message) <= 160:
                    print(f"✓ SMS sent successfully! (SMS used: {sms_used})")
            else:
                errors = result.get("errors", [])
                error_msg = "; ".join([e.get("error", "Unknown error") for e in errors])
                print(f"✗ SMS sending failed: {error_msg}")
                
                # If modem error, show available modems
                modem_error = any(e.get("source") == "modem" for e in errors)
                if modem_error:
                    print(f"\n  Attempting to retrieve available modems...")
                    modems = self.get_modems()
                    if modems and modems.get("success") and "data" in modems:
                        print(f"  Available modems:")
                        for modem in modems["data"]:
                            modem_id = modem.get("id", "unknown")
                            modem_name = modem.get("name", "Unnamed")
                            primary = " (Primary)" if modem.get("primary") else ""
                            state = modem.get("state", "unknown")
                            operator = modem.get("operator", "")
                            print(f"    - ID: {modem_id} | Name: {modem_name}{primary} | Status: {state} | Operator: {operator}")
                    else:
                        print(f"  Could not retrieve modem list. Please check router configuration.")
            
            return result
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Error sending SMS: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"  Response: {error_data}")
                except:
                    print(f"  Response text: {e.response.text[:200]}")
            return {"success": False, "error": str(e)}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Loads configuration from config.yaml
    
    Args:
        config_path: Path to config file (default: config.yaml in current directory)
    
    Returns:
        Dictionary with configuration values
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config or {}
    except (yaml.YAMLError, IOError) as e:
        print(f"⚠ Warning: Could not load config.yaml: {e}")
        return {}


def main():
    """Main function for command-line usage"""
    # Load configuration from config.yaml
    config = load_config()
    router_config = config.get("router", {})
    
    # Default values from config or environment variables
    default_router = router_config.get("url") or os.getenv("TRB245_ROUTER")
    default_user = router_config.get("username") or os.getenv("TRB245_USER")
    default_password = router_config.get("password") or os.getenv("TRB245_PASSWORD")
    
    # Check if config file exists
    config_file = Path(__file__).parent / "config.yaml"
    if not config_file.exists():
        example_file = Path(__file__).parent / "config.yaml.example"
        if example_file.exists():
            print("⚠ Warning: config.yaml not found!")
            print(f"  Please copy {example_file.name} to config.yaml and adjust the values.")
            print("  Or use --router, --user and --password as command-line arguments.")
            print()
    
    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Send SMS via Teltonika router",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration:
  The script reads configuration from config.yaml (copy config.yaml.example to config.yaml).
  Alternatively, you can use environment variables or command-line arguments.
  
  Priority: Command line > Environment variables > config.yaml

Examples:
  python send_sms.py +491234567890 "Hello World!"
  python send_sms.py +491234567890 "Hello" --router https://192.168.1.1 --user admin --password mypassword
  python send_sms.py +491234567890 "Hello" --modem "1-1.4"
  python send_sms.py --list-modems

Environment variables:
  TRB245_ROUTER    - Router URL
  TRB245_USER      - Username
  TRB245_PASSWORD  - Password
        """
    )
    
    parser.add_argument("phone_number", nargs='?', help="Recipient phone number (e.g. +491234567890) - required, except with --list-modems")
    parser.add_argument("message", nargs='?', help="SMS message to send - required, except with --list-modems")
    parser.add_argument("--modem", 
                       default=None,
                       help="Modem ID (default: '1-1.4' for Primary)")
    parser.add_argument("--list-modems", 
                       action="store_true",
                       help="List available modems and exit")
    parser.add_argument("--router", 
                       default=default_router,
                       help="Router URL (default: from config.yaml, environment variable TRB245_ROUTER or command line)")
    parser.add_argument("--user", 
                       default=default_user,
                       help="Username (default: from config.yaml, environment variable TRB245_USER or command line)")
    parser.add_argument("--password", 
                       default=default_password,
                       help="Password (default: from config.yaml, environment variable TRB245_PASSWORD or command line)")
    parser.add_argument("--config",
                       default=None,
                       help="Path to config.yaml file (default: config.yaml in current directory)")
    
    args = parser.parse_args()
    
    # Reload config if --config was specified
    if args.config:
        config = load_config(args.config)
        router_config = config.get("router", {})
        # Override only if not specified as argument
        if not args.router:
            args.router = router_config.get("url") or os.getenv("TRB245_ROUTER")
        if not args.user:
            args.user = router_config.get("username") or os.getenv("TRB245_USER")
        if not args.password:
            args.password = router_config.get("password") or os.getenv("TRB245_PASSWORD")
    
    # Check if all required values are present
    if not args.router:
        print("✗ Error: Router URL missing!")
        print("  Please specify --router, set TRB245_ROUTER or create config.yaml")
        sys.exit(1)
    if not args.user:
        print("✗ Error: Username missing!")
        print("  Please specify --user, set TRB245_USER or create config.yaml")
        sys.exit(1)
    if not args.password:
        print("✗ Error: Password missing!")
        print("  Please specify --password, set TRB245_PASSWORD or create config.yaml")
        sys.exit(1)
    
    # Initialize SMS class
    sms = TRB245SMS(args.router, args.user, args.password)
    
    # Authenticate
    if not sms.authenticate():
        print("✗ Authentication failed. Please check credentials.")
        sys.exit(1)
    
    # List modems if requested
    if args.list_modems:
        print("Available modems:")
        print("-" * 80)
        modems = sms.get_modems()
        if modems and modems.get("success") and "data" in modems:
            for modem in modems["data"]:
                modem_id = modem.get("id", "unknown")
                modem_name = modem.get("name", "Unnamed")
                primary = " (Primary)" if modem.get("primary") else ""
                state = modem.get("state", "unknown")
                operator = modem.get("operator", "")
                model = modem.get("model", "")
                print(f"  ID: {modem_id}")
                print(f"    Name: {modem_name}{primary}")
                print(f"    Status: {state}")
                print(f"    Operator: {operator}")
                if model:
                    print(f"    Model: {model}")
                print()
        else:
            print("  ✗ Could not retrieve modem list.")
        sys.exit(0)
    
    # Check if phone_number and message are specified
    if not args.phone_number or not args.message:
        parser.error("phone_number and message are required (or use --list-modems)")
    
    # Set modem if not specified - try to find primary modem
    if not args.modem:
        modems = sms.get_modems()
        if modems and modems.get("success") and "data" in modems:
            # Search for primary modem
            for modem_info in modems["data"]:
                if modem_info.get("primary"):
                    args.modem = modem_info.get("id", "1-1.4")
                    print(f"ℹ Using primary modem: {args.modem}")
                    break
            # If no primary found, use first modem
            if not args.modem and modems["data"]:
                args.modem = modems["data"][0].get("id", "1-1.4")
                print(f"ℹ Using modem: {args.modem}")
        else:
            # Fallback to default
            args.modem = "1-1.4"
    
    modem = args.modem
    
    # Send SMS
    result = sms.send_sms(args.phone_number, args.message, modem)
    
    # Exit code based on success
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
