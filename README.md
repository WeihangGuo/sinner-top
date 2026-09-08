# sinner-top

A terminal GPU monitor for Slurm clusters, with running and pending jobs side by side.

- Fits the terminal or tmux pane and handles resizing.
- Groups jobs by user and sorts them by earliest expected finish.
- Includes individual job-array tasks and highlights your own jobs.
- Discovers GPU resource types from Slurm, starting with H200 when available.
- Shows pending start estimates and independent scroll positions for each pane and GPU type.
- Ranks accounts and their users by historical GPU-hours and current GPU use in two panes.
- Gives the top three medals, ASCII meme portraits, animated effects, and gold/silver/bronze colors.
- Uses Python's standard library; no pip packages are needed.

## Install or update

Run this on your cluster login node:

```sh
curl -LsSf https://raw.githubusercontent.com/WeihangGuo/sinner-top/main/install.sh | sh
```

The installer writes to `~/.local/bin/sinner-top` and does not require `sudo`.
Once installed, update directly with:

```sh
sinner-top update
```

This downloads the latest script from this repository's `main` branch, checks
its Python syntax, and atomically replaces the executable you invoked. It works
with custom installation paths and follows symlinks to the actual script. No
Slurm queries are needed. An identical download reports that you are already
up to date; a failed download or validation leaves the previous version intact.
`SINNER_TOP_VERSION` can select a tag or commit, as with the installer.

For older versions without the `update` command, run the curl installer again.

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
- `sacct` and accessible Slurm accounting records for historical GPU-hours.
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
| Left / `h` | Select Running, or historical usage in rankings |
| Right / `l` | Select Pending, or current usage in rankings |
| Up / `k` | Scroll up 5 lines |
| Down / `j` | Scroll down 5 lines |
| Tab | Switch panes |
| Page Up / Ctrl+U | Scroll one page up |
| Page Down / Ctrl+D | Scroll one page down |
| Home | Scroll to the top |
| End / `G` | Scroll to the bottom |
| `[` | Previous GPU type or rankings view |
| `]` / `g` | Next GPU type or rankings view |
| Number keys shown in the footer | Select a GPU type directly |
| `0` / `a` | Open account rankings; press again to return to the previous GPU view |
| `e` | Pause/resume podium animation in rankings |
| `m` | Toggle large meme portraits / compact badges in rankings |
| `r` | Refresh now, including history when rankings are open |
| `q` / Ctrl+C | Quit |

When present, `1` selects H100 and `2` selects H200. Other discovered GPU types
get additional number shortcuts. All types remain reachable with `[` and `]`,
including when there are more types than available number keys.
The final footer entry, `0:RANK`, opens the account ranking view; it also follows
the last GPU type when cycling with `[` / `]` / `g`.

Your rows use a colored background, or reverse video when colors are disabled.
The interface honors `NO_COLOR`; use `--color always` to enable colors explicitly.

Running jobs' remaining time is **green** at one hour or less, **yellow** above
one hour through six hours, and **red** above six hours. Unknown remaining
time is dimmed. Colors follow the live countdown, including when a job crosses
a threshold between Slurm refreshes. Your own job rows keep their highlight;
the time text uses the terminal background for contrast.

## Account and user rankings

Press `0` to open two leaderboards side by side:

- **Left — ALL-TIME GPU HOURS:** cumulative GPU allocation time, computed as
  GPU count × elapsed hours. Four GPUs allocated for two hours add eight GPU-hours.
- **Right — CURRENT GPU USE:** the number of GPUs currently allocated to running
  and completing jobs, refreshed with the live job list.

Each pane ranks accounts highest first, then ranks users within each account.
Ties are ordered alphabetically. Both include all GPU types, with type breakdowns
for accounts and users using multiple types. Usage under different accounts is
attributed to the account on each job. Every GPU counts equally; these totals
measure allocated resources, not GPU kernel activity, CPU time, or relative GPU
performance.

The first three accounts receive 🥇/🥈/🥉, gold/silver/bronze colors, and ASCII
meme portraits surrounded by moving beams and sparks. The first three users in each
account receive medals and animated accents. Effects update five times per
second without moving the data rows; press `e` to pause/resume them. Your own
user rows and accounts containing your usage keep their highlight. Press `m` to
switch to compact badges when you want more account and user rows on screen.
Portraits scale to the pane width, and their rows scroll with the account.

The first two portraits are terminal adaptations of the supplied
[character portrait](https://miro.medium.com/v2/resize:fit:482/format:webp/1*WlwVGfL5qrp7m6I2nfM8AA.png)
and [The Shining typography reference](https://www.artpie.co.uk/wp-content/uploads/2013/06/ascii-art-shining.jpg).
The third is an original ASCII grin. All portraits are embedded as text in the
script; no images, rendering libraries, or image downloads are needed at runtime.

Use Left/Right or `h`/`l` to select a pane, and Up/Down or `k`/`j` to scroll five
lines. Page Up/Down and Home/End also work. Each pane retains its scroll position,
and returning to a GPU view restores that view's pane and position.

History includes **all accounting records still retained and visible to you**,
queried from 1970 onward with `sacct`. The left pane shows the earliest GPU
allocation found and the report's timestamp. Deleted or inaccessible accounting
records cannot be recovered. Individual array tasks and distinct allocation
records with reused job IDs are included; job steps such as `.batch` and `.extern`
are excluded to avoid counting their parent's GPUs again. Pending requests add
no usage. Running allocations contribute their elapsed time at the history
query, so historical totals advance on the history refresh interval.

History loads in the background when the rankings are first opened and refreshes
every 15 minutes while that view is open. Navigation and live jobs remain responsive
during the query. A private aggregate cache under
`${XDG_CACHE_HOME:-~/.cache}/sinner-top/` makes subsequent launches faster; caches
are separated by login host, user and Slurm configuration. Press `r` in rankings
to refresh immediately. If accounting is unavailable, the left pane reports the
error and retains any previous successful report; current usage remains available.

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
