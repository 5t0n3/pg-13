{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    discordpy-git = {
      url = "github:Rapptz/discord.py";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, utils, discordpy-git }:
    utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonPkgs = pkgs.python310.pkgs;
      in rec {
        packages = {
          discordpy-dev = pythonPkgs.buildPythonPackage rec {
            pname = "discord.py";
            version = "2.0.0a";
            src = discordpy-git;

            doCheck = false;

            propagatedBuildInputs = [ pythonPkgs.aiohttp ];
          };

          # botPython = pkgs.python310.withPackages
          #   (ps: [ packages.discordpy-dev ps.aiosqlite ps.toml ps.black ]);

          pg-13 = pythonPkgs.buildPythonPackage {
            pname = "pg13";
            version = "1.0.0";

            src = ./.;

            doCheck = false;

            buildInputs = with pythonPkgs; [ typing-extensions ];
            propagatedBuildInputs = with pythonPkgs; [
              # Direct dependencies
              aiosqlite
              toml
              packages.discordpy-dev
            ];
          };
        };

        nixosModules.pg13-service = { config }:
          with nixpkgs.lib;
          let cfg = config.services.pg13bot;
          in {
            options.services.pg13bot = {
              enable = mkOption {
                type = types.bool;
                default = false;
                description = "Whether to start the PG-13 Discord bot on boot.";
              };

              configFile = mkOption {
                type = with types; nullOr path;
                default = null;
                description = "The path to the PG-13 bot configuration.";
              };
            };

            config = mkIf cfg.enable {
              users.users.pg13 = {
                isSystemUser = true;
                home = /var/lib/pg13;
              };

              systemd.services.pg13bot = {
                enable = true;
                description = "the PG-13 point system bot";
                wants = [ "network-online.target" ];
                after = [ "network-online.target" ];
                wantedBy = [ "multi-user.target" ];

                serviceConfig = {
                  User = "pg13";
                  WorkingDirectory = /var/lib/pg13;
                  # TODO: Read config path from environment variable when running bot
                  ExecStart = (if cfg.configFile != null then
                    "CONFIG_PATH=${cfg.configFile} "
                  else
                    "") + "${packages.pg-13}/bin/pg-13";
                };
              };
            };
          };

        devShells.default = pkgs.mkShell { packages = [ packages.pg-13 ]; };

        formatter = pkgs.nixfmt;
      });
}
