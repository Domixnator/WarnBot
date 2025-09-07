import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import threading
import datetime
import itertools

# -----------------------------
#  Flask webserver (Render URL / keep-alive)
# -----------------------------
app = Flask("")

@app.route("/")
def home():
    return "✅ A bot él és fut Renderen!"

def run_web():
    port = int(os.environ.get("PORT", 8080))  # Render ad PORT-ot
    app.run(host="0.0.0.0", port=port)

# -----------------------------
#  Warnok tárolása
# -----------------------------
WARN_FILE = "warnings.json"

if os.path.exists(WARN_FILE):
    with open(WARN_FILE, "r", encoding="utf-8") as f:
        warnings = json.load(f)
else:
    warnings = {}

def save_warnings():
    with open(WARN_FILE, "w", encoding="utf-8") as f:
        json.dump(warnings, f, indent=4, ensure_ascii=False)

# ID generátor (folyamatos növekvő szám)
last_id = max([w.get("id", 0) for warns in warnings.values() for w in warns], default=0)
warn_id_counter = itertools.count(last_id + 1)

# -----------------------------
#  Discord bot (slash parancsok)
# -----------------------------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_ROLES = ["WarnStaff"]  # Csak ezek a rangok használhatják
LOG_CHANNEL_ID = 1302415427070201985  # <-- Ide írd a log csatorna ID-ját

def has_permission(interaction: discord.Interaction) -> bool:
    roles = [r.name for r in interaction.user.roles]
    return any(r in ALLOWED_ROLES for r in roles)

async def log_action(message: str):
    """Log üzenet küldése a megadott csatornába"""
    if LOG_CHANNEL_ID:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(message)

@bot.event
async def on_ready():
    print(f"✅ Bejelentkezve mint {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Sync kész: {len(synced)} parancs")
    except Exception as e:
        print(f"❌ Sync hiba: {e}")

# -----------------------------
#  Parancsok
# -----------------------------
@bot.tree.command(name="warn", description="Figyelmeztet egy felhasználót")
@app_commands.describe(member="Kit szeretnél warnolni?", reason="Miért kapja a warningot?")
async def warn_slash(interaction: discord.Interaction, member: discord.Member, reason: str):
    if not has_permission(interaction):
        await interaction.response.send_message("⛔ Nincs jogod ehhez!", ephemeral=True)
        return

    user_id = str(member.id)
    warnings.setdefault(user_id, [])
    warn_id = next(warn_id_counter)
    warnings[user_id].append({
        "id": warn_id,
        "reason": reason,
        "moderator": interaction.user.name,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_warnings()

    await interaction.response.send_message(
        f"⚠️ {member.mention} figyelmeztetést kapott! Indok: **{reason}** | ID: `{warn_id}`"
    )
    await log_action(f"⚠️ **WARN** | {member} (ID: {member.id}) kapott egy figyelmeztetést.\n"
                     f"Indok: {reason}\nModerator: {interaction.user} | Warn ID: `{warn_id}`")

@bot.tree.command(name="warnlist", description="Warnok listázása")
async def warnlist_slash(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("⛔ Nincs jogod ehhez!", ephemeral=True)
        return

    if not warnings:
        await interaction.response.send_message("✅ Még senki nem kapott figyelmeztetést.", ephemeral=True)
        return

    embed = discord.Embed(title="⚠️ Warn lista", color=discord.Color.orange())
    for user_id, warns in warnings.items():
        try:
            user = await bot.fetch_user(int(user_id))
        except Exception:
            continue
        warn_text = "\n".join([
            f"ID: `{w['id']}` – {w['reason']} *(adta: {w['moderator']} | {w.get('date', 'nincs dátum')})*"
            for w in warns
        ])
        embed.add_field(name=f"{user} – {len(warns)} warn", value=warn_text, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clearwarnid", description="Egy adott warn törlése ID alapján")
@app_commands.describe(warn_id="Melyik warn ID-t töröljük?")
async def clearwarnid_slash(interaction: discord.Interaction, warn_id: int):
    if not has_permission(interaction):
        await interaction.response.send_message("⛔ Nincs jogod ehhez!", ephemeral=True)
        return

    found = False
    for user_id, warns in list(warnings.items()):
        for w in list(warns):
            if int(w.get("id", -1)) == warn_id:
                warns.remove(w)
                if not warns:
                    warnings.pop(user_id)
                save_warnings()
                await interaction.response.send_message(f"✅ Warn ID `{warn_id}` törölve.")
                await log_action(f"🗑 **CLEAR WARN** | Warn ID `{warn_id}` törölve.\n"
                                 f"Moderator: {interaction.user}")
                found = True
                break
        if found:
            break

    if not found:
        await interaction.response.send_message(f"⚠️ Nem található warn ID `{warn_id}`.")

@bot.tree.command(name="clearwarn", description="Felhasználó összes warnjának törlése")
@app_commands.describe(member="Kinek töröljük a warnokat?")
async def clearwarn_slash(interaction: discord.Interaction, member: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("⛔ Nincs jogod ehhez!", ephemeral=True)
        return
    user_id = str(member.id)
    if user_id in warnings:
        count = len(warnings[user_id])
        warnings.pop(user_id)
        save_warnings()
        await interaction.response.send_message(f"✅ {member.mention} összes warnja törölve. ({count} db)")
        await log_action(f"🗑 **CLEAR ALL WARNS** | {member} ({member.id}) összes warnja törölve.\n"
                         f"Moderator: {interaction.user} | {count} db warn törölve")
    else:
        await interaction.response.send_message(f"ℹ️ {member.mention} nem rendelkezik warnnal.", ephemeral=True)

@bot.tree.command(name="help", description="Összes parancs listázása")
async def help_slash(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("⛔ Nincs jogod ehhez!", ephemeral=True)
        return
    embed = discord.Embed(title="📜 Elérhető parancsok", color=discord.Color.blue())
    for cmd in bot.tree.get_commands():
        embed.add_field(name=f"/{cmd.name}", value=cmd.description or "Nincs leírás", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="test", description="Teszteld, hogy a bot működik-e")
async def test_slash(interaction: discord.Interaction):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await interaction.response.send_message(
        f"✅ A bot él és fut!\n⏰ Idő: {now}\n🤖 Bot: {bot.user}", 
        ephemeral=True
    )

# -----------------------------
#  Indítás
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("❌ DISCORD_BOT_TOKEN hiányzik (Render env var)!")
    bot.run(token)


