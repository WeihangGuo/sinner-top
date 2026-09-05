# sinner-top

A terminal GPU monitor for Slurm clusters, with running and pending jobs side by side.

- Fits the terminal or tmux pane and handles resizing.
- Groups jobs by user and sorts them by earliest expected finish.
- Includes individual job-array tasks and highlights your own jobs.
- Discovers GPU resource types from Slurm, starting with H200 when available.
- Shows pending start estimates and independent scroll positions for each pane and GPU type.
- Uses Python's standard library; no pip packages are needed.

## Install or update

Run this on your cluster login node:

```sh
curl -LsSf https://raw.githubusercontent.com/WeihangGuo/sinner-top/main/install.sh | sh
```

The installer writes to `~/.local/bin/sinner-top` and does not require `sudo`.
Run the same command again to update. A failed download or syntax check leaves
the previous installation intact.

If `~/.local/bin` is not in your `PATH`, add this line to `~/.bashrc` or `~/.zshrc`
and open a new terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

To choose another installation directory:

```sh
curl -LsSf https://raw.githubusercontent.com/WeihangGuo/sinner-top/main/install.sh \
  | SINNER_TOP_INSTALL_DIR="$HOME/bin" sh
```

To install the script from a particular Git commit or tag, set
`SINNER_TOP_VERSION` on the `sh` side of the pipeline.

## Requirements

- Python 3.9 or newer with the `curses` module.
- A Slurm environment with `squeue` and `scontrol` in `PATH`.
- A terminal for the interactive interface. Piped output uses a printable snapshot.
- `curl` for the installer.

The monitor only queries Slurm; it does not submit, cancel, or modify jobs.
The displayed jobs depend on the current user's Slurm visibility permissions.

## Run

```sh
sinner-top
sinner-top --gpu h100
sinner-top --gpu 24gb
sinner-top --interval 10
sinner-top --show-ids
sinner-top --once
sinner-top --once --max-jobs 0
```

`--gpu TYPE` accepts the resource type configured by your cluster. If H200 is
unavailable, the interactive interface selects the first discovered type.
All array tasks are available by scrolling in the interactive interface.
`--once` shows up to five jobs per user by default; `--max-jobs 0` shows all.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| Left / `h` | Select Running |
| Right / `l` | Select Pending |
| Up / `k` | Scroll up |
| Down / `j` | Scroll down |
| Tab | Switch panes |
| Page Up / Ctrl+U | Scroll one page up |
| Page Down / Ctrl+D | Scroll one page down |
| Home | Scroll to the top |
| End / `G` | Scroll to the bottom |
| `[` | Previous GPU type |
| `]` / `g` | Next GPU type |
| Number keys shown in the footer | Select a GPU type directly |
| `r` | Refresh now |
| `q` / Ctrl+C | Quit |

When present, `1` selects H100 and `2` selects H200. Other discovered GPU types
get additional number shortcuts. All types remain reachable with `[` and `]`,
including when there are more types than available number keys.

Your rows use a colored background, or reverse video when colors are disabled.
The interface honors `NO_COLOR`; use `--color always` to enable colors explicitly.

## Reading the display

- **idle X/Y**: currently unallocated GPUs on schedulable nodes / all configured GPUs.
- **active**: GPU capacity on schedulable nodes, including both occupied and idle GPUs.
- **User GPU totals**: GPUs allocated to that user's running jobs or requested by
  that user's pending jobs, including each array task. Pending totals are queue
  demand, not a claim that all requested GPUs will be allocated at once.
- **end in**: time until the job's Slurm end-time limit, rather than a prediction
  of when the application will finish its work.
- **start in ~…**: Slurm's estimated start countdown. Estimates may change.
  `start unknown` means Slurm has not supplied an estimate; `start overdue`
  means its current estimate has passed while the job is still pending.
- **ANY**: jobs requesting GPUs without specifying a type. Running jobs are
  assigned to their actual GPU types when allocation details are available.

Existing jobs can keep using GPUs on a draining node. These allocations appear
in the running list even though the node's capacity is excluded from `active`.
If a refresh fails, the interface keeps the last successful snapshot and shows
the error at the bottom while continuing to accept keyboard input.

## Install from a checkout

```sh
git clone https://github.com/WeihangGuo/sinner-top.git
cd sinner-top
mkdir -p "$HOME/.local/bin"
install -m 755 sinner-top "$HOME/.local/bin/sinner-top"
```

## Tests

The tests use synthetic Slurm data and local installer fixtures; no cluster
access or network connection is needed.

```sh
python3 -B -m unittest discover -s tests -v
sh -n install.sh
```

## Uninstall

```sh
rm "$HOME/.local/bin/sinner-top"
```

If you chose a custom installation directory, remove `sinner-top` there instead.
