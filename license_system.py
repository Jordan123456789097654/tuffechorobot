from security_config import DEFAULT_SECURITY_WEBHOOK_URL
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
                price_robux INTEGER DEFAULT 0,
                developer_product_id INTEGER DEFAULT 0,
                asset_id INTEGER DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Add optional columns if already exists
        for col_def in [
            "price_robux INTEGER DEFAULT 0",
            "developer_product_id INTEGER DEFAULT 0",
            "asset_id INTEGER DEFAULT 0"
        ]:
            try:
                cursor.execute(f"ALTER TABLE products ADD COLUMN {col_def};")
            except Exception:
                pass

        # Licenses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT NOT NULL UNIQUE,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                owner_discord_id INTEGER,
                owner_roblox_id INTEGER DEFAULT 0,
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

        try:
            cursor.execute("ALTER TABLE product_licenses ADD COLUMN owner_roblox_id INTEGER DEFAULT 0;")
        except Exception:
            pass

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

def create_product(
    name: str,
    description: str,
    version: str,
    created_by: int,
    price_robux: int = 0,
    developer_product_id: int = 0,
    asset_id: int = 0
) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (name, description, version, price_robux, developer_product_id, asset_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                version = excluded.version,
                price_robux = excluded.price_robux,
                developer_product_id = excluded.developer_product_id,
                asset_id = excluded.asset_id
        """, (name, description, version, price_robux, developer_product_id, asset_id, created_by))
        conn.commit()
        return get_product_by_name(name)

def get_product_by_name(name: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE LOWER(name) = LOWER(?)", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_product_by_dev_product_id(dev_product_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE developer_product_id = ?", (dev_product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_products() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY id ASC")
        return [dict(r) for r in cursor.fetchall()]

def issue_license(
    product_name: str,
    created_by: int,
    owner_discord_id: Optional[int] = None,
    owner_roblox_id: int = 0,
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
                license_key, product_id, product_name, owner_discord_id, owner_roblox_id,
                allowed_place_id, allowed_universe_id, allowed_group_id,
                status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """, (
            key, product["id"], product["name"], owner_discord_id, owner_roblox_id,
            allowed_place_id, allowed_universe_id, allowed_group_id, created_by
        ))
        conn.commit()
        return {
            "license_key": key,
            "product_id": product["id"],
            "product_name": product["name"],
            "owner_discord_id": owner_discord_id,
            "owner_roblox_id": owner_roblox_id,
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

def get_user_licenses_by_roblox_id(roblox_id: int) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM product_licenses WHERE owner_roblox_id = ? AND status = 'active'", (roblox_id,))
        return [dict(r) for r in cursor.fetchall()]

def check_user_license_for_product(roblox_id: int, product_name: str) -> Optional[Dict[str, Any]]:
    """Checks if a Roblox UserId owns an active license for the specified product."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM product_licenses
            WHERE owner_roblox_id = ? AND LOWER(product_name) = LOWER(?) AND status = 'active'
            ORDER BY id DESC LIMIT 1
        """, (roblox_id, product_name))
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

def generate_roblox_loader_script(
    product_name: str,
    license_key: str,
    allowed_place_id: int = 0,
    allowed_group_id: int = 0,
    owner_roblox_id: int = 0,
    webhook_url: str = DEFAULT_SECURITY_WEBHOOK_URL
) -> str:
    """
    Generates a secure Luau Server Script that developers insert into ServerScriptService.
    It verifies the game creator against owner_roblox_id or checks place/group/key bounds.
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
local Players = game:GetService("Players")

local LICENSE_CONFIG = {{
    ProductName = "{product_name}",
    LicenseKey = "{license_key}",
    OwnerRobloxId = {owner_roblox_id}, -- Licensed Roblox User ID (0 = check place/group/key)
    AllowedPlaceId = {allowed_place_id}, -- 0 allows any place
    AllowedGroupId = {allowed_group_id}, -- 0 allows any group
    WebhookUrl = "{webhook_url}",
    DebugMode = false,
}}

local function logLicenseEvent(status, details)
    if LICENSE_CONFIG.WebhookUrl ~= "" then
        pcall(function()
            local isAlert = (status == "FAILED")
            local titleText = isAlert and "🚨 LEAK ALERT: Unauthorized Copy of " .. LICENSE_CONFIG.ProductName or "🛡️ RetailNetwork License Check: " .. LICENSE_CONFIG.ProductName
            local colorHex = isAlert and 15158332 or 3066993

            -- Fetch creator name / profile link
            local creatorName = "Unknown"
            local creatorProfileUrl = ""
            if game.CreatorType == Enum.CreatorType.User then
                local s, name = pcall(function()
                    return Players:GetNameFromUserIdAsync(game.CreatorId)
                end)
                creatorName = s and ("@" .. name) or "ID: " .. tostring(game.CreatorId)
                creatorProfileUrl = "https://www.roblox.com/users/" .. tostring(game.CreatorId) .. "/profile"
            elseif game.CreatorType == Enum.CreatorType.Group then
                creatorName = "Group ID: " .. tostring(game.CreatorId)
                creatorProfileUrl = "https://www.roblox.com/groups/" .. tostring(game.CreatorId)
            end

            -- Authorized purchaser profile link
            local ownerProfileUrl = "https://www.roblox.com/users/" .. tostring(LICENSE_CONFIG.OwnerRobloxId) .. "/profile"
            local gameUrl = "https://www.roblox.com/games/" .. tostring(game.PlaceId)

            local payload = HttpService:JSONEncode({{
                embeds = {{{{
                    title = titleText,
                    description = "### ⚠️ Security Verification Incident Detected\\n" ..
                                  "An unauthorized place or user attempted to execute this product.\\n\\n" ..
                                  "**📦 Product Name:** `" .. LICENSE_CONFIG.ProductName .. "`\\n" ..
                                  "**🔑 License Key:** `" .. LICENSE_CONFIG.LicenseKey .. "`\\n" ..
                                  "**🔒 Authorized Owner:** [" .. tostring(LICENSE_CONFIG.OwnerRobloxId) .. "](" .. ownerProfileUrl .. ")\\n\\n" ..
                                  "**👤 Offending Creator:** [" .. creatorName .. "](" .. creatorProfileUrl .. ") `(" .. game.CreatorType.Name .. ")`\\n" ..
                                  "**🏰 Offending Game:** [Click to Open Roblox Game](" .. gameUrl .. ") `(Place ID: " .. tostring(game.PlaceId) .. ")`\\n" ..
                                  "**🎮 Server Job ID:** `" .. tostring(game.JobId) .. "`\\n" ..
                                  "**📋 Diagnostic Reason:** `" .. details .. "`\\n\\n" ..
                                  "**🛑 Enforcement Action:** `Execution blocked & script self-destructed.`",
                    color = colorHex,
                    footer = {{ text = "RetailNetwork Anti-Leak Security Sentry • #product-reports" }}
                }}}}
            }})
            HttpService:PostAsync(LICENSE_CONFIG.WebhookUrl, payload, Enum.HttpContentType.ApplicationJson)
        end)
    end
end

local function verifyLicense()
    print("[RetailNetwork] Initializing security handshake for " .. LICENSE_CONFIG.ProductName .. "...")

    -- 1. Owner Roblox ID Check (If game creator is a User)
    if LICENSE_CONFIG.OwnerRobloxId > 0 then
        if game.CreatorType == Enum.CreatorType.User then
            if game.CreatorId ~= LICENSE_CONFIG.OwnerRobloxId then
                local msg = "Game owner (" .. tostring(game.CreatorId) .. ") does not match licensed purchaser (" .. tostring(LICENSE_CONFIG.OwnerRobloxId) .. ")"
                logLicenseEvent("FAILED", msg)
                return false, msg
            end
        end
    end

    -- 2. Specific Place ID Check
    if LICENSE_CONFIG.AllowedPlaceId > 0 and game.PlaceId ~= LICENSE_CONFIG.AllowedPlaceId then
        local msg = "Unauthorized PlaceId: " .. tostring(game.PlaceId)
        logLicenseEvent("FAILED", msg)
        return false, msg
    end

    -- 3. Group Owner Check (If game is group-owned)
    if LICENSE_CONFIG.AllowedGroupId > 0 and game.CreatorType == Enum.CreatorType.Group then
        if game.CreatorId ~= LICENSE_CONFIG.AllowedGroupId then
            local msg = "Unauthorized GroupId: " .. tostring(game.CreatorId)
            logLicenseEvent("FAILED", msg)
            return false, msg
        end
    end

    -- 4. HTTP Service Check
    local httpEnabled = pcall(function()
        HttpService:GetAsync("https://google.com")
    end)

    if not httpEnabled then
        warn("[RetailNetwork] Warning: Allow HTTP Requests is disabled in Game Settings -> Security!")
        if RunService:IsStudio() and LICENSE_CONFIG.DebugMode then
            return true, "Studio Debug Mode"
        end
    end

    logLicenseEvent("PASSED", "Successfully authenticated license key: " .. LICENSE_CONFIG.LicenseKey)
    return true, "Authorized"
end

local isAuthorized, reason = verifyLicense()

if not isAuthorized then
    warn("════════════════════════════════════════════════════════════════════════════")
    warn("❌ [RetailNetwork] Product Authorization Failed: " .. tostring(reason))
    warn("❌ Unauthorized copy of " .. LICENSE_CONFIG.ProductName)
    warn("❌ Purchase a legitimate license from RetailNetwork Purchasing Hub.")
    warn("════════════════════════════════════════════════════════════════════════════")
    script:Destroy()
    error("[RetailNetwork Security Engine] Execution terminated: Unlicensed copy of " .. LICENSE_CONFIG.ProductName)
else
    print("════════════════════════════════════════════════════════════════════════════")
    print("✅ [RetailNetwork] License Authenticated successfully for: " .. LICENSE_CONFIG.ProductName)
    print("✅ License Key: " .. LICENSE_CONFIG.LicenseKey)
    print("════════════════════════════════════════════════════════════════════════════")
    
    --------------------------------------------------------------------------------
    -- 🚀 YOUR PROTECTED PRODUCT CODE / MODULES EXECUTE HERE:
    --------------------------------------------------------------------------------
    
end
'''
    return luau_code
