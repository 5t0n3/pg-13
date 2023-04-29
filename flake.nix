{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
  };

  outputs = {
    self,
    nixpkgs,
    utils,
    flake-compat,
  }:
    utils.lib.eachSystem ["x86_64-linux" "aarch64-linux" "i686-linux"]
    (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      packages.pg-13 = pkgs.poetry2nix.mkPoetryApplication {
        projectDir = ./.;
        python = pkgs.python310;

        # TODO: figure out why this broke
        overrides = [
          pkgs.poetry2nix.defaultPoetryOverrides
          (final: prev: {
            systemd-python = prev.systemd-python.overridePythonAttrs (old: {
              buildInputs = old.buildInputs ++ [pkgs.python310Packages.setuptools];
            });
            discord-py = prev.discord-py.overridePythonAttrs (old: {
              buildInputs = old.buildInputs ++ [pkgs.python310Packages.setuptools];
            });
          })
        ];
      };

      devShells.default = pkgs.mkShell {
        packages = [self.packages.${system}.pg-13 pkgs.black pkgs.python310Packages.python-lsp-server];
      };

      formatter = pkgs.alejandra;
    })
    // {
      nixosModules.default = {
        config,
        pkgs,
        lib,
        ...
      }:
        with lib; let
          cfg = config.services.pg-13;
        in {
          options.services.pg-13 = {
            enable = mkOption {
              type = types.bool;
              default = false;
              description = "Whether to start the PG-13 Discord bot on boot.";
            };

            configFile = mkOption {
              type = types.path;
              default = "/var/lib/pg-13/config.toml";
              description = "The path to the PG-13 bot configuration.";
            };
          };

          config = mkIf cfg.enable {
            users.groups.pg-13 = {};
            users.users.pg-13 = {
              isSystemUser = true;
              group = "pg-13";
              extraGroups = ["postgres"];
              home = "/var/lib/pg-13";
              createHome = true;
            };

            systemd.services.pg-13 = {
              enable = true;
              description = "the PG-13 point system bot";
              wants = ["network-online.target"];
              after = ["network-online.target" "postgresql.service"];
              wantedBy = ["multi-user.target"];

              serviceConfig = {
                User = "pg-13";
                WorkingDirectory = "/var/lib/pg-13";
                ExecStart = "${self.packages.${pkgs.system}.pg-13}/bin/pg-13";
                Environment = "CONFIG_PATH=${cfg.configFile}";
              };
            };

            services.postgresql = {
              enable = true;
              package = pkgs.postgresql_14;

              ensureDatabases = ["pg_13"];
              ensureUsers = [
                {
                  name = "pg-13";
                  ensurePermissions = {"DATABASE pg_13" = "ALL PRIVILEGES";};
                }
              ];
            };
          };
        };
    };
}
