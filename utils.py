import httpx
from datetime import datetime

def log_info(msg): print(f"\033[94m[INFO]\033[0m {msg}")
def log_success(msg): print(f"\033[92m[SUCCESS]\033[0m {msg}")
def log_warn(msg): print(f"\033[93m[WARNING]\033[0m {msg}")
def log_err(msg): print(f"\033[91m[ERROR]\033[0m {msg}")

async def send_discord_webhook(url, user_data, config, app_name, ip_address):
    if not url: return
    if "discord.com" in url: url = url.replace("discord.com", "discordapp.com")

    fields = []
    fields.append({"name": "User", "value": f"`{user_data['username']}`", "inline": True})
    if config.get('show_app'): fields.append({"name": "Application", "value": f"`{app_name}`", "inline": True})
    if config.get('show_hwid') and user_data.get('hwid'): fields.append({"name": "HWID", "value": f"```{user_data['hwid']}```", "inline": False})
    if config.get('show_expiry'):
        exp_raw = user_data.get('expires_at', 'N/A')
        exp = exp_raw.split('T')[0] if exp_raw else "N/A"
        fields.append({"name": "Expiry Date", "value": f"`{exp}`", "inline": True})

    embed = {
        "title": "Login Authenticated",
        "color": 65280,
        "fields": fields,
        "footer": {"text": "Lynx Auth System"},
        "timestamp": datetime.utcnow().isoformat()
    }

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"embeds": [embed]}, headers=headers, timeout=10)
        except Exception as e:
            log_err(f"Webhook error: {e}")
