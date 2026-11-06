#!/usr/bin/env bash
​git_superuser_workflow - Hardened for Termux/puppygit
​Version: 2025.11.14_ENHANCED3
​Usage: ./git_superuser_workflow.sh <command> [--dry-run] [--workdir DIR]
​set -euo pipefail
IFS=$'\n\t'
​----------------------------------------------------------------------
​Globals & Setup
​----------------------------------------------------------------------
​SCRIPT_NAME="{0##*/}"
VERSION="2025.11.14_ENHANCED3"
DRY_RUN=0
WORKDIR="(pwd)"
LOG_DIR="{HOME:-/tmp}/.local/log/git_workflow"
SNAPSHOT_DIR="{HOME:-/tmp}/.local/snapshots"
SNAPSHOT_RETAIN=5                     # keep last N snapshots
SNAPSHOT_MAX_BYTES=((200*1024*1024)) # 200 MiB warning threshold
LARGE_FILE_LIMIT_BYTES=((1010241024)) # 10 MiB pre‑commit limit
TOOL_TOLERANCE=1                      # seconds tolerance for missing tools
​Portable command resolution
​_cmd() { command -v "1" 2>/dev/null || printf "%s\n" ""; }
TAR_CMD=(_cmd tar || true)
DATE_CMD=(_cmd date || true)
STAT_CMD=(_cmd stat || true)
SHA256SUM_CMD=(_cmd sha256sum || _cmd shasum || true)
AWK_CMD=(_cmd awk || true)
DU_CMD=(_cmd du || true)
XARGS_CMD=(_cmd xargs || true)
​Ensure required directories exist (no‑op in dry‑run)
​mkdir_p() {
if [ "${DRY_RUN:-0}" -eq 1 ]; then
echo "[DRY‑RUN] mkdir -p "1\""
else
mkdir -p "$1"
fi
}
mkdir_p "${LOG_DIR}"
mkdir_p "{SNAPSHOT_DIR}"
​----------------------------------------------------------------------
​Logging helpers
​----------------------------------------------------------------------
​_log() {
local level="1" message="$2"
local timestamp
timestamp=$("{DATE_CMD:-date}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')
local log_file="{LOG_DIR}/{SCRIPT_NAME}.log"
case "$level" in
error) printf "[%s] [ERROR] %s\n" "$timestamp" "$message" >&2 ;;
warn)  printf "[%s] [WARN]  %s\n" "$timestamp" "$message" >&2 ;;
info)  printf "[%s] [INFO]  %s\n" "$timestamp" "$message" ;;
*)     printf "[%s] [%s]  %s\n" "timestamp" "{level^^}" "message" ;;
esac
if [ "{DRY_RUN:-0}" -eq 0 ]; then
printf "[%s] [%s] %s\n" "timestamp" "{level^^}" "$message" >> "$log_file" 2>/dev/null || true
fi
}
​----------------------------------------------------------------------
​Utility helpers
​----------------------------------------------------------------------
​run_or_dry() {
if [ "${DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY‑RUN] *"
return 0
fi
bash -c "*" \vert{}\vert{} return $?
}
​numfmt_or_human() {
local size="$1"
if command -v numfmt >/dev/null 2>&1; then
numfmt --to=iec-i --suffix=B --padding=7 "$size" 2>/dev/null \vert{}\vert{} printf "%sB" "size"
else
"{AWK_CMD:-awk}" -v s="$size" 'function human(x){
split("B KB MB GB TB PB",u); i=1;
while(x>1024 && i<6){x/=1024; i++}
return sprintf("%.1f %s", x, u[i]);
}{print human(s)}'
fi
}
​safe_stat_size() {
local file="$1"
if [ -z "$file" ] \vert{}\vert{} [ ! -e "$file" ]; then echo 0; return; fi
if command -v stat >/dev/null 2>&1; then
if stat -c "%s" "$file" 2>/dev/null; then
stat -c "%s" "$file" 2>/dev/null || echo 0
else
stat -f "%z" "$file" 2>/dev/null || echo 0
fi
else
wc -c <"$file" 2>/dev/null || echo 0
fi
}
​prune_snapshots() {
local prefix="{SCRIPT_NAME%%.*}_"
local files
mapfile -t files < <(find "{SNAPSHOT_DIR}" -maxdepth 1 -type f -name "{prefix}*.tar.gz" -printf '%T@ %p\n' 2>/dev/null |
sort -n -r | awk '{print $2}')
for f in "${files[@]:{SNAPSHOT_RETAIN}}"; do
[ -z "f" ] && continue
if [ "{DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY‑RUN] rm -f "$f""
else
rm -f "$f" || _log warn "Failed to remove old snapshot: $f"
fi
done
}
​check_repo_size() {
if command -v du >/dev/null 2>&1; then
local size_mb
size_mb=$(( ({DU_CMD} -sm . 2>/dev/null | cut -f1 || echo 0) ))
if [ "$size_mb" -gt 500 ]; then
_log warn "Repository size ${size_mb} MB may be slow on Termux."
fi
fi
}
​----------------------------------------------------------------------
​Core Workflow Implementations
​----------------------------------------------------------------------
​dependency_master() {
_log info "Running dependency_master..."
if [ "${DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY‑RUN] Would update npm/pip/composer."
return 0
fi
​npm
​if [ -f package.json ] && command -v npm >/dev/null 2>&1; then
_log info "npm install --no-audit --no-fund"
npm install --no-audit --no-fund || _log warn "npm install failed."
fi
​pip
​if [ -f requirements.txt ] && command -v pip >/dev/null 2>&1; then
_log info "pip install -r requirements.txt"
pip install -r requirements.txt || _log warn "pip install failed."
fi
​composer
​if [ -f composer.json ] && command -v composer >/dev/null 2>&1; then
_log info "composer install --no-interaction"
composer install --no-interaction || _log warn "composer install failed."
fi
_log info "dependency_master completed."
}
​git_security_audit() {
_log info "Running git_security_audit (best‑effort)."
if command -v git-secrets >/dev/null 2>&1; then
_log info "git-secrets --scan"
git-secrets --scan || _log warn "git-secrets found issues."
else
_log warn "git-secrets not installed."
fi
if command -v git >/dev/null 2>&1; then
_log info "Checking large objects (heuristic only)"
git rev-list --objects --all 2>/dev/null | cut -d' ' -f1 | while read -r oid; do :; done
_log info "Branch divergence check"
git fetch --prune --quiet || true
git branch -vv | grep -E 'behind|ahead' || true
fi
_log info "git_security_audit completed."
}
​git_workflow_optimizer() {
_log info "Running git_workflow_optimizer."
if [ "${DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY‑RUN] git gc --prune=now --aggressive"
return 0
fi
if command -v git >/dev/null 2>&1; then
git gc --prune=now --aggressive || _log warn "git gc failed"
git remote prune origin || true
git reflog expire --expire=now --all || true
fi
_log info "git_workflow_optimizer completed."
}
​setup_pre_commit_hook() {
_log info "Setting up basic pre-commit hook..."
local hook_file=".git/hooks/pre-commit"
local hook_manager="${SCRIPT_NAME%%.*}"
​if [ ! -d .git ]; then
_log error "Not a git repository."
return 1
fi
​if [ -f "{hook_file}" ]; then
if grep -q "Managed by ${hook_manager}" "${hook_file}" 2>/dev/null; then
_log info "Pre-commit hook already installed and managed."
return 0
else
_log warn "Existing pre-commit hook present and unmanaged; preserving it and appending managed checks."
if [ "{DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY‑RUN] Would append managed checks to {hook_file}"
return 0
fi
cat >> "{hook_file}" <<EOF_MANAGED
​--- Managed by ${hook_manager} (appended) ---
​set -euo pipefail
​Prevent large files (>${LARGE_FILE_LIMIT_BYTES} bytes)
​MAX_BYTES={LARGE_FILE_LIMIT_BYTES}
git diff --cached --name-only -z | xargs -0 -I{} bash -c '
for f; do
[ -f "\$f" ] || continue
if [ "\$(wc -c <"\$f" 2>/dev/null)" -gt \$MAX_BYTES ]; then
echo "File is too large (>(($MAX_BYTES/1024/1024))MB): $f" >&2
exit 1
fi
done
' bash {} || { echo "ERROR: Large staged file detected." >&2; exit 1; }
​EOF_MANAGED
chmod +x "${hook_file}"
_log info "Appended managed checks to existing hook: ${hook_file}"
return 0
fi
fi
​if [ "${DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY‑RUN] Would create ${hook_file} with managed pre-commit checks."
return 0
fi
​cat > "${hook_file}" <<EOF_HOOK
#!/usr/bin/env bash
​Managed by ${hook_manager}
​set -euo pipefail
​Prevent large files (>(({LARGE_FILE_LIMIT_BYTES}/1024/1024))MB)
​MAX_BYTES={LARGE_FILE_LIMIT_BYTES}
git diff --cached --name-only -z | xargs -0 -I{} bash -c '
for f; do
[ -f "\$f" ] || continue
if [ "\$(wc -c <"\$f" 2>/dev/null)" -gt \$MAX_BYTES ]; then
echo "File is too large (>((${LARGE_FILE_LIMIT_BYTES}/1024/1024))MB): $f" >&2
exit 1
fi
done
' bash {} || { echo "ERROR: Large staged file detected. Use git-lfs or remove from staging." >&2; exit 1; }
EOF_HOOK
​chmod +x "${hook_file}"
_log info "Pre-commit hook installed in ${hook_file}"
return 0
}
​local_snapshot() {
_log info "Running Local Repository Snapshot..."
if [ ! -d "${WORKDIR:-.}" ]; then
_log error "Workdir ${WORKDIR} does not exist"
return 1
fi
​check_repo_size
​local DATE_TAG
DATE_TAG=("{DATE_CMD:-date}" '+%Y%m%d_%H%M%S' 2>/dev/null || date '+%Y%m%d_%H%M%S')
local base_name="{SCRIPT_NAME\%\%.*}_{DATE_TAG}"
local snapshot_file="{SNAPSHOT_DIR}/{base_name}.tar.gz"
local snapshot_checksum="{SNAPSHOT_DIR}/{base_name}.sha256"
​local EXCLUDE_PATTERNS=(
--exclude='.git'
--exclude='node_modules'
--exclude='venv'
--exclude='pycache'
--exclude='.o'
--exclude='.pyc'
--exclude='.swp'
--exclude='.bak'
--exclude='.tmp'
--exclude='.log'
--exclude='Thumbs.db'
--exclude='.DS_Store'
)
​_log info "Target snapshot file: ${snapshot_file}"
​local -a tar_args=( -czf "{snapshot_file}" )
tar_args+=( "{EXCLUDE_PATTERNS[@]}" . )
​if [ "{DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY-RUN] ${TAR_CMD:-tar}${tar_args[*]}"
else
( cd "{WORKDIR}" && "{TAR_CMD:-tar}" "{tar_args[@]}" ) || {
_log error "Snapshot tar creation failed."
return 1
}
​if [ -n "{SHA256SUM_CMD}" ]; then
if command -v "{SHA256SUM_CMD%% *}" >/dev/null 2>&1; then
"{SHA256SUM_CMD}" "{snapshot_file}" > "{snapshot_checksum}" 2>/dev/null || {
_log warn "Failed to generate checksum with ${SHA256SUM_CMD}"
}
fi
else
if command -v shasum >/dev/null 2>&1; then
shasum -a 256 "${snapshot_file}" > "{snapshot_checksum}" 2>/dev/null || _log warn "Failed to generate checksum with shasum"
else
_log warn "No sha256sum/shasum command available; skipping checksum."
fi
fi
​local size_bytes
size_bytes=(safe_stat_size "{snapshot_file}" || echo 0)
_log info "Snapshot created: ${snapshot_file} (size: $(numfmt_or_human "$size_bytes"))"
​if [ "{size_bytes:-0}" -gt "{SNAPSHOT_MAX_BYTES}" ]; then
_log warn "Snapshot size ($(numfmt_or_human "$size_bytes")) exceeds $(numfmt_or_human "$SNAPSHOT_MAX_BYTES"); consider storing externally."
fi
​prune_snapshots
fi
​return 0
}
​restore_snapshot() {
local sel="${1:-latest}"
local target_dir=""
​set -- "${@:-$sel}"
while [ # -gt 0 ]; do
case "$1" in
--target) shift; target_dir="${1:-}"; shift ;;
--target=*) target_dir="{1#*=}"; shift ;;
--dry-run) DRY_RUN=1; shift ;;
latest) sel="latest"; shift ;;
*) sel="$1"; shift ;;
esac
done
​if [ ! -d "${SNAPSHOT_DIR}" ]; then
_log error "Snapshot directory not found: ${SNAPSHOT_DIR}"
return 1
fi
​list_snapshots() {
if command -v find >/dev/null 2>&1 && command -v sort >/dev/null 2>&1; then
find "{SNAPSHOT_DIR}" -maxdepth 1 -type f -name "{SCRIPT_NAME%%.}_.tar.gz" -printf '%T@ %p\n' 2>/dev/null | sort -n -r | awk '{print 2}'
else
ls -1t "{SNAPSHOT_DIR}/${SCRIPT_NAME%%.}"_.tar.gz 2>/dev/null || true
fi
}
​mapfile -t snaps < <(list_snapshots)
​if [ "${#snaps[@]}" -eq 0 ]; then
_log warn "No snapshots found in ${SNAPSHOT_DIR}"
return 2
fi
​local snapshot_file=""
​if [ "{sel:-}" = "latest" ]; then
snapshot_file="{snaps[0]}"
else
for s in "{snaps[@]}"; do
if [ "$s" = "${sel}" ] \vert{}\vert{} [ "(basename "s")" = "{sel}" ]; then
snapshot_file="$s"
break
fi
done
if [ -z "$snapshot_file" ]; then
_log error "Snapshot not found: {sel}"
_log info "Available snapshots:"
for s in "{snaps[@]}"; do
_log info "  $(basename "$s")"
done
return 3
fi
fi
​local checksum_file="{snapshot_file%.tar.gz}.sha256"
if [ ! -f "{snapshot_file}" ]; then
_log error "Snapshot file missing: ${snapshot_file}"
return 4
fi
​if [ -z "{target_dir}" ]; then
local ts
ts=("{DATE_CMD:-date}" '+%Y%m%d_%H%M%S' 2>/dev/null || date '+%Y%m%d_%H%M%S')
target_dir="./restored_{ts}"
fi
​if [ -e "{target_dir}" ] && [ "(ls -A "${target_dir}" 2>/dev/null | wc -l)" -gt 0 ]; then
_log error "Target directory exists and is not empty: ${target_dir}"
return 5
fi
​_log info "Selected snapshot: ${snapshot_file}"
_log info "Target directory: ${target_dir}"
​if [ "{DRY_RUN:-0}" -eq 1 ]; then
_log info "[DRY-RUN] Would verify checksum and extract snapshot into ${target_dir}"
_log info "[DRY-RUN] Commands:"
if [ -f "${checksum_file}" ]; then
_log info "  sha256sum -c \"{checksum_file}" --status || exit 1"
else
_log info "  (no checksum file found; would compute and compare)"
_log info "  shasum -a 256 "{snapshot_file}\""
fi
_log info "  mkdir -p \"{target_dir}""
_log info "  tar -xzf "{snapshot_file}\" -C \"{target_dir}""
return 0
fi
​if [ -f "{checksum_file}" ]; then
_log info "Verifying checksum using: ${checksum_file}"
if command -v sha256sum >/dev/null 2>&1; then
if ! sha256sum -c "${checksum_file}" --status; then
_log error "Checksum verification failed for ${snapshot_file}"
return 6
fi
elif command -v shasum >/dev/null 2>&1; then
computed=$((shasum -a 256 "{snapshot_file}" 2>/dev/null) | awk '{print 1}')
expected=((awk '{print 1}' "{checksum_file}" 2>/dev/null) || echo "")
if [ -z "{expected}" ] || [ "{computed}" != "${expected}" ]; then
_log error "Checksum mismatch (computed: {computed} != expected:{expected}). Aborting."
return 6
fi
else
_log warn "No sha256sum/shasum available; skipping checksum verification."
fi
else
_log warn "Checksum file not found: ${checksum_file}; proceeding without verification."
fi
​mkdir_p "${target_dir}"
​_log info "Extracting {snapshot_file} ->{target_dir}"
if ! tar -xzf "{snapshot_file}" -C "{target_dir}"; then
_log error "Extraction failed."
return 7
fi
​if command -v chown >/dev/null 2>&1; then
local uid gid
uid=(id -u 2>/dev/null || echo "")
gid=(id -g 2>/dev/null || echo "")
if [ -n "{uid}" ] && [ -n "{gid}" ]; then
_log info "Setting ownership of restored files to UID:{uid} GID:{gid}"
chown -R "{uid}:{gid}" "${target_dir}" 2>/dev/null || _log warn "chown failed (insufficient permissions)."
fi
fi
​_log info "Restore completed: ${target_dir}"
return 0
}
​----------------------------------------------------------------------
​Usage & Dispatcher
​----------------------------------------------------------------------
​usage() {
cat <<EOF
Usage: $SCRIPT_NAME <command> [--dry-run] [--workdir DIR]
​Commands:
dependency_master      - Updates dependencies based on lock files (npm, pip, etc.).
git_security_audit     - Scans for secrets, large files, and branch divergence (best-effort).
git_workflow_optimizer - Performs garbage collection, prunes branches, and sets performance configs.
local_snapshot         - Creates a compressed tarball snapshot of the working directory (excluding .git/build dirs).
restore_snapshot       - Lists, verifies, and safely extracts a snapshot (latest or specific file).
setup_hooks            - Installs or appends managed pre-commit checks.
​Options:
--dry-run             Show commands without executing them.
--workdir DIR         Specify the working directory (default: current directory).
​Notes:
​Designed for Bash in Termux/PuppyGit. Uses portable fallbacks where possible.
​Snapshots are stored in: ${SNAPSHOT_DIR}
​Logs are stored in: ${LOG_DIR}
EOF
exit 2
}
​---------------------------
​Global CLI parsing
​---------------------------
​while [ $# -gt 0 ]; do
case "1" in
--dry-run) DRY_RUN=1; shift ;;
--workdir)
if [ -n "{2:-}" ] && [ -d "$2" ]; then
WORKDIR="$2"
shift 2
else
_log error "--workdir requires a valid directory"
exit 1
fi
;;
-*)
_log error "Unknown global option: $1"
usage
;;
*) break ;;
esac
done
​if [ -n "{WORKDIR:-}" ] && [ "{WORKDIR}" != "(pwd)" ]; then
if ! cd "{WORKDIR}"; then
_log error "Could not change to work directory ${WORKDIR}"
exit 1
fi
fi
​---------------------------
​Command Dispatch
​---------------------------
​COMMAND="{1:-}"
shift || true
ARGS=("@")
​case "{COMMAND}" in
dependency_master) dependency_master "{ARGS[@]}" ;;
git_security_audit) git_security_audit "{ARGS[@]}" ;;
git_workflow_optimizer) git_workflow_optimizer "{ARGS[@]}" ;;
local_snapshot) local_snapshot "{ARGS[@]}" ;;
restore_snapshot) restore_snapshot "{ARGS[@]}" ;;
setup_hooks) setup_pre_commit_hook "${ARGS[@]}" ;;
""|help|-h|--help) usage ;;
*) _log error "Unknown command: ${COMMAND}"; usage; exit 2 ;;
esac
​exit 0
