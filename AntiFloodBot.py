# coding=utf-8
import os.path
import random
import time

import botogram
import yaml

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


# suggest a replace of youtube link with their respective invidious
@bot.message_matches(
    "((?:https?:\\/\\/)?(?:www\\.)?youtu\\.?be(?:\\.com)?\\/?.*"
    "(?:watch|embed)?(?:.*v=|v\\/|\\/)([\\w_-]+))",
    multiple=True)
def youtube_link_replace(message, matches):
    if len(matches) == 2:
        blip_blopper(message, "https://invidio.us/watch?v=", matches)


# suggest a replace of twitter link with their respective nitter
@bot.message_matches(
    "((?:https?:\\/\\/)?(?:www\\.)?twitter\\.com\\/((?:#!\\/)?\\w+"
    "(?:\\/status\\/\\d+)?))",
    multiple=True)
def twitter_link_replace(message, matches):
    if len(matches) == 2:
        blip_blopper(message, "https://nitter.net/", matches)


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


# generate captcha buttons
def generate_captcha_buttons():
    btns = botogram.Buttons()
    tempemojis = emojis
    for i in range(len(emojis)):
        rkey = random.choice(list(tempemojis))
        btns[i].callback(emojis[rkey]["emoji"], "captcha", rkey)
        tempemojis = removekey(tempemojis, rkey)

    return btns


def blip_blopper(message, base_url, matches):
    btns = botogram.Buttons()
    btns[0].callback("Elimina", "delete_message", str(message.sender.id))
    message.delete()
    message.chat.send(
        blip_blop_message(message, base_url, matches),
        syntax='markdown',
        attach=btns)


def blip_blop_message(message, base_url, matches):
    privacy_friendly_url = base_url + escape(matches[1])
    return "Blip blop, ho convertito il messaggio di %s in modo da " \
           "rispettare la tua privacy:\n" \
           "\"%s\"\n\n" \
           "[Scopri cos'è successo](%s)" \
           % (get_user_tag(message.sender),
              message.text.replace(matches[0], privacy_friendly_url),
              blip_blop_explanation)


def get_user_tag(user):
    if user.username:
        return '@' + escape(user.username)
    else:
        return '[%s](tg:///user?id=%d)' \
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


if __name__ == "__main__":
    bot.run()
