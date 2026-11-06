mkdir -p ~/bin ~/.cleanup_logs
cat > ~/bin/cleanup_gui.py << 'PYEOF'
#!/data/data/com.termux/files/usr/bin/env python3
"""
cleanup_gui.py — Termux Space Reclaimer TUI
Usage: python3 ~/bin/cleanup_gui.py
No external dependencies. Uses stdlib curses.
"""

import curses
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

HOME = Path.home()
LOG_FILE = HOME / ".cleanup_logs" / "history.json"

# ─── Candidate Definitions ───────────────────────────────────────────────────

CANDIDATES: List[Tuple[str, str, str]] = [
    # (label, path, category)
    ("test-backup.tar.gz (2.7 GB test artifact)", "~/test-backup.tar.gz", "artifact"),
    ("Stale tech-ref-portal copy", "~/tech-ref-portal.stale", "duplicate"),
    ("Extracted Keystone copy", "~/keystone_extract", "duplicate"),
    ("Keystone downloadable mirror", "~/Keystone_Health_downloadable_files", "duplicate"),
    ("Duck-dev keystone sync mirror", "~/duck-dev/keystone-sync", "duplicate"),
    ("Chrombook Active_Projects (dup)", "~/Chrombook_crostini_repair_guide/Active_Projects", "duplicate"),
    ("ez_termux_backup Active_Projects (dup)", "~/ez_termux_backup_flashdrive/Active_Projects", "duplicate"),
    ("tech-ref-portal node_modules", "~/tech-ref-portal/node_modules", "reinstallable"),
    ("capyreader node_modules", "~/capyreader/node_modules", "reinstallable"),
    ("Old keystone bundles (keep newest)", "~/backups", "rotation"),
    ("tmp/chrombook-scrub", "~/tmp/chrombook-scrub", "stale"),
    ("_quarantine (mangled entries)", "~/_quarantine", "stale"),
    ("pixel-terminal .tgz archives (3x)", "~/pixel-terminal-master.*.tgz", "artifact"),
    ("vid2gif-repo.tar.gz", "~/vid2gif-repo.tar.gz", "artifact"),
    ("animated-umbrella.tar.gz", "~/animated-umbrella.tar.gz", "artifact"),
    ("ctx_report_*.txt (old)", "~/ctx_report_*.txt", "artifact"),
    ("deployment_*.log (old)", "~/deployment_*.log", "artifact"),
    ("test_results_*.xml (old)", "~/test_results_*.xml", "artifact"),
    ("keystone_fix*.sh (old scripts)", "~/keystone_fix*.sh", "artifact"),
    ("keystone_fix*_*.txt (old logs)", "~/keystone_fix*_*.txt", "artifact"),
    ("keystone_verify*.sh (old)", "~/keystone_verify*.sh", "artifact"),
    ("keystone_verify*_*.txt (old logs)", "~/keystone_verify*_*.txt", "artifact"),
    ("keystone_triage*.sh (old)", "~/keystone_triage*.sh", "artifact"),
    ("keystone_triage*_*.txt (old logs)", "~/keystone_triage*_*.txt", "artifact"),
    ("tmu_probe*.sh / *.txt", "~/tmu_probe*", "artifact"),
    ("env_audit_*.txt (old)", "~/env_audit_*.txt", "artifact"),
    ("session_context.txt", "~/session_context.txt", "artifact"),
    ("report.json (stale)", "~/report.json", "artifact"),
]

# ─── Utilities ───────────────────────────────────────────────────────────────

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def get_size(path_str: str) -> int:
    """Get size in bytes. Supports glob patterns."""
    path_str = path_str.replace("~", str(HOME))
    if "*" in path_str:
        import glob
        total = 0
        for p in glob.glob(path_str):
            if os.path.isfile(p):
                total += os.path.getsize(p)
            elif os.path.isdir(p):
                total += sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, _, fns in os.walk(p)
                    for f in fns
                    if os.path.exists(os.path.join(dp, f))
                )
        return total
    p = Path(path_str)
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for dp, _, fns in os.walk(p):
        for f in fns:
            fp = os.path.join(dp, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def remove_path(path_str: str) -> int:
    """Remove path (or glob matches). Returns bytes freed."""
    path_str = path_str.replace("~", str(HOME))
    freed = 0
    if "*" in path_str:
        import glob
        for p in glob.glob(path_str):
            size = get_size(p)
            if os.path.isfile(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            freed += size
    else:
        p = Path(path_str)
        if p.exists():
            freed = get_size(path_str)
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                # Special case: backups — keep newest keystone bundle
                if p.name == "backups":
                    bundles = sorted(
                        p.glob("keystone_*.bundle"),
                        key=lambda x: x.stat().st_mtime,
                        reverse=True,
                    )
                    for b in bundles[1:]:
                        b.unlink()
                else:
                    shutil.rmtree(p, ignore_errors=True)
    return freed


def find_git_repos() -> List[Path]:
    """Find .git directories in home (depth <= 3)."""
    repos = []
    for i, (dirpath, dirnames, _) in enumerate(os.walk(HOME)):
        if i > 3:
            dirnames.clear()
            continue
        if ".git" in dirnames:
            repos.append(Path(dirpath))
            dirnames.remove(".git")
        # Skip node_modules, .git internals
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git")]
    return repos


def git_gc(repo: Path) -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git", "gc", "--aggressive", "--prune=now"],
            cwd=repo, capture_output=True, text=True, timeout=120,
        )
        return (r.returncode == 0, r.stderr.strip() or "OK")
    except Exception as e:
        return (False, str(e))


def load_history() -> list:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_history(entries: list):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(entries, indent=2))


# ─── TUI ─────────────────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    if hasattr(curses, "COLOR_PAIR"):
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)
        curses.init_pair(5, curses.COLOR_WHITE, -1)

    history = load_history()
    selected: set = set()
    scan_results: List[Tuple[str, str, int]] = []
    status_msg = "Welcome. Select an option below."
    mode = "menu"  # menu | scan | reclaim | git | history | confirm | result

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        if h < 10 or w < 40:
            stdscr.addstr(0, 0, "Terminal too small. Resize and restart.")
            stdscr.refresh()
            time.sleep(2)
            continue

        # ── Header ──
        header = "  TERMUX SPACE RECLAIMER  "
        stdscr.addstr(0, max(0, (w - len(header)) // 2), header, curses.A_BOLD | curses.color_pair(4))

        df = subprocess.run(["df", "-h", "/data/user/0"], capture_output=True, text=True)
        if df.returncode == 0:
            lines = df.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    disk_str = f"  Disk: {parts[1]}/{parts[0]} ({parts[4]})  Free: {parts[3]}"
                    stdscr.addstr(1, 0, disk_str, curses.color_pair(3 if int(parts[4].rstrip('%')) >= 85 else 1))

        # ── Status bar ──
        stdscr.addstr(2, 0, status_msg[:w-2], curses.A_DIM)

        # ── Body ──
        y = 4

        if mode == "menu":
            menu_items = [
                "[1] Scan & Reclaim (interactive)",
                "[2] Git GC (all repos)",
                "[3] Quick Wipe (artifacts > 100MB, no prompt)",
                "[4] History",
                "[5] Quit",
            ]
            stdscr.addstr(y, 2, "MAIN MENU", curses.A_BOLD | curses.color_pair(5))
            y += 1
            for i, item in enumerate(menu_items):
                stdscr.addstr(y + i, 4, item)
            y += len(menu_items) + 1
            stdscr.addstr(y, 2, "Press 1-5 to select. q to quit.", curses.A_DIM)

        elif mode == "scan":
            stdscr.addstr(y, 2, "SCAN RESULTS — press [a] to select all, [n] to toggle, [r] to reclaim, [b] to back", curses.A_DIM)
            y += 1
            stdscr.addstr(y, 2, f"{'SEL':<4} {'SIZE':>10}  PATH", curses.A_BOLD)
            y += 1
            total_size = 0
            sel_size = 0
            for i, (label, path, size) in enumerate(scan_results):
                if y >= h - 2:
                    break
                mark = "[x]" if i in selected else "[ ]"
                color = curses.color_pair(1) if i in selected else 0
                stdscr.addstr(y, 2, f"{mark:<4} {human_size(size):>10}  {label}  ({path})", color)
                total_size += size
                if i in selected:
                    sel_size += size
                y += 1
            y += 1
            if y < h - 1:
                stdscr.addstr(y, 2, f"Total: {human_size(total_size)}  |  Selected: {human_size(sel_size)}", curses.A_BOLD)

        elif mode == "git":
            stdscr.addstr(y, 2, "GIT GC — running on all repos. Press [b] to go back.", curses.A_DIM)
            y += 1
            repos = find_git_repos()
            if not repos:
                stdscr.addstr(y, 2, "No git repositories found.")
            else:
                stdscr.addstr(y, 2, f"Found {len(repos)} repos. Running git gc --aggressive...")
                y += 1
                for repo in repos[:15]:
                    if y >= h - 2:
                        break
                    rel = str(repo.relative_to(HOME))
                    stdscr.addstr(y, 2, f"  {rel:<50} ... ", curses.A_DIM)
                    ok, msg = git_gc(repo)
                    stdscr.addstr(y, 52, "OK" if ok else f"ERR: {msg[:30]}",
                                  curses.color_pair(1) if ok else curses.color_pair(2))
                    y += 1
                status_msg = f"Git GC complete on {len(repos)} repos."

        elif mode == "history":
            stdscr.addstr(y, 2, "RUN HISTORY", curses.A_BOLD | curses.color_pair(5))
            y += 1
            if not history:
                stdscr.addstr(y, 2, "No previous runs recorded.")
            else:
                for entry in history[-20:]:
                    if y >= h - 2:
                        break
                    stdscr.addstr(y, 2, f"  {entry['timestamp']}  freed={human_size(entry['freed'])}  items={entry['items']}")
                    y += 1

        elif mode == "confirm":
            stdscr.addstr(y, 2, "CONFIRM RECLAMATION", curses.A_BOLD | curses.color_pair(2))
            y += 1
            sel_total = sum(s for i, (_, _, s) in enumerate(scan_results) if i in selected)
            stdscr.addstr(y, 2, f"  You are about to permanently delete {len(selected)} items ({human_size(sel_total)}).")
            y += 1
            for i, (label, path, size) in enumerate(scan_results):
                if i in selected and y < h - 3:
                    stdscr.addstr(y, 4, f"  - {label} ({human_size(size)})")
                    y += 1
            y += 1
            stdscr.addstr(y, 2, "  [y] Confirm  [n] Cancel", curses.A_BOLD)

        elif mode == "result":
            stdscr.addstr(y, 2, "RESULT", curses.A_BOLD | curses.color_pair(1))
            y += 1
            for line in result_lines:
                if y < h - 2:
                    stdscr.addstr(y, 2, line)
                    y += 1
            y += 1
            stdscr.addstr(y, 2, "Press any key to return to menu.", curses.A_DIM)

        # ── Footer ──
        footer = " [q]uit  "
        stdscr.addstr(h - 1, 0, footer, curses.A_DIM)

        stdscr.refresh()

        # ── Input ──
        key = stdscr.getch()

        if mode == "menu":
            if key in (ord('1'), 261, 262):  # 1 or F1
                mode = "scan"
                selected.clear()
                status_msg = "Scanning..."
                stdscr.refresh()
                scan_results = []
                for label, path, cat in CANDIDATES:
                    sz = get_size(path)
                    scan_results.append((label, path, sz))
                status_msg = f"Scan complete. {len([s for s in scan_results if s[2] > 0])} items found."
            elif key in (ord('2'),):
                mode = "git"
                status_msg = "Running git gc..."
                time.sleep(0.1)
                # Actually run gc (blocking)
                repos = find_git_repos()
                count = 0
                for repo in repos:
                    git_gc(repo)
                    count += 1
                status_msg = f"Git GC complete on {count} repos."
                time.sleep(3)
                mode = "menu"
            elif key in (ord('3'),):
                # Quick wipe: artifacts > 100MB, no prompt
                freed = 0
                wiped = []
                for label, path, cat in CANDIDATES:
                    if cat == "artifact":
                        sz = get_size(path)
                        if sz > 100 * 1024 * 1024:
                            f = remove_path(path)
                            freed += f
                            wiped.append(f"{label} ({human_size(f)})")
                result_lines = [f"  Quick wipe complete. Freed: {human_size(freed)}"]
                for w_ in wiped:
                    result_lines.append(f"    {w_}")
                history.append({
                    "timestamp": datetime.now().isoformat(),
                    "freed": freed,
                    "items": len(wiped),
                    "mode": "quick_wipe",
                })
                save_history(history)
                mode = "result"
            elif key in (ord('4'),):
                mode = "history"
            elif key in (ord('5'), ord('q'), 27):
                break

        elif mode == "scan":
            if key in (ord('a'),):
                selected = set(i for i, (_, _, s) in enumerate(scan_results) if s > 0)
            elif key in (ord('n'),):
                # Toggle next unselected
                for i, (_, _, s) in enumerate(scan_results):
                    if s > 0 and i not in selected:
                        selected.add(i)
                        break
            elif key in (ord('r'), ord('R')):
                if not selected:
                    status_msg = "Nothing selected. Press [n] to select items."
                else:
                    mode = "confirm"
            elif key in (ord('b'), ord('q'), 27):
                mode = "menu"
                status_msg = "Back to menu."

        elif mode == "git":
            if key in (ord('b'), ord('q'), 27, curses.KEY_ENTER, 10):
                mode = "menu"

        elif mode == "history":
            if key in (ord('b'), ord('q'), 27, curses.KEY_ENTER, 10):
                mode = "menu"

        elif mode == "confirm":
            if key in (ord('y'), ord('Y')):
                freed = 0
                removed = 0
                errors = []
                for i in sorted(selected):
                    label, path, size = scan_results[i]
                    try:
                        f = remove_path(path)
                        freed += f
                        removed += 1
                    except Exception as e:
                        errors.append(f"{label}: {e}")
                result_lines = [
                    f"  Reclaimed: {human_size(freed)}",
                    f"  Items removed: {removed}",
                    "",
                ]
                if errors:
                    result_lines.append("  Errors:")
                    for e in errors:
                        result_lines.append(f"    {e}")
                result_lines.append("")
                df2 = subprocess.run(["df", "-h", "/data/user/0"], capture_output=True, text=True)
                if df2.returncode == 0:
                    lines2 = df2.stdout.strip().split("\n")
                    if len(lines2) >= 2:
                        p2 = lines2[1].split()
                        if len(p2) >= 5:
                            result_lines.append(f"  Disk now: {p2[1]}/{p2[0]} ({p2[4]})  Free: {p2[3]}")
                history.append({
                    "timestamp": datetime.now().isoformat(),
                    "freed": freed,
                    "items": removed,
                    "mode": "interactive",
                })
                save_history(history)
                mode = "result"
                status_msg = f"Reclaimed {human_size(freed)}."
            elif key in (ord('n'), ord('N'), 27):
                mode = "scan"
                status_msg = "Cancelled."

        elif mode == "result":
            if key != -1:
                mode = "menu"
                status_msg = "Back to menu."

        # Global quit
        if key in (ord('q'), 27) and mode not in ("confirm",):
            break

    stdscr.addstr(h - 1, 0, "  Goodbye.  ", curses.A_DIM)
    stdscr.refresh()
    time.sleep(1)


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\nInterrupted.")
PYEOF
chmod +x ~/bin/cleanup_gui.py
echo "✓ Installed: ~/bin/cleanup_gui.py"
echo "  Run with:  python3 ~/bin/cleanup_gui.py"
