import sqlite3

new_db = sqlite3.connect("pg-13_NEW.db")

# User scores
new_db.execute(
    "CREATE TABLE scores(guild INT, user INT, score INT, UNIQUE(guild, user))"
)

scores = sqlite3.connect("databases/scores.db")
scores.row_factory = sqlite3.Row
score_tables = scores.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
for table in score_tables.fetchall():
    guild_id = table["name"][6:]
    guild_scores = scores.execute(f"SELECT * FROM {table['name']}")
    for row in guild_scores:
        new_db.execute(
            "INSERT INTO scores VALUES(?, ?, ?)",
            (guild_id, row["user"], row["cumulative"]),
        )
print("User scores successfully migrated")

# Daily bonuses
new_db.execute(
    "CREATE TABLE channel_bonuses(channel INT, guild INT, points INT, attachment BOOLEAN, UNIQUE(channel, guild))"
)
new_db.execute(
    "CREATE TABLE IF NOT EXISTS channel_claims"
    "(channel INT, guild INT, user INT, UNIQUE(channel, user))"
)
new_db.execute(
    "CREATE TABLE IF NOT EXISTS daily_claims"
    "(guild INT, user INT, UNIQUE(guild, user))"
)

dailies = sqlite3.connect("databases/dailies.db")
dailies.row_factory = sqlite3.Row

daily_tables = dailies.execute(
    "SELECT name FROM sqlite_master WHERE type = 'table'"
).fetchall()

# Used to determine channel/guild associations
channel_guilds = dict()

# Guild tables have to be migrated first
for guild_table in filter(
    lambda table: table["name"].startswith("guild_"), daily_tables
):
    guild_id = table["name"][6:]
    guild_bonuses = dailies.execute(f"SELECT * FROM {table['name']}")
    for row in guild_bonuses.fetchall():
        new_db.execute(
            "INSERT INTO channel_bonuses VALUES(?, ?, ?, ?) ON CONFLICT(channel, guild) DO NOTHING",
            (
                row["channel"],
                guild_id,
                row["bonus"],
                row["attachment"],
            ),
        )
        channel_guilds[row["channel"]] = guild_id

for table in filter(lambda table: not table["name"].startswith("guild_"), daily_tables):
    table_contents = dailies.execute(f"SELECT * FROM {table['name']}")

    # Channel bonus claims
    # TODO: Check if this actually works when they are present
    if table["name"].startswith("channel_"):
        channel_id = int(table["name"][8:])
        for row in table_contents.fetchall():
            new_db.execute(
                "INSERT INTO channel_claims VALUES(?, ?, ?)",
                (channel_id, channel_guilds[channel_id], row["user"]),
            )

    # `/daily claim` claims
    elif table["name"].startswith("bonus_"):
        guild_id = table["name"][6:]
        for row in table_contents.fetchall():
            new_db.execute(
                "INSERT INTO daily_claims VALUES(?, ?)", (guild_id, row["user"])
            )

    else:
        print(f"Unknown table: {table['name']}")

print("Daily bonuses/claims successfully migrated")
dailies.close()
