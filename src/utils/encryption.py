"""
Encryption utilities for securing sensitive data in the database
"""
import os
import base64
import hashlib
import logging
import time

# Try to import cryptography modules, fallback to simpler encryption if not available
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    logging.warning("Cryptography package not found. Using basic encryption fallback.")
    CRYPTOGRAPHY_AVAILABLE = False

# Environment-based key or fallback to secure random key
ENCRYPTION_KEY = os.environ.get('AI_CBT_ENCRYPTION_KEY', None)

# File to store encryption key if not provided in environment
KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'secrets', 'encryption.key')

def get_or_create_key():
    """Get encryption key from environment, file, or create a new one"""
    if ENCRYPTION_KEY:
        # Use environment key
        key = ENCRYPTION_KEY.encode()
    else:
        # Try to read from key file
        try:
            if os.path.exists(KEY_FILE):
                with open(KEY_FILE, 'rb') as f:
                    key = f.read().strip()
            else:
                # Create new key
                os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
                if CRYPTOGRAPHY_AVAILABLE:
                    key = Fernet.generate_key()
                else:
                    # Simple key generation fallback
                    random_bytes = os.urandom(32)
                    key = base64.urlsafe_b64encode(random_bytes)
                
                with open(KEY_FILE, 'wb') as f:
                    f.write(key)
                # Secure the key file
                try:
                    os.chmod(KEY_FILE, 0o600)  # Read/write for owner only
                except Exception:
                    pass  # Skip if not on Unix
        except Exception as e:
            # If file operations fail, use a derived key for this session
            salt = b'AI-CBT-Theory-Salt'
            import socket
            try:
                hostname = socket.gethostname()
            except:
                hostname = 'unknown'
                
            password = f"ai-cbt-{os.getpid()}-{hostname}".encode()
            
            if CRYPTOGRAPHY_AVAILABLE:
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                key = base64.urlsafe_b64encode(kdf.derive(password))
            else:
                # Simple key derivation fallback
                derived = b''
                for i in range(10):  # Multiple rounds of hashing
                    h = hashlib.sha256()
                    h.update(password + salt + str(i).encode())
                    derived += h.digest()
                key = base64.urlsafe_b64encode(derived[:32])
    
    # Check if key is valid for Fernet (if we're using Fernet)
    if CRYPTOGRAPHY_AVAILABLE and not (len(key) == 44 and key[-2:] == b'=='):
        # Convert to Fernet-compatible format if needed
        key_hash = hashlib.sha256(key).digest()
        key = base64.urlsafe_b64encode(key_hash)
    
    return key

# Initialize encryption system
if CRYPTOGRAPHY_AVAILABLE:
    try:
        _key = get_or_create_key()
        cipher = Fernet(_key)
        logging.info("Initialized Fernet encryption")
    except Exception as e:
        logging.error(f"Failed to initialize Fernet encryption: {e}")
        CRYPTOGRAPHY_AVAILABLE = False

# Fallback encryption if cryptography module is not available
if not CRYPTOGRAPHY_AVAILABLE:
    logging.warning("Using simplified encryption - install cryptography package for better security")
    
    class SimpleCipher:
        """Simple XOR-based cipher with a rotating key for basic protection"""
        def __init__(self):
            self.key = get_or_create_key()
            if isinstance(self.key, str):
                self.key = self.key.encode()
            
            # Expand key for XOR operations
            key_hash = hashlib.sha512(self.key).digest()
            self.expanded_key = key_hash * 8  # 512 bytes of key material
            
        def _xor_bytes(self, data, key):
            """XOR data with key bytes"""
            key_len = len(key)
            return bytes(data[i] ^ key[i % key_len] for i in range(len(data)))
            
        def encrypt(self, data):
            """Basic encryption - not cryptographically strong"""
            if isinstance(data, str):
                data = data.encode('utf-8')
                
            # Add a random salt and timestamp for uniqueness
            salt = os.urandom(16)
            timestamp = str(int(time.time())).encode()
            
            # Add length prefix to help with decryption
            length = len(data).to_bytes(4, byteorder='big')
            
            # Combine components
            to_encrypt = length + data
            
            # XOR with expanded key
            encrypted = self._xor_bytes(to_encrypt, self.expanded_key)
            
            # Combine salt and encrypted data
            result = b'SIMPLE:' + salt + timestamp + encrypted
            
            # Return base64 encoded result
            return base64.b64encode(result)
            
        def decrypt(self, data):
            """Basic decryption - not cryptographically strong"""
            try:
                # Handle unencrypted data
                if isinstance(data, str):
                    if not data.startswith('SIMPLE:') and not data.startswith('U0lNUExFOg=='):
                        return data
                    data = data.encode('utf-8')
                    
                # Decode base64
                decoded = base64.b64decode(data)
                
                if decoded.startswith(b'SIMPLE:'):
                    # Extract components
                    prefix_len = len(b'SIMPLE:')
                    salt_len = 16
                    timestamp_len = 10  # Unix timestamp
                    
                    # Skip prefix, salt, and timestamp
                    encrypted = decoded[prefix_len + salt_len + timestamp_len:]
                    
                    # XOR with expanded key
                    decrypted = self._xor_bytes(encrypted, self.expanded_key)
                    
                    # Extract original data using length prefix
                    length = int.from_bytes(decrypted[:4], byteorder='big')
                    result = decrypted[4:4+length]
                    
                    return result
                else:
                    # Not our format, return as is
                    return data
            except Exception as e:
                logging.error(f"Decryption error: {e}")
                # Return original if decryption fails
                return data
    
    cipher = SimpleCipher()

def encrypt_text(text):
    """Encrypt text data"""
    if text is None:
        return None
    
    if isinstance(text, str):
        text = text.encode('utf-8')
    
    return cipher.encrypt(text).decode('utf-8')

def decrypt_text(encrypted_text):
    """Decrypt text data"""
    if encrypted_text is None or not encrypted_text:
        return None
        
    if isinstance(encrypted_text, str):
        encrypted_text = encrypted_text.encode('utf-8')
    
    try:
        decrypted = cipher.decrypt(encrypted_text)
        return decrypted.decode('utf-8')
    except Exception:
        # If decryption fails, return the data as is (might be unencrypted legacy data)
        try:
            return encrypted_text.decode('utf-8')
        except:
            return str(encrypted_text)

# Context processors for SQLAlchemy
def encrypt_dict_values(data_dict, sensitive_fields):
    """Encrypt sensitive fields in a dictionary"""
    if not data_dict:
        return data_dict
        
    encrypted = data_dict.copy()
    
    for field in sensitive_fields:
        if field in encrypted and encrypted[field]:
            encrypted[field] = encrypt_text(encrypted[field])
    
    return encrypted

def decrypt_dict_values(data_dict, sensitive_fields):
    """Decrypt sensitive fields in a dictionary"""
    if not data_dict:
        return data_dict
        
    decrypted = data_dict.copy()
    
    for field in sensitive_fields:
        if field in decrypted and decrypted[field]:
            decrypted[field] = decrypt_text(decrypted[field])
    
    return decrypted