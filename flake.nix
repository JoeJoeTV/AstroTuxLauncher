{
  description = "Nix flake for AstroTuxLauncher, a dedicated ASTRONEER server launcher for Linux.";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    pyproject-nix = {
      url = "github:nix-community/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      pyproject-nix,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        # fetch AstroTuxLauncher itself from github
        astroTuxSrc = pkgs.fetchFromGitHub {
          owner = "JoeJoeTV";
          repo = "AstroTuxLauncher";
          rev = "1.1.11";
          hash = "sha256-O9ZMwDioP848BXfZaUs/Bp0MyxK8t7ixI+7eAa7xXsc=";
        };
        # custom package for pansi
        pansiCustom = pkgs.python3Packages.buildPythonPackage rec {
          pname = "pansi";
          version = "2020.7.3";
          format = "setuptools";

          src = pkgs.fetchPypi {
            inherit pname version;
            hash = "sha256-vRgtUEUo+HBgGssCgq3tQRrQCgFIQnsOU6EhYvTnTc8=";
          };

          meta = with pkgs.lib; {
            description = "Text mode rendering library";
            homepage = "https://github.com/technige/pansi";
            license = licenses.asl20;
          };
        };
        # python environment
        astroTuxLauncherEnv = pkgs.python3.withPackages (
          p: with p; [
            alive-progress
            chardet
            colorlog
            dataclasses-json
            ipy
            packaging
            pansiCustom
            pathvalidate
            psutil
            requests
            tomli
            tomli-w
          ]
        );
        # everything needed to run the server that isn't python
        pack = [
          pkgs.wineWowPackages.staging
          pkgs.dotnet-sdk_8
          pkgs.depotdownloader
	  pkgs.winetricks
	  pkgs.gnutls
        ];
      in
      {
        packages = {
          default = self.packages.${system}.AstroTuxLauncher;
          AstroTuxLauncher = pkgs.python3Packages.buildPythonApplication rec {
            pname = "AstroTuxLauncher";
            version = "1.1.11";
            src = astroTuxSrc;
            format = "other";
            nativeBuildInputs = [
              astroTuxLauncherEnv
              pkgs.makeWrapper
            ];
            dontBuild = true;
            installPhase = ''
              install -d $out/libexec/${pname}
              cp -r ./* $out/libexec/${pname}/
              install -d $out/bin

              # bash script to move everything to .local/share/AstroTuxLauncher/                
              cat << EOF > $out/bin/run-helper
              #!${pkgs.bash}/bin/bash
              set -euo pipefail
              REAL_HOME=\$(getent passwd \$(whoami) | cut -d: -f6)
              DATA_DIR="\''${XDG_DATA_HOME:-\$REAL_HOME/.local/share}/AstroTuxLauncher"
              mkdir -p "\$DATA_DIR"
              cd "\$DATA_DIR"
              cp -rf $out/libexec/${pname}/* .
              ${astroTuxLauncherEnv.interpreter} ./AstroTuxLauncher.py install -d ${pkgs.depotdownloader}/bin/DepotDownloader
              exec ${astroTuxLauncherEnv.interpreter} ./AstroTuxLauncher.py start
              EOF
              chmod +x $out/bin/run-helper

              # install and run server command wrapper
              makeWrapper $out/bin/run-helper $out/bin/AstroTuxLauncher \
                --prefix PATH : ${pkgs.lib.makeBinPath pack}
            '';

            meta = with pkgs.lib; {
              description = "Fixes AstroTuxLauncher for NixOS so you can run a dedicated ASTRONEER server.";
              homepage = "https://github.com/JoeJoeTV/AstroTuxLauncher";
              license = licenses.gpl3Only;
              platforms = platforms.x86_64;
              mainProgram = "AstroTuxLauncher";
            };
          };
        };
      }
    );
}
