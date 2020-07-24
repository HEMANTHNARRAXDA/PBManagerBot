import html
import re
from typing import Optional, List

from telegram import Message, Chat, Update, Bot, User, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.error import BadRequest
from telegram.ext import Filters, MessageHandler, CommandHandler, CallbackQueryHandler, run_async
from telegram.utils.helpers import mention_html

from tg_bot import dispatcher, WHITELIST_USERS, TIGER_USERS
from tg_bot.modules.helper_funcs.chat_status import is_user_admin, user_admin, can_restrict, bot_admin, user_admin_no_reply, connection_status
from tg_bot.modules.log_channel import loggable
from tg_bot.modules.sql import antiflood_sql as sql

FLOOD_GROUP = 3


@run_async
@loggable
def check_flood(bot: Bot, update: Update) -> str:
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    log_message = ""

    if not user:  # ignore channels
        return log_message

    # ignore admins and whitelists
    if (is_user_admin(chat, user.id) 
            or user.id in WHITELIST_USERS
            or user.id in TIGER_USERS):
        sql.update_flood(chat.id, None)
        return log_message

    should_mute = sql.update_flood(chat.id, user.id)
    if not should_mute:
        return ""

    try:
        bot.restrict_chat_member(
            chat.id,
            user.id,
            can_send_messages=False
        )

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Unmute", callback_data="unmute_flooder({})".format(user.id))]]
        )
        bot.send_message(chat.id,
            f"{mention_html(user.id, user.first_name)} has been muted for flooding the group!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )


        return "<b>{}:</b>" \
               "\n#MUTED" \
               "\n<b>User:</b> {}" \
               "\nFlooded the group.\nMuted until an admin unmutes".format(html.escape(chat.title),
                                             mention_html(user.id, user.first_name))

    except BadRequest:
        msg.reply_text("I can't mute people here, give me permissions first! Until then, I'll disable antiflood.")
        sql.set_flood(chat.id, 0)
        log_message = ("<b>{chat.title}:</b>\n"
                       "#INFO\n"
                       "Don't have kick permissions, so automatically disabled antiflood.")

        return log_message


@run_async
@user_admin
@can_restrict
@loggable
def set_flood(bot: Bot, update: Update, args: List[str]) -> str:
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    message = update.effective_message  # type: Optional[Message]

    if len(args) >= 1:
        val = args[0].lower()
        if val == "off" or val == "no" or val == "0":
            sql.set_flood(chat.id, 0)
            message.reply_text("Antiflood has been disabled.")

        elif val.isdigit():
            amount = int(val)
            if amount <= 0:
                sql.set_flood(chat.id, 0)
                message.reply_text("Antiflood has been disabled.")
                return "<b>{}:</b>" \
                       "\n#SETFLOOD" \
                       "\n<b>Admin:</b> {}" \
                       "\nDisabled antiflood.".format(html.escape(chat.title), mention_html(user.id, user.first_name))

            elif amount < 3:
                message.reply_text("Antiflood has to be either 0 (disabled), or a number bigger than 3!")
                return ""

            else:
                sql.set_flood(chat.id, amount)
                message.reply_text("Antiflood has been updated and set to {}".format(amount))
                return "<b>{}:</b>" \
                       "\n#SETFLOOD" \
                       "\n<b>Admin:</b> {}" \
                       "\nSet antiflood to <code>{}</code>.".format(html.escape(chat.title),
                                                                    mention_html(user.id, user.first_name), amount)

        else:
            message.reply_text("Unrecognised argument - please use a number, 'off', or 'no'.")

    return ""


@run_async
def flood(bot: Bot, update: Update):
    chat = update.effective_chat  # type: Optional[Chat]

    limit = sql.get_flood_limit(chat.id)
    if limit == 0:
        update.effective_message.reply_text("I'm not currently enforcing flood control!")
    else:
        update.effective_message.reply_text(
            "I'm currently banning users if they send more than {} consecutive messages.".format(limit))


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    limit = sql.get_flood_limit(chat_id)
    if limit == 0:
        return "*Not* currently enforcing flood control."
    else:
        return "Antiflood is set to `{}` messages.".format(limit)


__help__ = """
 - /flood: Get the current flood control setting

*Admin only:*
 - /setflood <int/'no'/'off'>: enables or disables flood control
"""

__mod_name__ = "AntiFlood"

FLOOD_BAN_HANDLER = MessageHandler(Filters.all & ~Filters.status_update & Filters.group, check_flood)
SET_FLOOD_HANDLER = CommandHandler("setflood", set_flood, pass_args=True, filters=Filters.group)
FLOOD_HANDLER = CommandHandler("flood", flood, filters=Filters.group)

dispatcher.add_handler(FLOOD_BAN_HANDLER, FLOOD_GROUP)
dispatcher.add_handler(SET_FLOOD_HANDLER)
dispatcher.add_handler(FLOOD_HANDLER)
