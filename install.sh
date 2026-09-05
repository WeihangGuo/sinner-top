#!/bin/sh
# Install or update sinner-top without administrator privileges.
set -eu

main() {
    command -v curl >/dev/null 2>&1 || {
        printf '%s\n' 'Error: curl is required.' >&2
        exit 1
    }
    command -v python3 >/dev/null 2>&1 || {
        printf '%s\n' 'Error: Python 3.9 or newer is required.' >&2
        exit 1
    }
    python3 -c 'import sys; sys.version_info >= (3, 9) or sys.exit("Error: Python 3.9 or newer is required."); import curses'

    install_dir=${SINNER_TOP_INSTALL_DIR:-"$HOME/.local/bin"}
    version=${SINNER_TOP_VERSION:-main}
    base_url=${SINNER_TOP_BASE_URL:-"https://raw.githubusercontent.com/WeihangGuo/sinner-top/$version"}
    mkdir -p "$install_dir"
    download=$(mktemp "$install_dir/.sinner-top.XXXXXX")
    trap 'rm -f "$download"' 0
    trap 'exit 130' INT
    trap 'exit 143' HUP TERM

    curl -LsSf --connect-timeout 15 --max-time 120 --retry 2 \
        "$base_url/sinner-top" -o "$download"
    python3 -c 'import pathlib, sys; p = pathlib.Path(sys.argv[1]); compile(p.read_bytes(), "sinner-top", "exec")' "$download"
    chmod 755 "$download"
    mv -f "$download" "$install_dir/sinner-top"

    printf 'Installed: %s/sinner-top\n' "$install_dir"
    case ":${PATH:-}:" in
        *":$install_dir:"*) printf '%s\n' 'Run: sinner-top' ;;
        *)
            printf '%s\n' 'Add the installation directory to PATH in your shell configuration:'
            # Quote the directory for a POSIX-compatible shell, including spaces.
            quoted_dir=$(printf '%s' "$install_dir" | sed "s/'/'\\\\''/g")
            printf "  export PATH='%s':\"\$PATH\"\n" "$quoted_dir"
            ;;
    esac
    printf '%s\n' 'Run sinner-top on a Slurm host with squeue and scontrol available.'
}

main "$@"
