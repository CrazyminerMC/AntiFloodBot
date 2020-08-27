# coding=utf-8
import os.path
import random
import time
from datetime import datetime as dt, timedelta
import re

import botogram
import yaml
import requests

import database as db

config = yaml.safe_load(open('config.yml'))

blip_blop_explanation = 'https://gitlab.com/etica-digitale/gruppo-telegram/-'\
        '/blob/master/Redirect-Spiegazione.md'

# bot information
bot = botogram.create(config.get('token'))
bot.about = "This bot is used to block a flooder with a captcha"
bot.owner = "@sonomichelequellostrano"

# antiflood config
antiflood_config = config.get('antiflood_config')

# emoji list for captcha
emojis = config.get('emojis')

# list of privacy friend Youtube player
ytinstances = config.get('ytinstances')


# delete message with replaced links if clicked by original sender
@bot.callback("delete_message")
def delete_message(query, data, chat, message):
    if query.sender.id == int(data):
        message.delete()
    else:
        query.notify("Solo chi ha inviato il messaggio originale può "
                     "cancellare questo",
                     alert=True)


# antiflood
@bot.process_message
def antiflood(shared, chat, message):
    db.add_user(message.sender.id, message.sender.username)
    db.update_username(message.sender)
    if 'users' not in shared:
        if os.path.isfile('data.yml'):
            shared['users'] = yaml.safe_load(open('data.yml')).get('users')
        else:
            shared['users'] = {}

    users = shared['users']
    currentmillis = int(round(time.time() * 1000))
    # Allows only groups
    if chat.type not in ("group", "supergroup"):
        return

    # Activate antiflood only for normal users
    if message.sender not in chat.admins:
        sender_id = message.sender.id
        if message.sender.id in users:
            user = users[sender_id]
            if 'bloccato' in user and user['bloccato'] == 0:
                rmessages = user['messages']
                starttime = user['starttime']
                delay = round((currentmillis - starttime) / 1000)
                print("delay %i    rmessages: %i" % (delay, rmessages))

                if delay > antiflood_config['secondi']:
                    users[sender_id] = {'messages': 1,
                                        'starttime': currentmillis,
                                        'bloccato': 0}
                    saveusers(users)
                    shared['users'] = users
                elif rmessages > antiflood_config["messaggi"]:
                    # mute the user
                    with chat.permissions(message.sender.id) as perms:
                        perms.send_messages = False  # Restrict user forever
                        perms.save()

                    # this is the captcha
                    emoji = random.choice(list(emojis))

                    user['bloccato'] = 1
                    user['emoji'] = emoji
                    user['errori'] = 0
                    user['messages'] = 0
                    saveusers(users)
                    shared['users'] = users

                    chat.send("%s clicca *%s* per risolvere il captcha. "
                              "*Errori*: %d"
                              % (get_user_tag(message.sender),
                                 emojis[user['emoji']]["description"],
                                 user['errori']),
                              syntax='markdown',
                              attach=generate_captcha_buttons())

            user['messages'] += 1
            saveusers(users)
            shared['users'] = users
        else:
            users[message.sender.id] = {'messages': 1,
                                        'starttime': currentmillis,
                                        'bloccato': 0}
            saveusers(users)
            shared['users'] = users


# twitter and youtube link replacer
@bot.process_message
def link_replacer(chat, message):
    clean_msg = message.text
    twitter_regex = r"(?:https?://)?(?:www\.)?twitter\.com/"
    youtube_regex = r"((?:https?://)?(?:www\.)?youtu\.?be(?:\.com)?/(.*(?:watch|embed)?(?:.*)[\w_-]+))"
    yt_matches = re.findall(youtube_regex, clean_msg, re.MULTILINE | re.IGNORECASE)
    twitter_matches = re.findall(twitter_regex, clean_msg, re.MULTILINE | re.IGNORECASE)
    blip_blop = False  # should blip blop or not

    if twitter_matches:
        clean_msg = re.sub(twitter_regex, 'https://nitter.net/', clean_msg, flags=re.MULTILINE | re.IGNORECASE)
        blip_blop = True

    if yt_matches:
        for match in yt_matches:
            url, video = match
            clean_msg = clean_msg.replace(url, f"{get_working_yt_instance(video)}{video}")
        blip_blop = True
    
    if blip_blop: blip_blopper(message, escape(clean_msg))


# captcha callback
@bot.callback("captcha")
def captcha_callback(shared, query, data, chat, message):
    if 'users' not in shared:
        if os.path.isfile('data.yml'):
            shared['users'] = yaml.safe_load(open('data.yml')).get('users')
        else:
            shared['users'] = {}

    users = shared['users']
    if query.sender.id in users:
        user = users[query.sender.id]
        if user['bloccato'] == 0:
            return
        if user['emoji'] == data:
            user['bloccato'] = 0
            user['errori'] = 0
            user['messages'] = 0
            saveusers(users)
            shared['users'] = users
            query.notify("Captcha risolto con successo")
            message.delete()
            with chat.permissions(query.sender.id) as perms:
                perms.send_messages = True
                perms.send_media_messages = True
                perms.send_other_messages = True
                perms.add_web_page_previews = True
                perms.save()
        else:
            user['errori'] += 1
            saveusers(users)
            shared['users'] = users
            if user['errori'] >= 2:
                message.edit("%s ha sbagliato due volte il captcha ed è stato "
                             "bloccato per sempre"
                             % (get_user_tag(query.sender)))
            else:
                message.edit("%s clicca *%s* per risolvere il captcha. "
                             "*Errori*: %d"
                             % (get_user_tag(query.sender),
                                emojis[user['emoji']]["description"],
                                user['errori']),
                             syntax='markdown',
                             attach=generate_captcha_buttons())


# punisce un utente
# 1 volta: muta utente per una settimana
# 2 volta: ban permanente, se è passato un anno funziona come la prima volta
@bot.command("punisci")
def punisci_command(chat, message, args):
    if chat.type not in ("group", "supergroup"):
        return

    if message.sender not in chat.admins:
        return

    if message.reply_to_message:
        user_to_punish = message.reply_to_message.sender
        db.add_user(user_to_punish.id, user_to_punish.username)
        punishment = punish_user(user_to_punish, chat)

        # l'utente è stato silenziato
        if punishment == 0:
            text = f"L'utente {get_user_tag(user_to_punish)} è stato silenziato per 7 giorni."

            if args:
                punishment_reason = " ".join(args)
                text = text + f"\nMotivo: {punishment_reason}"

            chat.send(text)
            return

        # l'utente è stato bannato
        if punishment == 1:
            text = f"L'utente {get_user_tag(user_to_punish)} è stato rimosso."

            if args:
                punishment_reason = " ".join(args)
                text = text + f"\nMotivo: {punishment_reason}"

            chat.send(text, syntax='markdown')
            return

    if len(args) >= 1:
        is_username = True  # check if args[0] is username or id
        if '@' not in args[0]:
            is_username = False

        if is_username:
            user = db.get_user_by_username(args[0].replace('@', ''))
            if user:
                user_id = user[0]
            else:
                return
            username = args[0]
        else:
            user_id = args[0]
            username = args[0]

        del args[0]
        punishment = punish_user(user_id, chat)
        # l'utente è stato silenziato
        if punishment == 0:
            text = f"L'utente [{username}](tg://user?id={user_id}) è stato silenziato per 7 giorni."

            if args:
                punishment_reason = " ".join(args)
                text = text + f"\nMotivo: {punishment_reason}"

            chat.send(text, syntax='markdown')
            return

        # l'utente è stato bannato
        if punishment == 1:
            text = f"L'utente [{username}](tg://user?id={user_id}) è stato rimosso."

            if args:
                punishment_reason = " ".join(args)
                text = text + f"\nMotivo: {punishment_reason}"

            chat.send(text, syntax='markdown')
            return



# banhammer per casi eccezionali
@bot.command("banhammer")
def banhammer_command(chat, message, args):
    if chat.type not in ("group", "supergroup"):
        return

    if message.sender not in chat.admins:
        return

    if message.reply_to_message:
        user_to_ban = message.reply_to_message.sender

        if not args:
            chat.ban(user_to_ban)
            chat.send(f"L'utente {get_user_tag(user_to_ban)} è stato rimosso.", syntax='markdown')
            db.remove_user(user_to_ban.id)
            return

        ban_reason = " ".join(args)
        chat.ban(user_to_ban)
        chat.send(
            f"L'utente {get_user_tag(user_to_ban)} è stato rimosso.\n"
            f"Motivo: {ban_reason}",
            syntax='markdown'
        )
        db.remove_user(user_to_ban.id)
        return

    # il comando non è usato in risposta e quindi richiede un id o username
    if len(args) >= 1:
        is_username = True  # check if args[0] is username or id
        if '@' not in args[0]:
            is_username = False

        if is_username:
            user = db.get_user_by_username(args[0].replace('@', ''))

            del args[0]

            chat.ban(user[0])
            if not args:
                chat.send(f"L'utente @{user[1]} è stato rimosso.", syntax='markdown')
            else:
                ban_reason = " ".join(args)
                chat.send(
                    f"L'utente @{user[1]} è stato rimosso.\n"
                    f"Motivo: {ban_reason}",
                    syntax='markdown'
                )
            db.remove_user(user[0])
        else:
            user = args[0]

            del args[0]

            chat.ban(user)
            if not args:
                chat.send(f"L'utente {user} è stato rimosso.", syntax='markdown')
            else:
                ban_reason = " ".join(args)
                chat.send(
                    f"L'utente {user} è stato rimosso.\n"
                    f"Motivo: {ban_reason}",
                    syntax='markdown'
                )
            db.remove_user(user)

        return


# generate captcha buttons
def generate_captcha_buttons():
    btns = botogram.Buttons()
    tempemojis = emojis
    for i in range(len(emojis)):
        rkey = random.choice(list(tempemojis))
        btns[i].callback(emojis[rkey]["emoji"], "captcha", rkey)
        tempemojis = removekey(tempemojis, rkey)

    return btns


def blip_blopper(message, clean_msg):
    btns = botogram.Buttons()
    btns[0].callback("Elimina", "delete_message", str(message.sender.id))
    message.delete()
    message.chat.send(
        blip_blop_message(message, clean_msg),
        syntax='markdown',
        attach=btns)


def blip_blop_message(message, clean_msg):
    return f"Blip blop, ho convertito il messaggio di {get_user_tag(message.sender)} in modo da " \
           "rispettare la tua privacy:\n" \
           f"\"{clean_msg}\"\n\n" \
           f"[Scopri cos'è successo]({blip_blop_explanation})"


def get_working_yt_instance(url_part):
    if url_part:
        for instance in ytinstances:
            instance_response = requests.get(instance + url_part)
            print("Richiesto l'url %s" % instance_response.url)
            if instance_response.status_code == 200:
                return instance
    return None


def get_user_tag(user):
    if user.username:
        return '@' + escape(user.username)
    else:
        return '[%s](tg://user?id=%d)' \
               % (escape(user.first_name), user.id)


def escape(string):
    return string.replace('_', '\\_').replace('*', '\\*') \
        .replace('`', '\\`').replace('[', '\\[')


# remove key from dictionary without really changing it
def removekey(d, key):
    newdict = dict(d)
    del newdict[key]
    return newdict


def saveusers(users):
    with open('data.yml', 'w') as file:
        yaml.dump({'users': users}, file)


# legenda dei return
# 0: l'utente non ha warn
# -1: l'utente ha un warn ma è più vecchio di un anno (31536000.0 secondi)
# 1: l'utente ha un warn ed è più recente di un anno (31536000.0 secondi)
def check_punishment(user_id):
    user = db.get_user(user_id)
    warnings = user[2]
    last_warn = user[3]
    more_than_one_year = (time.time() - float(last_warn) >= 31536000.0) if last_warn else True

    if warnings == 0:
        return 0

    if warnings == 1 and more_than_one_year:
        return -1

    return 1


# ritorna 0 se l'utente viene silenziato
# ritorna 1 se l'utente viene bannato
def punish_user(user, chat):
    if isinstance(user, botogram.User):
        user_id = user.id
    else:
        user_id = user

    punishment = check_punishment(user_id)

    # silenzia utente e aggiunge warn nel db
    if punishment == 0:
        with chat.permissions(user_id) as perms:
            perms.send_messages = False
            perms.send_media_messages = False
            perms.send_other_messages = False
            perms.add_web_page_previews = False
            perms.until_date = dt.now() + timedelta(days=7)
            perms.save()

        db.set_warning(user_id, 1)
        return 0

    # silenzia utente e cambia la data nel database con quella attuale
    if punishment == -1:
        with chat.permissions(user_id) as perms:
            perms.send_messages = False
            perms.send_media_messages = False
            perms.send_other_messages = False
            perms.add_web_page_previews = False
            perms.until_date = dt.now() + timedelta(days=7)
            perms.save()

        db.set_warning(user_id, 1)
        return 0

    # banna permanentemente l'utente e lo rimuove dal db
    if punishment == 1:
        chat.ban(user_id)
        db.remove_user(user_id)
        return 1


if __name__ == "__main__":
    bot.run()
