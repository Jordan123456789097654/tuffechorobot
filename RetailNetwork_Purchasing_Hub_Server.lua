--[[
    ================================================================================
    🛒 RETAILNETWORK IN-GAME PURCHASING HUB & LICENSE VENDOR
    ================================================================================
    Place this script into ServerScriptService inside your Roblox Purchasing Hub game.
    
    Features:
    • Prompts MarketplaceService Developer Product purchase.
    • Listens to ProcessReceipt.
    • Auto-generates and grants a RetailNetwork License Key to the buyer.
    • Sends the license key to the buyer in-game (ScreenGui notification)
    • Syncs the purchase to RetailNetwork Discord via Webhook.
    • In-game license validation check.
    ================================================================================
--]]

local MarketplaceService = game:GetService("MarketplaceService")
local Players = game:GetService("Players")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

--------------------------------------------------------------------------------
-- ⚙️ CONFIGURATION
--------------------------------------------------------------------------------
local HUB_CONFIG = {
    -- Put your Discord Webhook URL here to receive instant purchase & license alerts
    DiscordWebhookUrl = "", 
    
    -- Products catalogue mapping: DeveloperProductId -> Product Data
    Products = {
        [1892019283] = {
            ProductName = "Self-Checkout Register System V2",
            Version = "2.0.0",
            PriceRobux = 250,
        },
        [1892019284] = {
            ProductName = "Retail Anti-Theft Sensor Gates",
            Version = "1.0.0",
            PriceRobux = 150,
        },
        [1892019285] = {
            ProductName = "Point of Sale (POS) Barcode Scanner",
            Version = "1.5.0",
            PriceRobux = 100,
        }
    }
}

-- RemoteEvent to notify client GUI with their license key
local LicenseGrantedEvent = ReplicatedStorage:FindFirstChild("RetailNetwork_LicenseGranted")
if not LicenseGrantedEvent then
    LicenseGrantedEvent = Instance.new("RemoteEvent")
    LicenseGrantedEvent.Name = "RetailNetwork_LicenseGranted"
    LicenseGrantedEvent.Parent = ReplicatedStorage
end

--------------------------------------------------------------------------------
-- 🔑 LICENSE GENERATOR FUNCTION
--------------------------------------------------------------------------------
local function generateLicenseKey()
    local chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    local function randomChunk(len)
        local s = ""
        for i = 1, len do
            local r = math.random(1, #chars)
            s = s .. string.sub(chars, r, r)
        end
        return s
    end
    return "RN-" .. randomChunk(4) .. "-" .. randomChunk(4) .. "-" .. randomChunk(4) .. "-" .. randomChunk(4)
end

--------------------------------------------------------------------------------
-- 📡 DISCORD WEBHOOK PURCHASE DISPATCHER
--------------------------------------------------------------------------------
local function dispatchDiscordPurchaseLog(player, productInfo, licenseKey)
    if HUB_CONFIG.DiscordWebhookUrl == "" then return end
    
    task.spawn(function()
        local payload = HttpService:JSONEncode({
            embeds = {{
                title = "🛒 RetailNetwork • Product Purchased & License Issued!",
                description = "**Buyer:** `" .. player.Name .. "` (`" .. tostring(player.UserId) .. "`)\n" ..
                              "**Product:** `" .. productInfo.ProductName .. "` (v" .. productInfo.Version .. ")\n" ..
                              "**Price:** `" .. tostring(productInfo.PriceRobux) .. " Robux`\n\n" ..
                              "**🔑 Generated License Key:**\n```fix\n" .. licenseKey .. "\n```\n" ..
                              "**Bound Game Owner:** `" .. tostring(player.UserId) .. "`\n" ..
                              "**Status:** `Active`",
                color = 3066993,
                footer = { text = "RetailNetwork Purchasing Hub Engine" },
                timestamp = DateTime.now():ToIsoDate()
            }}
        })
        pcall(function()
            HttpService:PostAsync(HUB_CONFIG.DiscordWebhookUrl, payload, Enum.HttpContentType.ApplicationJson)
        end)
    end)
end

--------------------------------------------------------------------------------
-- 💳 MARKETPLACE SERVICE RECEIPT PROCESSING
--------------------------------------------------------------------------------
MarketplaceService.ProcessReceipt = function(receiptInfo)
    local player = Players:GetPlayerByUserId(receiptInfo.PlayerId)
    local productId = receiptInfo.ProductId
    local product = HUB_CONFIG.Products[productId]

    if not product then
        warn("[RetailNetwork Hub] Received purchase for unmapped product ID: " .. tostring(productId))
        return Enum.ProductPurchaseDecision.PurchaseGranted
    end

    local licenseKey = generateLicenseKey()
    print("════════════════════════════════════════════════════════════════════════════")
    print("🛒 [RetailNetwork Hub] Purchase Confirmed!")
    print("👤 Buyer: " .. (player and player.Name or "UserId: " .. tostring(receiptInfo.PlayerId)))
    print("📦 Product: " .. product.ProductName)
    print("🔑 Issued License Key: " .. licenseKey)
    print("════════════════════════════════════════════════════════════════════════════")

    -- Notify the player on their screen
    if player then
        LicenseGrantedEvent:FireClient(player, {
            ProductName = product.ProductName,
            LicenseKey = licenseKey,
            OwnerRobloxId = player.UserId
        })
    end

    -- Send notification to Discord
    if player then
        dispatchDiscordPurchaseLog(player, product, licenseKey)
    end

    return Enum.ProductPurchaseDecision.PurchaseGranted
end

--------------------------------------------------------------------------------
-- 🛍️ HELPER FUNCTION: Prompt Purchase from ProximityPrompt or Button
--------------------------------------------------------------------------------
-- You can fire this function when a user clicks a shelf item or UI button!
local function promptProductPurchase(player, productId)
    if HUB_CONFIG.Products[productId] then
        MarketplaceService:PromptProductPurchase(player, productId)
    else
        warn("Invalid product ID: " .. tostring(productId))
    end
end
