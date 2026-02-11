"""
Simplified Credential Vault for Noctem MVP.

Storage backends (in order of preference):
1. Environment variables (most secure for servers)
2. Encrypted JSON file (requires master password)
3. Plain JSON file (development only - warns on use)

For production, use environment variables:
    export NOCTEM_EMAIL_USER="your@email.com"
    export NOCTEM_EMAIL_PASSWORD="app-password-here"
    export NOCTEM_EMAIL_SMTP_SERVER="smtp.gmail.com"
"""

import json
import os
import base64
import warnings
from pathlib import Path
from typing import Optional, Dict, Any

# Try to import cryptography for encrypted storage
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
VAULT_FILE = DATA_DIR / ".vault.json"
VAULT_ENCRYPTED = DATA_DIR / ".vault.enc"
VAULT_SALT = DATA_DIR / ".vault.salt"

# Environment variable prefix
ENV_PREFIX = "NOCTEM_"

# Credential keys we support
VALID_KEYS = [
    "email_user",
    "email_password", 
    "email_smtp_server",
    "email_smtp_port",
    "email_imap_server",
    "email_imap_port",
    "email_recipient",      # Default recipient for reports (your personal email)
    "email_from_name",      # Display name for sent emails
    "email_provider",       # Provider name (fastmail, gmail, etc.)
]


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive encryption key from password."""
    if not HAS_CRYPTO:
        raise RuntimeError("cryptography package required for encrypted storage")
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


class Vault:
    """Simple credential storage with multiple backends."""
    
    def __init__(self, master_password: Optional[str] = None):
        """
        Initialize vault.
        
        Args:
            master_password: Required for encrypted file storage.
                            Not needed if using env vars or plain file.
        """
        self.master_password = master_password
        self._cache: Dict[str, str] = {}
        self._backend = self._detect_backend()
        
        if self._backend == "encrypted":
            self._load_encrypted()
        elif self._backend == "plaintext":
            self._load_plaintext()
    
    def _detect_backend(self) -> str:
        """Detect which storage backend to use."""
        # Check if any env vars are set
        for key in VALID_KEYS:
            if os.environ.get(f"{ENV_PREFIX}{key.upper()}"):
                return "env"
        
        # Check for encrypted file
        if VAULT_ENCRYPTED.exists() and VAULT_SALT.exists():
            if self.master_password:
                return "encrypted"
            else:
                warnings.warn(
                    "Encrypted vault exists but no master password provided. "
                    "Pass master_password to Vault() or use env vars."
                )
        
        # Check for plain file (dev only)
        if VAULT_FILE.exists():
            warnings.warn(
                "Using PLAIN TEXT credential storage! "
                "This is insecure. For production, use environment variables."
            )
            return "plaintext"
        
        # Default to env (will return None for missing keys)
        return "env"
    
    def _load_encrypted(self):
        """Load credentials from encrypted file."""
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography package required")
        
        salt = VAULT_SALT.read_bytes()
        key = _derive_key(self.master_password, salt)
        fernet = Fernet(key)
        
        try:
            encrypted = VAULT_ENCRYPTED.read_bytes()
            decrypted = fernet.decrypt(encrypted)
            self._cache = json.loads(decrypted.decode())
        except Exception as e:
            raise RuntimeError(f"Failed to decrypt vault: {e}")
    
    def _save_encrypted(self):
        """Save credentials to encrypted file."""
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography package required")
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Generate salt if needed
        if not VAULT_SALT.exists():
            salt = os.urandom(16)
            VAULT_SALT.write_bytes(salt)
        else:
            salt = VAULT_SALT.read_bytes()
        
        key = _derive_key(self.master_password, salt)
        fernet = Fernet(key)
        
        encrypted = fernet.encrypt(json.dumps(self._cache).encode())
        VAULT_ENCRYPTED.write_bytes(encrypted)
    
    def _load_plaintext(self):
        """Load credentials from plain JSON file."""
        try:
            self._cache = json.loads(VAULT_FILE.read_text())
        except Exception:
            self._cache = {}
    
    def _save_plaintext(self):
        """Save credentials to plain JSON file (dev only)."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        VAULT_FILE.write_text(json.dumps(self._cache, indent=2))
    
    def get(self, key: str) -> Optional[str]:
        """Get a credential by key."""
        if key not in VALID_KEYS:
            raise ValueError(f"Invalid key: {key}. Valid keys: {VALID_KEYS}")
        
        # Try environment variable first
        env_val = os.environ.get(f"{ENV_PREFIX}{key.upper()}")
        if env_val:
            return env_val
        
        # Fall back to cache (file-based)
        return self._cache.get(key)
    
    def set(self, key: str, value: str):
        """Set a credential."""
        if key not in VALID_KEYS:
            raise ValueError(f"Invalid key: {key}. Valid keys: {VALID_KEYS}")
        
        self._cache[key] = value
        
        # Save based on backend
        if self._backend == "encrypted":
            self._save_encrypted()
        elif self._backend == "plaintext":
            self._save_plaintext()
        elif self._backend == "env":
            # Switch to plaintext for now (with warning)
            warnings.warn(
                "Saving to PLAIN TEXT file. For production, use environment variables."
            )
            self._backend = "plaintext"
            self._save_plaintext()
    
    def delete(self, key: str):
        """Delete a credential."""
        self._cache.pop(key, None)
        
        if self._backend == "encrypted":
            self._save_encrypted()
        elif self._backend == "plaintext":
            self._save_plaintext()
    
    def has(self, key: str) -> bool:
        """Check if a credential exists."""
        return self.get(key) is not None
    
    def get_backend(self) -> str:
        """Get the current storage backend name."""
        return self._backend
    
    def status(self) -> Dict[str, Any]:
        """Get vault status (without revealing secrets)."""
        configured_keys = [k for k in VALID_KEYS if self.has(k)]
        return {
            "backend": self._backend,
            "configured_keys": configured_keys,
            "has_crypto": HAS_CRYPTO,
        }


# Singleton instance
_vault: Optional[Vault] = None


def init_vault(master_password: Optional[str] = None) -> Vault:
    """Initialize the global vault instance."""
    global _vault
    _vault = Vault(master_password)
    return _vault


def get_vault() -> Optional[Vault]:
    """Get the global vault instance."""
    global _vault
    if _vault is None:
        # Auto-initialize with env backend
        _vault = Vault()
    return _vault


def get_credential(key: str) -> Optional[str]:
    """Convenience function to get a credential."""
    vault = get_vault()
    return vault.get(key)


def set_credential(key: str, value: str):
    """Convenience function to set a credential."""
    vault = get_vault()
    vault.set(key, value)


def setup_email_interactive():
    """
    Interactive setup for email credentials.
    Call from CLI to configure email.
    """
    import getpass
    
    print("\n📧 Noctem Email Setup")
    print("=" * 40)
    print("\nThis will configure email for Noctem.")
    print("Recommended: Fastmail with app password.\n")
    
    # Provider selection - Fastmail first
    providers = {
        "1": ("Fastmail", "smtp.fastmail.com", "imap.fastmail.com"),
        "2": ("Gmail", "smtp.gmail.com", "imap.gmail.com"),
        "3": ("Outlook/Hotmail", "smtp.office365.com", "outlook.office365.com"),
        "4": ("Migadu", "smtp.migadu.com", "imap.migadu.com"),
        "5": ("Custom", None, None),
    }
    
    print("Select email provider:")
    for key, (name, _, _) in providers.items():
        print(f"  {key}. {name}")
    
    choice = input("\nChoice [1]: ").strip() or "1"
    provider_name, smtp, imap = providers.get(choice, providers["1"])
    
    if choice == "5":
        smtp = input("SMTP server: ").strip()
        imap = input("IMAP server: ").strip() or smtp.replace("smtp", "imap")
    
    email = input(f"\nNoctem's email address: ").strip()
    password = getpass.getpass("App password: ")
    
    print(f"\nWhere should reports be sent?")
    recipient = input(f"Your personal email [{email}]: ").strip() or email
    
    from_name = input(f"Display name [Noctem]: ").strip() or "Noctem"
    
    vault = get_vault()
    vault.set("email_user", email)
    vault.set("email_password", password)
    vault.set("email_smtp_server", smtp)
    vault.set("email_imap_server", imap)
    vault.set("email_recipient", recipient)
    vault.set("email_from_name", from_name)
    vault.set("email_provider", provider_name.lower())
    
    print(f"\n✓ Email configured for {provider_name}")
    print(f"  Noctem's email: {email}")
    print(f"  Reports sent to: {recipient}")
    print(f"  SMTP: {smtp}")
    print(f"  IMAP: {imap}")
    print(f"\n  Backend: {vault.get_backend()}")
    
    if vault.get_backend() == "plaintext":
        print("\n⚠️  Credentials stored in plain text!")
        print("    For production, set environment variables instead:")
        print(f"    export NOCTEM_EMAIL_USER='{email}'")
        print(f"    export NOCTEM_EMAIL_PASSWORD='...'")
    
    return True


if __name__ == "__main__":
    # Run interactive setup when executed directly
    setup_email_interactive()
