import sqlite3
from flask import g, current_app
from config import DATABASE


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()
    if exception:
        current_app.logger.error(f"Context torn down due to error: {exception}")


def init_app(app):
    app.teardown_appcontext(close_db)