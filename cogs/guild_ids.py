import toml

# Default to registering commands in all guilds with a provided config
GUILD_IDS = list(map(int, toml.load("config.toml")["guilds"]))
