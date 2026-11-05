"""
Test helper: adds fake verified profiles to bot.db so you can try
/browse, Like, Skip, Report and matching with only ONE Telegram account.

Usage (from the verified_bot folder, with the venv active):
    python seed_test.py seed     add fake profiles (two of them already like you)
    python seed_test.py clean    remove all fake profiles again

Fake users have IDs 900000001-900000003. Never use this on a live database.
"""
import os
import sqlite3
import sys

DB_PATH = os.getenv("DB_PATH", "bot.db")
FAKE_IDS = (900000001, 900000002, 900000003)
FAKES = [
    (FAKE_IDS[0], "Test Aarav", 25, "Male", "Mumbai", "Fake profile #1. Likes you already."),
    (FAKE_IDS[1], "Test Priya", 24, "Female", "Pune", "Fake profile #2. Likes you already."),
    (FAKE_IDS[2], "Test Rohan", 27, "Male", "Nashik", "Fake profile #3. Has not liked you."),
]

con = sqlite3.connect(DB_PATH)
cmd = sys.argv[1] if len(sys.argv) > 1 else ""

if cmd == "seed":
    me = con.execute(
        "SELECT id, photo FROM users WHERE status='verified' AND id NOT IN (?,?,?) LIMIT 1", FAKE_IDS
    ).fetchone()
    if not me:
        sys.exit("No verified real user found. Finish your own verification first.")
    my_id, photo = me
    for uid, name, age, gender, city, bio in FAKES:
        con.execute(
            "INSERT OR REPLACE INTO users(id, username, name, age, gender, city, bio, photo, status) "
            "VALUES(?,?,?,?,?,?,?,?, 'verified')",
            (uid, None, name, age, gender, city, bio, photo),  # uses your photo for all fakes
        )
    for uid in FAKE_IDS[:2]:  # first two already like you -> instant match when you like back
        con.execute("INSERT OR REPLACE INTO swipes VALUES(?,?, 'like')", (uid, my_id))
    con.commit()
    print(f"Added {len(FAKES)} fake profiles. Send /browse to your bot (your ID: {my_id}).")

elif cmd == "clean":
    q = ",".join("?" * len(FAKE_IDS))
    con.execute(f"DELETE FROM users WHERE id IN ({q})", FAKE_IDS)
    con.execute(f"DELETE FROM swipes WHERE user_id IN ({q}) OR target IN ({q})", FAKE_IDS * 2)
    con.execute(f"DELETE FROM reports WHERE reporter IN ({q}) OR target IN ({q})", FAKE_IDS * 2)
    con.commit()
    print("Fake profiles removed.")

else:
    sys.exit(__doc__)
