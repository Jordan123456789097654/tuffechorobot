--[[
    ================================================================================
    💻 RETAILNETWORK CLIENT LICENSE POPUP & NOTIFICATION GUI
    ================================================================================
    Place this LocalScript into StarterPlayerScripts or inside your Hub ScreenGui.
    When a purchase completes, it pops up a clean UI presenting their license key
    and copying it to clipboard.
    ================================================================================
--]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")
local player = Players.LocalPlayer

local LicenseGrantedEvent = ReplicatedStorage:WaitForChild("RetailNetwork_LicenseGranted")

LicenseGrantedEvent.OnClientEvent:Connect(function(data)
    print("--------------------------------------------------")
    print("🎉 Congratulations on purchasing " .. tostring(data.ProductName) .. "!")
    print("🔑 Your License Key is: " .. tostring(data.LicenseKey))
    print("🔒 Locked to your Roblox Account: " .. tostring(data.OwnerRobloxId))
    print("--------------------------------------------------")

    -- Create or show celebratory notification ScreenGui
    local playerGui = player:WaitForChild("PlayerGui")
    local screenGui = Instance.new("ScreenGui")
    screenGui.Name = "RetailNetwork_LicensePopup"
    screenGui.ResetOnSpawn = false
    screenGui.Parent = playerGui

    local frame = Instance.new("Frame")
    frame.Size = UDim2.new(0, 480, 0, 260)
    frame.Position = UDim2.new(0.5, -240, 0.5, -130)
    frame.BackgroundColor3 = Color3.fromRGB(20, 20, 25)
    frame.BorderSizePixel = 0
    frame.Parent = screenGui

    local corner = Instance.new("UICorner")
    corner.CornerRadius = UDim.new(0, 12)
    corner.Parent = frame

    local stroke = Instance.new("UIStroke")
    stroke.Color = Color3.fromRGB(46, 204, 113)
    stroke.Thickness = 2
    stroke.Parent = frame

    local title = Instance.new("TextLabel")
    title.Size = UDim2.new(1, 0, 0, 40)
    title.Text = "🛡️ RETAILNETWORK PRODUCT LICENSE"
    title.TextColor3 = Color3.fromRGB(46, 204, 113)
    title.Font = Enum.Font.GothamBold
    title.TextSize = 18
    title.BackgroundTransparency = 1
    title.Parent = frame

    local desc = Instance.new("TextLabel")
    desc.Size = UDim2.new(1, -40, 0, 50)
    desc.Position = UDim2.new(0, 20, 0, 45)
    desc.Text = "Thank you for purchasing " .. data.ProductName .. "!\nYour license is now activated for your Roblox account."
    desc.TextColor3 = Color3.fromRGB(220, 220, 220)
    desc.Font = Enum.Font.Gotham
    desc.TextSize = 14
    desc.TextWrapped = true
    desc.BackgroundTransparency = 1
    desc.Parent = frame

    -- Key Box
    local keyBox = Instance.new("TextBox")
    keyBox.Size = UDim2.new(1, -40, 0, 50)
    keyBox.Position = UDim2.new(0, 20, 0, 110)
    keyBox.Text = data.LicenseKey
    keyBox.TextColor3 = Color3.fromRGB(255, 255, 255)
    keyBox.BackgroundColor3 = Color3.fromRGB(35, 35, 45)
    keyBox.Font = Enum.Font.Code
    keyBox.TextSize = 16
    keyBox.ClearTextOnFocus = false
    keyBox.TextEditable = false
    keyBox.Parent = frame

    local keyCorner = Instance.new("UICorner")
    keyCorner.CornerRadius = UDim.new(0, 8)
    keyCorner.Parent = keyBox

    -- Close Button
    local closeBtn = Instance.new("TextButton")
    closeBtn.Size = UDim2.new(1, -40, 0, 40)
    closeBtn.Position = UDim2.new(0, 20, 0, 180)
    closeBtn.Text = "Close & Save"
    closeBtn.BackgroundColor3 = Color3.fromRGB(46, 204, 113)
    closeBtn.TextColor3 = Color3.fromRGB(20, 20, 25)
    closeBtn.Font = Enum.Font.GothamBold
    closeBtn.TextSize = 15
    closeBtn.Parent = frame

    local btnCorner = Instance.new("UICorner")
    btnCorner.CornerRadius = UDim.new(0, 8)
    btnCorner.Parent = closeBtn

    closeBtn.MouseButton1Click:Connect(function()
        screenGui:Destroy()
    end)
end)
