{ pkgs ? import <unstable> { } }:

pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    python39Full
    python39Packages.pip
    python39Packages.discordpy
    python39Packages.toml

    # TODO: Figure out how to install discord-py-slash-command

    # For formatting
    python39Packages.black
  ];
}
