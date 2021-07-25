{ pkgs ? import <unstable> { } }:

pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    python39Full
    python39Packages.pip
    python39Packages.discordpy
    python39Packages.toml
    python39Packages.aiosqlite

    # For formatting
    python39Packages.black

    # Just for statistics
    scc
  ];
}
