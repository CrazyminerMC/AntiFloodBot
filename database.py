import sqlite3
import time

import yaml


config = yaml.safe_load(open('config.yml'))


def get_connection():
    conn = None

    try:
        conn = sqlite3.connect(config["db_file"])
    except sqlite3.Error as e:
        print(e)

    return conn

def get_user(user_id):
    c = get_connection().cursor()
    query = 'SELECT * FROM users WHERE user_id = ?'
    params = (user_id,)

    c.execute(query, params)
    return c.fetchone()

def get_user_by_username(username):
    c = get_connection().cursor()
    query = 'SELECT * FROM users WHERE username = ?'
    params = (username,)

    c.execute(query, params)
    return c.fetchone()


def add_user(user_id, username):
    if not get_user(user_id):
        conn = get_connection()
        c = conn.cursor()
        query = 'INSERT INTO users(user_id, username) VALUES(?, ?)'
        params = (user_id, username)

        c.execute(query, params)
        conn.commit()
        return c.lastrowid

    return False


def remove_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    query = 'DELETE FROM users WHERE user_id = ?'
    params = (user_id,)

    c.execute(query, params)
    conn.commit()

    return c.lastrowid


def update_username(user):
    old_user = get_user(user.id)
    conn = get_connection()
    c = conn.cursor()

    if old_user[1] == user.username:
        return False

    query = 'UPDATE users SET username = ? WHERE user_id = ?'
    params = (user.username, user.id)

    c.execute(query, params)
    conn.commit()

    return c.lastrowid


def set_warning(user_id, warning):
    conn = get_connection()
    c = conn.cursor()
    query = 'UPDATE users SET warnings = ?, last_warn_time = ? WHERE user_id = ?'
    params = (warning, time.time(), user_id)

    c.execute(query, params)
    conn.commit()

    return c.lastrowid


connection = get_connection()
c = connection.cursor()

c.execute(
    """create table if not exists users
        (
            user_id int not null
                constraint users_pk
                    primary key,
            username varchar(255),
            warnings int default 0 not null,
            last_warn_time text
        )"""
)

connection.commit()
connection.close()
