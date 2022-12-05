# PG-13

[![built with nix](https://builtwithnix.org/badge.svg)](https://builtwithnix.org)

A Discord bot that keeps track of points from a variety of sources.

I don't expect this to be useful to anyone, but hey, if it is that's great :)

## Features

- **Score tracking** through server-specific leaderboards
- **Manual score management** when you want to ~~punish your enemies~~ reward
  specific users
- **Assignment of special roles** to the users with the most points
- **Daily point rewards** for both messages in configurable text channels and
  via a command
- **Game nights** with points awarded based on how long someone stays in a call
  for
- Something about the [**Door to Darkness**](pg13/cogs/door_to_darkness.py), if
  you so desire :)

## Configuration

An [example configuration](config.example.toml) is included in this repository
which shows the structure that PG-13 expects when running. If you are running
PG-13 without using the supplied NixOS module options, it expects a
`config.toml` file in the working directory, or wherever the `CONFIG_PATH`
environment variable points to, if applicable.

If you're using NixOS, something like [agenix](https://github.com/ryantm/agenix)
can be useful for managing your PG-13 configuration. Just set
`services.pg-13.configFile` to be the `path` attribute of the corresponding
secret.

## Installation

### NixOS with flakes (recommended)

Just add the following to your system configuration flake:

```nix
{
  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-<channel>";
  inputs.pg-13.url = "github:5t0n3/pg-13/v1.1.0";

  outputs = { self, nixpkgs, pg-13 }: {
    nixosConfigurations.yourhostname = nixpkgs.lib.nixosSystem {
      system = "<your system/architecture>";
      modules = [
        pg-13.nixosModules.default
        ({
          services.pg-13.enable = true;

          # optional but recommended
          # (defaults to /var/lib/pg-13/config.toml)
          # services.pg-13.configFile = "<path/to/your/config.toml>";
        })
      ];
    };
  };
}
```

### NixOS (no flakes)

Add the following to your system configuration:

```nix
{ pkgs, ... }:
let
  pg-13 = import (pkgs.fetchFromGitHub {
    owner = "5t0n3";
    repo = "pg-13";
    rev = "v1.1.0"; # or a commit hash
    sha256 = "<hash>"; # obtained using nix-prefetch-url
  });
in {
  imports = [ pg-13.nixosModules.default ];

  services.pg-13.enable = true;

  # optional but recommended
  # (defaults to /var/lib/pg-13/config.toml)
  # services.pg-13.configFile = "<path/to/your/config.toml>";
}
```

You can probably also add this repository as a channel, if you'd like.

### Nix on other Linux distributions

If you have a flakes-capable Nix on top of another Linux flavor, installation of
PG-13 is still pretty easy:

```
$ nix profile install github:5t0n3/pg-13/v1.1.0#pg-13
```

Without a flakes-capable Nix, you should be able to run the following to achieve
the same effect:

```
$ nix-env -f https://github.com/5t0n3/pg-13/tarball/v1.1.0 -iA packages.<your system>.pg-13
```

In both cases, you will have to install and set up PostgreSQL and systemd
separately, but Nix will manages all of PG-13's Python dependencies for you.

### Other operating systems (without Nix)

You'll need to install a few things in order to get PG-13 running on other
operating systems. Plenty of guides should be available online should you need
them.

- **Python** - I've only tested PG-13 with Python 3.9 and 3.10, but other
  versions could work
- [**poetry**](https://python-poetry.org/) - used for Python dependency
  management
- **PostgreSQL** - this bot expects database `pg_13` to exist as well as the
  user `pg-13` with full privileges to it
- **systemd** - used for logging (via journald); I recommend running the bot
  with a systemd service

After ensuring all of these are installed and set up properly and
[configuring the bot](#configuration), you should be able to run this bot using
the following command from wherever you cloned this repository to:

```
$ poetry run pg-13
```
