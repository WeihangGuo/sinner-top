# sinner-top

A terminal GPU monitor for Slurm clusters, with running and pending jobs side by side.

- Fits the terminal or tmux pane and handles resizing.
- Groups jobs by user and sorts them by earliest expected finish.
- Includes individual job-array tasks and highlights your own jobs.
- Discovers GPU resource types from Slurm, starting with H200 when available.
- Shows pending start estimates and independent scroll positions for each pane and GPU type.
- Ranks accounts and their users on separate pages for historical GPU-hours and current GPU use.
- Gives the all-time top three a dedicated podium page, clear ASCII memes, and replayable hero entrances.
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
| Left / `h` | Select Running; from either ranking page, open Live |
| Right / `l` | Select Pending; from either ranking page, open Total |
| Up / `k` | Scroll up 5 lines; at the top of a historical list, return to the podium |
| Down / `j` | On the podium, show rank #4 onward; in a list, scroll down 5 lines |
| Tab | Switch job panes, or switch between Live and Total |
| Page Up / Ctrl+U | Scroll one page up |
| Page Down / Ctrl+D | Scroll one page down |
| Home | Scroll to the top |
| End / `G` | Scroll to the bottom |
| `[` | Previous GPU type or rankings view |
| `]` / `g` | Next GPU type or rankings view |
| Number keys shown in the footer | Select a GPU type directly |
| `0` / `a` | Open Live rankings; press again to return to the previous GPU view |
| `t` | Open the all-time podium; press again to return to the previous GPU view |
| Enter | From the podium, open a full list of all accounts and users |
| `b` / Backspace | From a historical list, return to the podium and replay its entrance |
| `e` | Pause/resume the all-time podium animation |
| `m` | Toggle full memes / compact faces on the all-time podium |
| `r` | Refresh now, including history when Total is open |
| `q` / Ctrl+C | Quit |

When present, `1` selects H100 and `2` selects H200. Other discovered GPU types
get additional number shortcuts. All types remain reachable with `[` and `]`,
including when there are more types than available number keys.
The footer shows `0:LIVE` and `t:TOTAL`. Both ranking pages follow the last GPU
type when cycling with `[` / `]` / `g`.

Your rows use a colored background, or reverse video when colors are disabled.
The interface honors `NO_COLOR`; use `--color always` to enable colors explicitly.

Running jobs' remaining time is **green** at one hour or less, **yellow** above
one hour through six hours, and **red** above six hours. Unknown remaining
time is dimmed. Colors follow the live countdown, including when a job crosses
a threshold between Slurm refreshes. Your own job rows keep their highlight;
the time text uses the terminal background for contrast.

## Account and user rankings

The rankings have two separate pages:

- **`0:LIVE` — current GPU use:** a full-width account and user list showing GPUs
  allocated to running and completing jobs. It refreshes with the job list and
  has no ASCII portraits, entrance animations, or particle effects.
- **`t:TOTAL` — cumulative GPU-hours:** a dedicated podium for the three leading
  accounts, followed by a separate list for the remaining ranks. Four GPUs
  allocated for two hours add eight GPU-hours.

On the podium, **first place occupies the left half of the terminal**. Second
and third place split the right half vertically. Account totals, GPU-type usage,
and member usage are expanded by default inside each card. The layout adjusts
faces and detail columns to the available space; an unusually long user list
shows a continuation hint, and Enter opens every account and user in a full-width
list. Your account and user rows keep their highlight.
Compact values use `kh` for thousands of GPU-hours; `~` marks the rounded
per-type figures used in small cards. The full lists show the detailed totals.

The memes use original, clean line art: a GPU goblin ("More! More!") for first
place, a sunglasses face ("Deal with it") for second, and a coffee-holding dog
("This is fine") for third. The winner's account name appears in large ASCII
letters below its meme. Longer names use narrower letters or wrap; very small
panes fall back to a compact name label. Each meme enters
from a different direction, with staggered arrivals and a brief landing burst.
Faces and the account lettering use seven shades within each gold, silver, or
copper palette, with offset shadows, lit edges, and a travelling highlight.
After the entrance, the faces stay still while layered light fans, comet trails,
four-point star flares, and expanding halos move around them. Frame edges carry
moving highlights too. Terminals with fewer colors use dim and bold shades as
a fallback. Every return to the podium replays the entrance; routine data refreshes
and resizing do not. The animation waits for the first history report and never
blocks keyboard input. `e` pauses/resumes it; `m` switches to compact faces.
No image downloads, fonts, or rendering libraries are required by the script.

Press **Down / `j`** on the podium to open the next page, starting at **rank #4**.
The remaining accounts and their users are expanded there by default. In lists,
Up/Down or `k`/`j` scroll five lines, and Page Up/Down and Home/End work normally.
Press `b` to return to the podium; Up at the top of a historical list also returns.
Enter on the podium opens the full list starting with rank #1, including any
members that do not fit inside the podium cards. Live and historical lists have
separate scroll positions. Returning to a GPU view restores its pane and position.

Both rankings combine all GPU types. Accounts and users within each account
are sorted highest first, with alphabetical tie-breaking. Every GPU counts
equally; usage is attributed to the account on each job. These totals measure
allocated resources, not GPU kernel activity, CPU time, or relative performance.
Account/user lists retain 🥇/🥈/🥉 medals, and the podium uses gold/silver/bronze
colors. Names, totals, and user details remain visible during the entrance.

History includes **all accounting records still retained and visible to you**,
queried from 1970 onward with `sacct`. The Total page shows the earliest GPU
allocation found and the report's timestamp. Deleted or inaccessible accounting
records cannot be recovered. Individual array tasks and distinct allocation
records with reused job IDs are included; job steps such as `.batch` and `.extern`
are excluded to avoid counting their parent's GPUs again. Pending requests add
no usage. Running allocations contribute their elapsed time at the history
query, so historical totals advance on the history refresh interval.

History loads in the background when Total is first opened and refreshes
every 15 minutes while that view is open. Navigation and live jobs remain responsive
during the query. A private aggregate cache under
`${XDG_CACHE_HOME:-~/.cache}/sinner-top/` makes subsequent launches faster; caches
are separated by login host, user and Slurm configuration. Press `r` in Total
to refresh immediately. If accounting is unavailable, the page reports the
error and retains any previous successful report; Live remains available.

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
