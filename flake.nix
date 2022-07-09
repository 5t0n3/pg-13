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

            buildInputs = [ pythonPkgs.aiohttp ];
          };
          botPython = pkgs.python310.withPackages
            (ps: [ packages.discordpy-dev ps.aiosqlite ps.toml ps.black ]);
        };

        devShells.default = pkgs.mkShell { packages = [ packages.botPython ]; };

        formatter = pkgs.nixfmt;
      });
}
