import asyncio
import io
import discord
from license_system import create_product, issue_license, generate_roblox_loader_script

async def execute_prefix_create_product(bot, message: discord.Message):
    """Interactive step-by-step prefix command wizard to create a product and issue a license."""
    author = message.author
    channel = message.channel

    def check(m):
        return m.author.id == author.id and m.channel.id == channel.id

    try:
        await channel.send(f"{author.mention} **[Step 1/4]** What is the name of the Roblox product you want to license? (e.g. `Self-Checkout Register System`)")
        msg1 = await bot.wait_for("message", timeout=60.0, check=check)
        product_name = msg1.content.strip()

        await channel.send(f"{author.mention} **[Step 2/4]** Enter a brief description for `{product_name}` (or type `skip`):")
        msg2 = await bot.wait_for("message", timeout=60.0, check=check)
        desc = "Standard RetailNetwork Product" if msg2.content.strip().lower() == "skip" else msg2.content.strip()

        await channel.send(f"{author.mention} **[Step 3/4]** Enter the **Allowed Roblox Place ID** (type `0` or `none` for any place):")
        msg3 = await bot.wait_for("message", timeout=60.0, check=check)
        try:
            place_id = int(msg3.content.strip())
        except ValueError:
            place_id = 0

        await channel.send(f"{author.mention} **[Step 4/4]** Enter the **Allowed Roblox Group ID** (type `0` or `none` for any group):")
        msg4 = await bot.wait_for("message", timeout=60.0, check=check)
        try:
            group_id = int(msg4.content.strip())
        except ValueError:
            group_id = 0

        try:
            create_product(product_name, desc, "1.0.0", author.id)
        except Exception:
            pass

        lic = issue_license(product_name, author.id, allowed_place_id=place_id, allowed_group_id=group_id)
        key = lic["license_key"]
        script_code = generate_roblox_loader_script(product_name, key, place_id, group_id)

        place_str = str(place_id) if place_id > 0 else "Universal (Any Place)"
        group_str = str(group_id) if group_id > 0 else "Universal (Any Group)"

        embed = discord.Embed(
            title="🛡️ Product & License Key Created • RetailNetwork Security",
            description=(
                f"Successfully registered product **{product_name}**!\n\n"
                f"**🔑 License Key:**\n```fix\n{key}\n```\n"
                f"**🏰 Allowed Place ID:** `{place_str}`\n"
                f"**👥 Allowed Group ID:** `{group_str}`\n"
                f"**🔒 Status:** `Active`\n\n"
                f"### 📜 How to protect your Roblox Product:\n"
                f"1. Open Roblox Studio and open your game or model.\n"
                f"2. Create a new **Server Script** in `ServerScriptService` (e.g. `RetailNetworkLoader`).\n"
                f"3. Paste the contents of the attached `.lua` file into it.\n"
                f"4. In Roblox Studio, make sure **Allow HTTP Requests** is turned **ON** (`Game Settings -> Security`)."
            ),
            color=0x2ECC71,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="RetailNetwork Anti-Leak & Licensing Engine")

        script_file = discord.File(
            fp=io.BytesIO(script_code.encode("utf-8")),
            filename=f"RetailNetwork_Loader_{product_name.replace(' ', '_')}.lua"
        )

        await channel.send(embed=embed, file=script_file)

    except asyncio.TimeoutError:
        await channel.send(f"{author.mention} ⏳ Product creation timed out. Please run `!rn create-product` again when ready.")
