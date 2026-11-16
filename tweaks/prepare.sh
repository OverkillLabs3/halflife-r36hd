#!/bin/sh
# prepare.sh - run by the port's run.sh just before the game starts, as its own process, so nothing in here can keep
# the game from starting. Everything it changes is lost at the next reboot.
#   sh prepare.sh <port folder>
# Switches (empty files in the port folder): tweaks_off (skip everything), sdfast_off (leave the SD clock alone).
PORT_DIR="${1:-.}"
TW="$PORT_DIR/tweaks"
LOG="$PORT_DIR/tweaks.log"
wr() { [ -w "$2" ] && echo "$1" > "$2" 2>/dev/null; return 0; }
{
    echo "prepare $(date 2>/dev/null)"
    # drop wired TLB entries a crashed game may have left behind (the game installs its own at start)
    [ -x "$TW/tlbclear" ] && "$TW/tlbclear" "$LOG.tlb" </dev/null >/dev/null 2>&1
    # the SD card at 50 MHz instead of 20 (checks a 2 MB write and read-back, goes back to 20 MHz on any difference)
    if [ -x "$TW/sdfast" ] && [ ! -f "$PORT_DIR/sdfast_off" ]; then
        "$TW/sdfast" "$LOG.sd" none 50000000 </dev/null >/dev/null 2>&1
    fi
    # do not spill pages to the slow SD swap, keep some memory free, bigger read-ahead for asset streaming
    wr 0 /proc/sys/vm/swappiness
    wr 200 /proc/sys/vm/vfs_cache_pressure
    wr 2048 /proc/sys/vm/min_free_kbytes
    wr 512 /sys/block/mmcblk0/queue/read_ahead_kb
    # kernel messages are not drawn on the console during the game
    wr "1 4 1 7" /proc/sys/kernel/printk
    # free clean caches the menu left behind
    sync
    wr 3 /proc/sys/vm/drop_caches
    grep -E 'MemTotal|MemFree|MemAvailable' /proc/meminfo 2>/dev/null
} > "$LOG" 2>&1
exit 0
