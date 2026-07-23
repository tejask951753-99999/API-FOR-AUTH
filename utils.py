import httpx
from datetime import datetime, timezone
from google.cloud.firestore_v1.base_query import FieldFilter

def parse_expiry(expire_str: str) -> datetime:
    if not expire_str:
        raise ValueError("Expiration string is empty")
    s = expire_str.strip()

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except ValueError:
        pass

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
            
    raise ValueError(f"Unsupported datetime format: {expire_str}")


def log_info(msg): print(f"\033[94m[INFO]\033[0m {msg}")
def log_success(msg): print(f"\033[92m[SUCCESS]\033[0m {msg}")
def log_warn(msg): print(f"\033[93m[WARNING]\033[0m {msg}")
def log_err(msg): print(f"\033[91m[ERROR]\033[0m {msg}")

async def send_discord_webhook(url, user_data, config, app_name, ip_address, title="Login Authenticated", color=65280, reason=None):
    if not url:
        return
    if "discord.com" in url:
        url = url.replace("discord.com", "discordapp.com")

    fields = []
    fields.append({"name": "User", "value": f"`{user_data.get('username', 'Unknown')}`", "inline": True})
    if config.get('show_app'):
        fields.append({"name": "Application", "value": f"`{app_name}`", "inline": True})
    if ip_address:
        fields.append({"name": "IP Address", "value": f"`{ip_address}`", "inline": True})
    if config.get('show_hwid') and user_data.get('hwid'):
        fields.append({"name": "HWID", "value": f"```{user_data['hwid']}```", "inline": False})
    if config.get('show_expiry'):
        exp_raw = user_data.get('expires_at', 'N/A')
        exp = exp_raw.split('T')[0] if exp_raw else "N/A"
        fields.append({"name": "Expiry Date", "value": f"`{exp}`", "inline": True})
    if reason:
        fields.append({"name": "Error", "value": f"```{reason}```", "inline": False})

    embed = {
        "title": title,
        "color": color,
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

async def send_discord_error_webhook(primary_url, user_data, config, app_name, ip_address, reason):
    if not config.get('error_enabled'):
        return
    target_url = (config.get('error_webhook_url') or primary_url or "").strip()
    if not target_url:
        return
    await send_discord_webhook(target_url, user_data, config, app_name, ip_address, "Authentication Error", 15158332, reason)


def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception as e:
        err_msg = str(e)
        if "index" in err_msg.lower() or "failedprecondition" in err_msg.lower():
            log_err(f"Firestore missing index error. Please create the index: {err_msg}")
        else:
            log_err(f"Error getting count: {e}")
        return 0


def get_reseller_counts(db, appid: str, email: str) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    email_lower = email.lower()

    # Licenses query
    lic_ref = db.collection('licenses').where(filter=FieldFilter('appid', '==', appid)).where(filter=FieldFilter('created_by', '==', email_lower))
    today_lic_agg = lic_ref.where(filter=FieldFilter('created_at', '>=', today_start)).count()
    month_lic_agg = lic_ref.where(filter=FieldFilter('created_at', '>=', month_start)).count()

    # Users query
    user_ref = db.collection('users').where(filter=FieldFilter('appid', '==', appid)).where(filter=FieldFilter('created_by', '==', email_lower))
    today_users_agg = user_ref.where(filter=FieldFilter('created_at', '>=', today_start)).count()
    month_users_agg = user_ref.where(filter=FieldFilter('created_at', '>=', month_start)).count()

    today_lic = get_secure_count(today_lic_agg)
    month_lic = get_secure_count(month_lic_agg)
    
    today_users = get_secure_count(today_users_agg)
    month_users = get_secure_count(month_users_agg)

    return {
        "today_licenses": today_lic,
        "month_licenses": month_lic,
        "today_users": today_users,
        "month_users": month_users,
        "today_total": today_lic + today_users,
        "month_total": month_lic + month_users
    }
