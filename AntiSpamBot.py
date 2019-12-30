import os.path
import random
import time

import botogram
import yaml

config = yaml.load(open('config.yml'), Loader=yaml.FullLoader)

# bot information
bot = botogram.create(config.get('token'))
bot.about = "This bot is used to block a flooder with a captcha"
bot.owner = "@sonomichelequellostrano"

# antiflood config
antiflood_config = config.get('antiflood_config')

# emoji list for captcha
emojis = config.get('emojis')


@bot.command("unmuteme", hidden=True)
def unmuteme(message):
    with bot.chat(-1001329432550).permissions(message.sender.id) as perms:
        perms.send_messages = False
        perms.save()
    message.chat.send('smutato')


# antiflood
@bot.process_message
def antiflood(shared, chat, message):
    if 'users' not in shared:
        if os.path.isfile('data.yml'):
            shared['users'] = yaml.load(open('data.yml'), Loader=yaml.FullLoader).get('users')
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
                    users[sender_id] = {'messages': 1, 'starttime': currentmillis, 'bloccato': 0}
                    saveusers(users)
                    shared['users'] = users
                elif rmessages > antiflood_config["messaggi"]:
                    # mute the user
                    with chat.permissions(message.sender.id) as perms:
                        perms.send_messages = False  # Restrict user forever
                        perms.save()
                    # this is the captcha
                    btns = generate_captcha_buttons()
                    emoji = random.choice(list(emojis))

                    user['bloccato'] = 1
                    user['emoji'] = emoji
                    user['errori'] = 0
                    user['messages'] = 0
                    saveusers(users)
                    shared['users'] = users

                    chat.send("@" + message.sender.username + " clicca *" + emojis[emoji]["description"]
                              + "* per risolvere il captcha. *Errori*: " + str(user['errori']), attach=btns)

            user['messages'] += 1
            saveusers(users)
            shared['users'] = users
        else:
            users[message.sender.id] = {'messages': 1, 'starttime': currentmillis, 'bloccato': 0}
            saveusers(users)
            shared['users'] = users


# captcha callback
@bot.callback("captcha")
def captcha_callback(shared, query, data, chat, message):
    if 'users' not in shared:
        if os.path.isfile('data.yml'):
            shared['users'] = yaml.load(open('data.yml'), Loader=yaml.FullLoader).get('users')
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
        else:
            user['errori'] += 1
            saveusers(users)
            shared['users'] = users
            if user['errori'] >= 2:
                message.edit("@" + query.sender.username +
                             " ha sbagliato due volte il captcha ed è stato bloccato per sempre", syntax='plain')
            else:
                message.edit("@" + query.sender.username + " clicca *" + emojis[user['emoji']]["description"]
                             + "* per risolvere il captcha. *Errori*: " + str(user['errori']), attach=generate_captcha_buttons())


# generate captcha buttons
def generate_captcha_buttons():
    btns = botogram.Buttons()
    tempemojis = emojis
    for i in range(3):
        rkey = random.choice(list(tempemojis))
        btns[i].callback(emojis[rkey]["emoji"], "captcha", rkey)
        tempemojis = removekey(tempemojis, rkey)

    return btns


# remove key from dictionary without really changing it (used to select 3 different random emojis)
def removekey(d, key):
    newdict = dict(d)
    del newdict[key]
    return newdict


def saveusers(users):
    with open('data.yml', 'w') as file:
        yaml.dump({'users': users}, file)


if __name__ == "__main__":
    bot.run()
