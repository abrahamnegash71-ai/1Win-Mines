import os
import logging
import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    MenuButtonWebApp,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────
ADMIN_ID       = int(os.environ.get("ADMIN_TELEGRAM_ID", "5555698804"))
FREE_LIMIT     = 3
PROMO_CODE     = "MILKOFIX"
PARTNER_LINK   = os.environ.get("WIN_PARTNER_LINK",  "https://lkqz.cc/a07b09")
TG_SUPPORT_LINK = os.environ.get("TG_SUPPORT_LINK", "https://t.me/WON_BET1")
WA_SUPPORT_LINK = os.environ.get("WA_SUPPORT_LINK", "https://wa.me/251930989018")
API_BASE       = "http://localhost:80/api"

# ── API helpers (DB-backed via Express) ───────────────────────
async def api_get_tier(telegram_id: str) -> str:
    """Return 'free', 'registered', or 'vip' from the database."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE}/user-status/{telegram_id}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                data = await r.json()
                return data.get("tier", "free")
    except Exception as e:
        logger.error("api_get_tier error: %s", e)
        return "free"


async def api_grant_vip(telegram_id: str) -> bool:
    """Grant VIP (deposit) tier via the webhook endpoint."""
    secret  = os.environ.get("WEBHOOK_SECRET", "")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}/webhook/1win",
                json={"user_id": telegram_id, "event_type": "DEPOSIT"},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                return r.status == 200
    except Exception as e:
        logger.error("api_grant_vip error: %s", e)
        return False


async def api_revoke_access(telegram_id: str) -> bool:
    """Revoke a user's access back to free tier."""
    secret  = os.environ.get("WEBHOOK_SECRET", "")
    headers = {"Content-Type": "application/json", "X-Admin-Secret": secret}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}/admin/deny",
                json={"telegram_id": telegram_id},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                return r.status == 200
    except Exception as e:
        logger.error("api_revoke_access error: %s", e)
        return False


# ── Helpers ───────────────────────────────────────────────────
def get_webapp_url() -> str:
    domains = os.environ.get("REPLIT_DOMAINS", "")
    domain  = domains.split(",")[0].strip() if domains else ""
    return f"https://{domain}/api/app/" if domain else ""


def build_main_menu(webapp_url: str) -> InlineKeyboardMarkup:
    rows = []
    if webapp_url:
        rows.append([InlineKeyboardButton("🔍 Open Signal Generator", web_app=WebAppInfo(url=webapp_url))])
    rows.append([
        InlineKeyboardButton("✈️ Telegram Support", url=TG_SUPPORT_LINK),
        InlineKeyboardButton("💬 WhatsApp Support", url=WA_SUPPORT_LINK),
    ])
    return InlineKeyboardMarkup(rows)


def build_lock_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Register on 1Win", url=PARTNER_LINK)],
        [
            InlineKeyboardButton("✈️ Telegram Support", url=TG_SUPPORT_LINK),
            InlineKeyboardButton("💬 WhatsApp Support", url=WA_SUPPORT_LINK),
        ],
    ])


# ── Command handlers ──────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id    = update.effective_user.id
    user_id_s  = str(user_id)
    webapp_url = get_webapp_url()

    # Admin always bypasses the DB check
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            f"👑 *Admin Mode — Full Access*\n\nYour ID: `{user_id_s}`",
            parse_mode="MarkdownV2",
            reply_markup=build_main_menu(webapp_url),
        )
        return

    tier = await api_get_tier(user_id_s)

    if tier in ("registered", "vip"):
        tier_label = "⭐ VIP Member" if tier == "vip" else "✓ Registered Member"
        await update.message.reply_text(
            f"🎮 *Welcome back\\!* {tier_label}\n\n"
            "▸ Use the button below to launch the radar signal tool\\.",
            parse_mode="MarkdownV2",
            reply_markup=build_main_menu(webapp_url),
        )
    else:
        await update.message.reply_text(
            f"🔒 *Access Denied\\! Your free limit is over\\.*\n\n"
            f"Your Telegram ID: `{user_id_s}`\n\n"
            f"To unlock unlimited VIP signals:\n"
            f"1\\. Click the button below and register on 1Win\\.\n"
            f"2\\. Use Promo Code: `{PROMO_CODE}` during registration and make a deposit\\.\n"
            f"3\\. Send your Telegram ID to the admin for manual approval\\.",
            parse_mode="MarkdownV2",
            reply_markup=build_lock_keyboard(),
        )


async def allow_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: /allow <telegram_id> — grants VIP access."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You do not have permission to use this command!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please provide a User ID.\nExample: /allow 1234567")
        return

    target_id = context.args[0].strip()
    if not target_id.isdigit():
        await update.message.reply_text("⚠️ Invalid ID — must be a numeric Telegram ID.")
        return

    ok = await api_grant_vip(target_id)
    if ok:
        await update.message.reply_text(
            f"✅ User `{target_id}` has been successfully approved to VIP\\!",
            parse_mode="MarkdownV2",
        )
        try:
            await context.bot.send_message(
                chat_id=int(target_id),
                text=(
                    "🎉 *Congratulations\\!* The admin has approved your VIP status\\!\n\n"
                    "You now have unlimited premium signals\\.\n"
                    "Type /start to access them\\!"
                ),
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.warning("Could not notify user %s: %s", target_id, e)
    else:
        await update.message.reply_text(
            f"❌ Failed to grant access to `{target_id}`\\. Check server logs\\.",
            parse_mode="MarkdownV2",
        )


async def deny_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: /deny <telegram_id> — revokes access back to free tier."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You do not have permission to use this command!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please provide a User ID.\nExample: /deny 1234567")
        return

    target_id = context.args[0].strip()
    if not target_id.isdigit():
        await update.message.reply_text("⚠️ Invalid ID — must be a numeric Telegram ID.")
        return

    ok = await api_revoke_access(target_id)
    if ok:
        await update.message.reply_text(
            f"✅ User `{target_id}` access has been revoked\\.",
            parse_mode="MarkdownV2",
        )
    else:
        await update.message.reply_text(
            f"❌ Failed to revoke access for `{target_id}`\\. Check server logs\\.",
            parse_mode="MarkdownV2",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ *How to Use*\n\n"
        "1\\. Tap *Open Signal Generator* to launch the visual radar tool\\.\n"
        "2\\. If your account is locked, register using the 1Win partner link\\.\n"
        "3\\. Use Promo Code: `MILKOFIX` and make a deposit\\.\n"
        "4\\. Send your Telegram ID to the admin for approval\\.\n\n"
        "*Admin Commands:*\n"
        "• /allow \\<id\\> — Grant VIP access\n"
        "• /deny \\<id\\> — Revoke access",
        parse_mode="MarkdownV2",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id == ADMIN_ID:
        return

    tier = await api_get_tier(str(user_id))
    if tier not in ("registered", "vip"):
        await query.edit_message_text(
            f"🔒 *Access Denied\\! Your free limit is over\\.*\n\n"
            f"Your Telegram ID: `{user_id}`\n\n"
            f"Register using the link below, use Promo Code: `{PROMO_CODE}`, and deposit to unlock\\.",
            reply_markup=build_lock_keyboard(),
            parse_mode="MarkdownV2",
        )


# ── App init ──────────────────────────────────────────────────
async def post_init(app) -> None:
    webapp_url = get_webapp_url()
    if webapp_url:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🔍 Signal App",
                web_app=WebAppInfo(url=webapp_url),
            )
        )
        logger.info("Menu button set → %s", webapp_url)
    else:
        logger.warning("REPLIT_DOMAINS not set — skipping menu button")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("allow", allow_user))
    application.add_handler(CommandHandler("deny",  deny_user))
    application.add_handler(CommandHandler("help",  help_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Mines Bot starting… (Admin ID: %s)", ADMIN_ID)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
