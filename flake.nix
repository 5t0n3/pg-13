{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
  };

  outputs = inputs @ {flake-parts, ...}:
    flake-parts.lib.mkFlake {inherit inputs;}
    ({moduleWithSystem, ...}: {
      systems = ["x86_64-linux" "aarch64-linux"];

      perSystem = {
        self',
        pkgs,
        system,
        ...
      }: {
        _module.args.pkgs = import inputs.nixpkgs {
          inherit system;
          overlays = [inputs.poetry2nix.overlays.default];
        };

        packages.pg-13 = pkgs.poetry2nix.mkPoetryApplication {
          projectDir = ./.;

          # TODO: remove these once build overrides are upstreamed
          overrides = pkgs.poetry2nix.overrides.withDefaults (
            final: prev: {
              # necessary due to python version being less than 3.11
              # broken as of https://github.com/aio-libs/yarl/commit/98eac52a7add38dd770f2baf95f0c4c5a62165e5#diff-50c86b7ed8ac2cf95bd48334961bf0530cdc77b5a56f852c5c61b89d735fd711R8-R9
              yarl = prev.yarl.overridePythonAttrs (old: {
                buildInputs = old.buildInputs ++ [pkgs.python310Packages.tomli];
              });
            }
          );

          # TODO: bump to 3.11
          python = pkgs.python310;
        };

        devShells.default = let
          pylsp = pkgs.python310Packages.python-lsp-server;
        in
          pkgs.mkShell {
            packages = [
              # pylsp & dependencies (apparently passing nested lists to packages still works?)
              pylsp
              pylsp.optional-dependencies.all

              # pg-13 dependencies for lsp purposes (?)
              self'.packages.pg-13.dependencyEnv
            ];
          };

        formatter = pkgs.alejandra;

        # this doesn't seem to be evaluated by default for some reason?
        checks.pg-13 = self'.packages.pg-13;
      };

      flake = {
        nixosModules.default = moduleWithSystem (
          # perSystem arguments (used for accessing pg-13 package)
          {self'}:
          # regular NixOS module arguments
          {
            config,
            pkgs,
            lib,
            ...
          }: let
            cfg = config.services.pg-13;
            inherit (lib) mkIf mkOption types optionalString;
          in {
            options.services.pg-13 = {
              enable = mkOption {
                type = types.bool;
                default = false;
                description = "Whether to start the PG-13 Discord bot on boot.";
              };

              configFile = mkOption {
                type = with types; nullOr path;
                default = null;
                example = "/var/lib/pg-13/config.toml";
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
                wants = ["network-online.target" "postgresql.service"];
                after = ["network-online.target" "postgresql.service"];
                wantedBy = ["multi-user.target"];

                serviceConfig = {
                  User = "pg-13";
                  WorkingDirectory = "/var/lib/pg-13";
                  ExecStart = "${self'.packages.pg-13}/bin/pg-13";
                  LoadCredential = "config.toml" + optionalString (cfg.configFile != null) ":${cfg.configFile}";
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
          }
        );
      };
    });
}
