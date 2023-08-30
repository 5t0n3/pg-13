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

## Configuration

An [example configuration](config.example.toml) is included in this repository
which shows the structure that PG-13 expects when running. The bot expects its
configuration to be supplied as a 
[systemd credential](https://systemd.io/CREDENTIALS/) with the name `config.toml`.
If the `services.pg-13.configFile` option is set, this is handled automatically;
otherwise you can set it up manually using something like the `SetCredential` 
service option.

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
  inputs.pg-13.url = "github:5t0n3/pg-13/v1.2.0";

  outputs = { self, nixpkgs, pg-13 }: {
    nixosConfigurations."<yourhostname>" = nixpkgs.lib.nixosSystem {
      system = "<your system/architecture>";
      modules = [
        pg-13.nixosModules.default
        ({
          services.pg-13.enable = true;

          # optional but recommended
          # automatically sets up the systemd credential expected by the bot
          # the config file only has to be readable by root, systemd handles
          # the rest of the permissions
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
    rev = "v1.2.0"; # or a commit hash
    sha256 = "<hash>"; # obtained using nix-prefetch-url or nix flake prefetch
  });
in {
  imports = [ pg-13.nixosModules.default ];

  services.pg-13.enable = true;

  # optional but recommended
  # automatically sets up the systemd credential expected by the bot
  # services.pg-13.configFile = "<path/to/your/config.toml>";
}
```

You can probably also add this repository as a channel, if you'd like. Then
something like this should work (althought I haven't tested it):

```nix
let pg-13 = import <pg-13>;
in {
  imports = [ pg-13.nixosModules.default ];

  # ...
}
```
