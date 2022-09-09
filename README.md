# PG-13 - the Discord point bot you'll never need

I don't expect this to be useful to anyone, but hey, if it is that's great :)

## Functionality

TODO

## Installation

If you're using NixOS, something like [agenix](https://github.com/ryantm/agenix)
can be useful for managing your PG-13 configuration. Just set
`services.pg-13.configFile` to be the `path` attribute of the corresponding
secret.

### NixOS with flakes (recommended)

Just add the following to your system configuration flake:

```nix
{
  inputs.pg-13.url = "github:5t0n3/pg-13";

  outputs = { self, nixpkgs, pg-13 }: {
    nixosConfigurations.yourhostname = nixpkgs.lib.nixosSystem {
      system = "<your system/architecture>";
      modules = [
        pg-13.nixosModules.default
        ({
          services.pg-13.enable = true;

          # optional but recommended
          # (defaults to /var/lib/pg-13/config.toml)
          # services.pg-13.configFile = <path/to/your/config.toml>;
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
    rev = "v1.0.0"; # or a commit hash
    sha256 = "<repository hash>"; # obtained using nix-prefetch-url
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

### Other operating systems

You'll need to install a few things in order to get PG-13 running on other
operating systems, namely PostgreSQL, Python (3.10+), and
[poetry](https://python-poetry.org/), a Python package manager. PG-13 also
depends on systemd, so if your operating system doesn't use it then you're out
of luck unfortunately. There might also be a couple more things to install, but
given that I use NixOS I don't know what they might be :)

On the Postgres side, PG-13 expects the `pg_13` database to exist and to have
all privileges in modifying it. When running the bot itself, the bot
configuration should either be placed in `config.toml` in the working directory
or supplied via the `CONFIG_PATH` environment variable. I'd recommend running
PG-13 as a systemd service, as that way you don't have to worry about manually
starting it up whenever the computer it's running on is restarted. You can look
at flake.nix for a good starting point for doing this.
