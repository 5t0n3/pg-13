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
          discordpy-dev = pythonPkgs.buildPythonPackage {
            pname = "discord.py";
            version = "2.0.0a";
            src = discordpy-git;

            doCheck = false;

            propagatedBuildInputs = [ pythonPkgs.aiohttp ];
          };

          pg-13 = pythonPkgs.buildPythonPackage {
            pname = "pg13";
            version = "1.0.0";

            src = ./.;

            doCheck = false;

            buildInputs = with pythonPkgs; [ typing-extensions ];
            propagatedBuildInputs = with pythonPkgs; [
              aiosqlite
              systemd
              toml
              packages.discordpy-dev
            ];
          };
        };

        devShells.default = pkgs.mkShell { packages = [ packages.pg-13 pkgs.black ]; };

        formatter = pkgs.nixfmt;

        nixosModules.default = { config, ... }:
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
                description = "The path to the PG-13 bot configuration (defaults to config.toml in the working directory).";
              };
            };

            config = mkIf cfg.enable {
              users.groups.pg-13 = { };
              users.users.pg-13 = {
                isSystemUser = true;
                group = "pg-13";
                home = "/var/lib/pg-13";
                createHome = true;
              };

              systemd.services.pg-13 = {
                enable = true;
                description = "the PG-13 point system bot";
                wants = [ "network-online.target" ];
                after = [ "network-online.target" ];
                wantedBy = [ "multi-user.target" ];

                serviceConfig = {
                  User = "pg-13";
                  WorkingDirectory = "/var/lib/pg-13";
                  ExecStart = "${packages.pg-13}/bin/pg-13";
                } // (if cfg.configFile != null then {
                  Environment = "CONFIG_PATH=${cfg.configFile}";
                } else {});
              };
            };
          };
      });
}
