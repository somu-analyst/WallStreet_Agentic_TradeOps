# -*- coding: utf-8 -*-
"""One-way mirror: canonical repo -> the separate cloud deployment repo, WITH RENAMING.

WHY THIS EXISTS (user decision, cloud tracker ID 7, 2026-08-27)
    The cloud deployment lives in its own repo, independent of WallStreet_Agentic_TradeOps.
    Two copies of a 43k-line engine therefore exist, which is the drift the CLAUDE.md
    canonical-files rule warns about. This script is the mitigation: the fork is ONE-WAY.
    Edits happen in the canonical files and are pushed outward. The cloud repo is a build
    artifact, never a place to edit.

WHY THE FILES GET RENAMED (user decision, cloud tracker ID 11, 2026-08-27)
    The user wants the two deployments to be unmistakably distinct. Renaming module files
    normally breaks everything, because references live in three different shapes:

        import telegram_bot_optimized as B      <- import statement
        from NYSE_OpenBB import fetch_chain     <- from-import
        JOB_BB = os.path.join(BASE_DIR, "NYSE_OpenBB.py")   <- STRING filename
        py_compile.compile("dashboard.py")                  <- STRING filename

    A rename that only moves files would leave the last two pointing at names that no longer
    exist -- and those fail at RUN time, not import time, so the cloud scheduler would look
    healthy until the night it actually tried to launch a job. This script rewrites all four
    shapes as part of the copy, so the renamed tree is internally consistent by construction.

    The renaming also makes the mirror self-enforcing: a file called cloud_bot.py cannot be
    confused with the canonical telegram_bot_optimized.py, so nobody edits the wrong one.

Usage:
    python tools/sync_cloud.py                 # mirror into ../NYSE_Cloud
    python tools/sync_cloud.py <target-dir>
    python tools/sync_cloud.py --dry-run
"""
import filecmp
import os
import re
import shutil
import sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DST = os.path.join(os.path.dirname(SRC), "NYSE_Cloud")

# canonical name -> cloud name. Every .py that ships is renamed; the mapping is the single
# source of truth for both the file move and the reference rewrite.
RENAME = {
    "telegram_bot_optimized.py": "cloud_bot.py",
    "dashboard.py":              "cloud_dashboard.py",
    "dashboard_app.py":          "cloud_dashboard_app.py",
    "NYSE_OpenBB.py":            "cloud_capture.py",
    "NYSE_OpenBB_derive.py":     "cloud_derive.py",
    "NYSE_YFin.py":              "cloud_yfin.py",
    "NYSE_Telegram.py":          "cloud_report.py",
    "NYSE_intraday.py":          "cloud_intraday.py",
    "run_all_offhours.py":       "cloud_scheduler.py",
    "skew_snapshot.py":          "cloud_skew.py",
    "edgar_13f.py":              "cloud_edgar13f.py",
    "bot_watchdog.py":           "cloud_watchdog.py",
    "mcp_server.py":             "cloud_mcp.py",
    "_ssl_fix.py":               "cloud_ssl_fix.py",
    "cloud_smoke.py":            "cloud_smoke.py",          # already unambiguous
}
FILES = list(RENAME) + ["requirements.txt", "requirements_openbb.txt"]
DIRS = ["_lib", "static", ".streamlit"]

# A copy is not a place to be clever: anything matching these never crosses, whatever the
# whitelist says. The cloud repo is private, but "private" is not a reason to ship keys.
NEVER = ("token.txt", "dash_token.txt", "api_keys.enc", "api_keys.env",
         ".db", ".key", ".pem", "us_bot_")

_MODMAP = {os.path.splitext(o)[0]: os.path.splitext(n)[0]
           for o, n in RENAME.items() if o != n}


def _forbidden(name):
    return any(p in name.lower() for p in NEVER)


def _rewrite(text):
    """Point every reference at the renamed module. Four shapes, all of them load-bearing."""
    for old, new in _MODMAP.items():
        # import X / import X as Y / from X import ...
        text = re.sub(rf"(?m)^(\s*)import\s+{re.escape(old)}\b", rf"\1import {new}", text)
        text = re.sub(rf"(?m)^(\s*)from\s+{re.escape(old)}\b",   rf"\1from {new}", text)
        # NOTE: deliberately NOT a bare-token rewrite. `skew_snapshot` and `edgar_13f` are also
        # DATABASE TABLE names, and a loose rule rewrites them inside SQL strings -- a silent
        # data bug that compiles cleanly and only shows up as a missing table at run time.
        # Verified 2026-08-27: the quoted-string count for both is identical either side of the
        # mirror. If a dynamic importlib.import_module of a renamed module ever appears, handle
        # it explicitly here rather than by loosening this.
        # string filenames: "NYSE_OpenBB.py" -> "cloud_capture.py"
        text = text.replace(f'"{old}.py"', f'"{new}.py"').replace(f"'{old}.py'", f"'{new}.py'")
    return text


def _is_text(path):
    return os.path.splitext(path)[1].lower() in (".py", ".txt", ".toml", ".json", ".md", ".cfg")


def _put(src, dst, dry, rewrite):
    if _forbidden(os.path.basename(src)):
        print(f"  SKIP (never-copy) {os.path.basename(src)}")
        return 0
    if rewrite and _is_text(src):
        new = _rewrite(open(src, encoding="utf-8").read())
        if os.path.exists(dst) and open(dst, encoding="utf-8").read() == new:
            return 0
        print(f"  {'would write' if dry else 'write'} {os.path.basename(dst)}")
        if not dry:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "w", encoding="utf-8", newline="").write(new)
        return 1
    if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
        return 0
    print(f"  {'would copy' if dry else 'copy'} {os.path.basename(dst)}")
    if not dry:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return 1


def _sweep(dst_root, dry):
    """Delete canonically-named .py left over from before the rename, so the cloud tree cannot
    end up with both cloud_bot.py and a stale telegram_bot_optimized.py that nothing imports."""
    n = 0
    for old, new in RENAME.items():
        if old == new:
            continue
        stale = os.path.join(dst_root, old)
        if os.path.exists(stale):
            print(f"  {'would remove' if dry else 'remove'} stale {old}")
            if not dry:
                os.remove(stale)
            n += 1
    return n


def _universe(dst_root, dry):
    """Ship a STRIPPED ticker_universe.xlsx -- reference sheets only.

    The dashboard heatmap reads the `bk` sheet for ticker/name/category. That is curated
    reference data and is NOT derivable, unlike the capture universe which rebuilds itself from
    Wikipedia. Without it the heatmap errors on every render.

    Only the reference sheets cross. The source workbook also holds `Trade` and `MSTR` sheets
    whose columns are unnamed and whose contents nobody has accounted for -- a private repo is
    not a reason to publish data you have not looked at.
    """
    KEEP = ("bk", "openbb_universe", "ticker_universe", "Whole_universe")
    src = os.path.join(SRC, "ticker_universe.xlsx")
    dst = os.path.join(dst_root, "ticker_universe.xlsx")
    hashfile = dst + ".srchash"
    if not os.path.exists(src):
        print("  MISSING in source: ticker_universe.xlsx")
        return 0
    try:
        import hashlib
        with open(src, "rb") as f:
            src_hash = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        print(f"  SKIP ticker_universe.xlsx (could not read source: {e})")
        return 0
    # This used to rebuild and report "changed" on EVERY run, unconditionally -- openpyxl was
    # never even asked whether the source had moved. That is harmless by itself, but it makes
    # `changed` in deploy_cloud.py permanently non-empty, which defeats that tool's whole
    # "never restart when nothing changed" guarantee (found while wiring a scheduled safety
    # net for cloud row 50 -- a schedule built on this would have restarted the live bot every
    # cycle, forever). Comparing a hash of the SOURCE, not the built output, sidesteps openpyxl
    # re-saving to non-identical bytes from identical input (xlsx embeds its own timestamps).
    if os.path.exists(dst) and os.path.exists(hashfile):
        try:
            with open(hashfile, encoding="utf-8") as f:
                if f.read().strip() == src_hash:
                    return 0
        except OSError:
            pass
    try:
        import openpyxl
    except ImportError:
        print("  SKIP ticker_universe.xlsx (openpyxl not installed)")
        return 0
    print(f"  {'would build' if dry else 'build'} ticker_universe.xlsx ({', '.join(KEEP)})")
    if dry:
        return 1
    wb = openpyxl.load_workbook(src)
    for name in list(wb.sheetnames):
        if name not in KEEP:
            del wb[name]
    wb.save(dst)
    with open(hashfile, "w", encoding="utf-8") as f:
        f.write(src_hash)
    return 1


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    dst_root = os.path.abspath(args[0]) if args else DEFAULT_DST
    if os.path.abspath(dst_root) == os.path.abspath(SRC):
        print("FATAL: target is the canonical repo itself")
        return 1
    if not dry:
        os.makedirs(dst_root, exist_ok=True)
    print(f"mirror  {SRC}\n     -> {dst_root}{'  (dry run)' if dry else ''}\n")

    n = 0
    for f in FILES:
        s = os.path.join(SRC, f)
        if not os.path.exists(s):
            print(f"  MISSING in source: {f}")
            continue
        n += _put(s, os.path.join(dst_root, RENAME.get(f, f)), dry, rewrite=f.endswith(".py"))
    for d in DIRS:
        s_dir = os.path.join(SRC, d)
        if not os.path.isdir(s_dir):
            continue
        for root, _sub, files in os.walk(s_dir):
            if "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".pyc"):
                    continue
                s = os.path.join(root, f)
                n += _put(s, os.path.join(dst_root, os.path.relpath(s, SRC)), dry,
                          rewrite=f.endswith(".py"))
    n += _universe(dst_root, dry)
    n += _sweep(dst_root, dry)

    print(f"\n{n} file(s) {'would change' if dry else 'updated'}")
    if n and not dry:
        print(f"\nnext:  cd {dst_root}  &&  git add -A  &&  git commit -m \"sync\"  &&  git push")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
