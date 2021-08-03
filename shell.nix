{ pkgs ? import <nixpkgs> { } }:

let
  discord-py-slash-command = pkgs.python39Packages.buildPythonPackage rec {
    pname = "discord-py-slash-command";
    version = "2.4.0";

    src = pkgs.python39Packages.fetchPypi {
      inherit pname version;
      sha256 = "133g2bdi7h3kl3d6whs64pc5zs7g29kq8rw9ycpq0x2yjrgbp4sm";
    };

    buildInputs = with pkgs.python39Packages; [ aiohttp discordpy ];
  };
  customPython = pkgs.python39.withPackages
    (ps: [ discord-py-slash-command ps.discordpy ps.toml ps.aiosqlite ]);
in pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    customPython
    black # Formatting
    scc # Just for statistics
  ];
}
