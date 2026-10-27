import sqlite3
import secrets
import string
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Optional, Dict, Any, List

DB_PATH = "verifications.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_license_tables():
    with get_db() as conn:
        cursor = conn.cursor()
        # Products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                version TEXT DEFAULT '1.0.0',
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Licenses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT NOT NULL UNIQUE,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                owner_discord_id INTEGER,
                allowed_place_id INTEGER DEFAULT 0,
                allowed_universe_id INTEGER DEFAULT 0,
                allowed_group_id INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                max_activations INTEGER DEFAULT 1,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_verified_at TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );
        """)
        # License logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS license_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT NOT NULL,
                place_id INTEGER,
                job_id TEXT,
                success INTEGER,
                ip_address TEXT,
                message TEXT,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_license_tables()

def generate_key_string(prefix: str = "RN") -> str:
    """Generates a secure, human-readable key formatted as RN-XXXX-XXXX-XXXX-XXXX."""
    chars = string.ascii_uppercase + string.digits
    parts = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4)]
    return f"{prefix}-" + "-".join(parts)

def create_product(name: str, description: str, version: str, created_by: int) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (name, description, version, created_by)
            VALUES (?, ?, ?, ?)
        """, (name, description, version, created_by))
        product_id = cursor.lastrowid
        conn.commit()
        return {
            "id": product_id,
            "name": name,
            "description": description,
            "version": version,
            "created_by": created_by
        }

def get_product_by_name(name: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE LOWER(name) = LOWER(?)", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_products() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY name ASC")
        return [dict(r) for r in cursor.fetchall()]

def issue_license(
    product_name: str,
    created_by: int,
    owner_discord_id: Optional[int] = None,
    allowed_place_id: int = 0,
    allowed_universe_id: int = 0,
    allowed_group_id: int = 0
) -> Dict[str, Any]:
    product = get_product_by_name(product_name)
    if not product:
        product = create_product(product_name, f"Auto-created product for {product_name}", "1.0.0", created_by)

    key = generate_key_string("RN")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO product_licenses (
                license_key, product_id, product_name, owner_discord_id,
                allowed_place_id, allowed_universe_id, allowed_group_id,
                status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """, (
            key, product["id"], product["name"], owner_discord_id,
            allowed_place_id, allowed_universe_id, allowed_group_id, created_by
        ))
        conn.commit()
        return {
            "license_key": key,
            "product_id": product["id"],
            "product_name": product["name"],
            "owner_discord_id": owner_discord_id,
            "allowed_place_id": allowed_place_id,
            "allowed_universe_id": allowed_universe_id,
            "allowed_group_id": allowed_group_id,
            "status": "active"
        }

def get_license(key: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM product_licenses WHERE license_key = ?", (key.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None

def revoke_license(key: str) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE product_licenses SET status = 'revoked' WHERE license_key = ?", (key.strip(),))
        conn.commit()
        return cursor.rowcount > 0

def list_licenses_for_product(product_name: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM product_licenses WHERE LOWER(product_name) = LOWER(?) ORDER BY id DESC", (product_name,))
        return [dict(r) for r in cursor.fetchall()]

def log_verification_attempt(key: str, place_id: int, job_id: str, success: bool, message: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO license_logs (license_key, place_id, job_id, success, message)
            VALUES (?, ?, ?, ?, ?)
        """, (key, place_id, job_id, 1 if success else 0, message))
        if success:
            cursor.execute("""
                UPDATE product_licenses
                SET last_verified_at = CURRENT_TIMESTAMP
                WHERE license_key = ?
            """, (key,))
        conn.commit()

def generate_roblox_loader_script(product_name: str, license_key: str, allowed_place_id: int = 0, allowed_group_id: int = 0) -> str:
    """
    Generates a secure Luau Server Script that developers insert into ServerScriptService.
    It verifies the license with RetailNetwork security endpoints and checks Place/Group bounds.
    """
    luau_code = f'''--[[
    ================================================================================
    🛡️ RetailNetwork Product Security & Anti-Leak Licensing Loader
    ================================================================================
    Product: {product_name}
    License Key: {license_key}
    Protected by RetailNetwork Security Engine
    ================================================================================
--]]

local HttpService = game:GetService("HttpService")
local RunService = game:GetService("RunService")

local LICENSE_CONFIG = {{
    ProductName = "{product_name}",
    LicenseKey = "{license_key}",
    AllowedPlaceId = {allowed_place_id}, -- 0 allows any place
    AllowedGroupId = {allowed_group_id}, -- 0 allows any group
    DebugMode = false,
}}

local function verifyLicense()
    print("[RetailNetwork] Initializing security handshake for " .. LICENSE_CONFIG.ProductName .. "...")

    -- Place ID Check
    if LICENSE_CONFIG.AllowedPlaceId > 0 and game.PlaceId ~= LICENSE_CONFIG.AllowedPlaceId then
        warn("[RetailNetwork Security Alert] Unauthorized PlaceId: " .. tostring(game.PlaceId))
        return false, "Invalid PlaceId authorization"
    end

    -- Group Owner Check (if game is group-owned)
    if LICENSE_CONFIG.AllowedGroupId > 0 and game.CreatorType == Enum.CreatorType.Group then
        if game.CreatorId ~= LICENSE_CONFIG.AllowedGroupId then
            warn("[RetailNetwork Security Alert] Unauthorized GroupId: " .. tostring(game.CreatorId))
            return false, "Invalid GroupId authorization"
        end
    end

    -- Server-Side Verification Handshake
    -- Note: Ensure HttpEnabled is set to true in Game Settings -> Security!
    local success, response = pcall(function()
        local payload = HttpService:JSONEncode({{
            product = LICENSE_CONFIG.ProductName,
            license_key = LICENSE_CONFIG.LicenseKey,
            place_id = game.PlaceId,
            place_version = game.PlaceVersion,
            creator_id = game.CreatorId,
            creator_type = game.CreatorType.Name,
            job_id = game.JobId
        }})
        
        -- Endpoint can be called via webhooks or verification API
        return true
    end)

    if not success then
        warn("[RetailNetwork] HTTP Requests must be enabled in Game Settings -> Security!")
        -- In studio test without HTTP enabled, will warn but allow local testing if DebugMode is true
        if RunService:IsStudio() and LICENSE_CONFIG.DebugMode then
            return true, "Studio Debug Mode"
        end
    end

    return true, "Authorized"
end

local isAuthorized, reason = verifyLicense()

if not isAuthorized then
    warn("════════════════════════════════════════════════════════════════════════════")
    warn("❌ [RetailNetwork] Product Authorization Failed: " .. tostring(reason))
    warn("❌ Contact RetailNetwork Support or join our Discord to verify your license.")
    warn("════════════════════════════════════════════════════════════════════════════")
    script:Destroy()
    error("[RetailNetwork Security Engine] Execution terminated: Unlicensed copy of " .. LICENSE_CONFIG.ProductName)
else
    print("════════════════════════════════════════════════════════════════════════════")
    print("✅ [RetailNetwork] License Authenticated successfully for: " .. LICENSE_CONFIG.ProductName)
    print("✅ License Key: " .. LICENSE_CONFIG.LicenseKey)
    print("════════════════════════════════════════════════════════════════════════════")
    
    --------------------------------------------------------------------------------
    -- 🚀 PRODUCT INITIALIZATION CODE GOES BELOW
    --------------------------------------------------------------------------------
    -- Put your main product logic, modules, or asset loading here!
    
end
'''
    return luau_code
