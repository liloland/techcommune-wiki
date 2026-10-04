---
title: Test a logrotate rule without waiting until tomorrow
category: tips
summary: How to dry-run and force a logrotate rule safely, and what its three most common error messages mean.
date: 2026-10-04
author: TechCommune
tested_on: Debian 13 (trixie), logrotate 3.22.0
tags: logrotate, logs, testing
---

logrotate normally runs once a day, so a mistake in a rule can stay hidden until tomorrow, or until a log fills a disk. You can test a rule in a minute instead. Use a scratch state file with `-s` so your tests never touch the real one (on Debian and Ubuntu the real one is usually `/var/lib/logrotate/status`).

Here is the rule used for the examples below:

```
/tmp/lab/app.log {
    daily
    rotate 3
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root root
}
```

## 1. Dry run: see what logrotate would do

```bash
sudo logrotate -d -s /tmp/lr-state /etc/logrotate.d/myapp
```

`-d` is debug mode: it prints what it would do and changes nothing. It does not even create the state file, so you can run it as often as you like.

## 2. The trap: "log does not need rotating" on the first run

On the very first run, with no state file, logrotate assumes the log was just rotated:

```
rotating pattern: /tmp/lab/app.log after 1 days empty log files are not rotated, (3 rotations), old logs are removed
considering log /tmp/lab/app.log
Creating new state
  Now: 2026-10-04 00:46
  Last rotated at 2026-10-04 00:00
  log does not need rotating (log has already been rotated)
```

That tells you nothing about your rule. Pretend the last rotation was a few days ago by writing a scratch state file with an old date (the format is one line per log: the path, then `year-month-day-hour:minute:second`):

```bash
printf 'logrotate state -- version 2\n"/tmp/lab/app.log" 2026-10-1-0:0:0\n' > /tmp/lr-state
sudo logrotate -d -s /tmp/lr-state /etc/logrotate.d/myapp
```

Now the dry run shows the real plan (shortened here):

```
  Last rotated at 2026-10-01 00:00
  log needs rotating
previous log /tmp/lab/app.log.1 does not exist
renaming /tmp/lab/app.log.1.gz to /tmp/lab/app.log.2.gz (rotatecount 3, logstart 1, i 1),
renaming /tmp/lab/app.log to /tmp/lab/app.log.1
creating new /tmp/lab/app.log mode = 0640 uid = 0 gid = 0
```

Check the lines that matter to you: does it rotate when you expect, and does it create the new file with the mode and owner your program needs? Because the rule has `delaycompress`, there is no "compressing log" line yet: the file is compressed at the next rotation (see the next section).

## 3. Force a real rotation on a copy

`-f` forces a rotation now, whatever the age of the log. It really rotates, so try it on a copy of the rule that points at a scratch file, not on a live log:

```bash
logrotate -f -s /tmp/lr-state /tmp/lab/app.conf
ls -l /tmp/lab
```

```
-rw-r----- 1 root root   0 Oct  4 00:46 app.log
-rw-r--r-- 1 root root 451 Oct  4 00:46 app.log.1
```

(The listing also shows your config and the state file, left out here.)

The old log is now `app.log.1`, and a fresh empty `app.log` was created with mode `0640`, as the rule says. `app.log.1` is not compressed yet because of `delaycompress`. Force a second rotation and the earlier file is compressed:

```
app.log  app.log.1  app.log.2.gz
```

## 4. The three error messages you will meet

**A typo in the config is only a warning, and the exit code is still 0.** Here `daily` was mistyped as `dayly`:

```
warning: /tmp/lab/typo.conf:2 unknown option 'dayly' -- ignoring line
Handling 1 logs
```

logrotate carries on without that line, so the rule silently falls back to its defaults. Always read the first lines of a dry run, or check for the word `warning` in the output.

**Log directory writable by everyone** (or by a group other than root):

```
error: skipping "/tmp/lab/open/web.log" because parent directory has insecure permissions (It's world writable or writable by group which is not "root") Set "su" directive in config file to tell logrotate which user/group should be used for rotation.
```

The log is skipped completely. The fix is the message's own advice: add a `su` line to the rule, with the user and group that own the log directory, for example `su root root`. After adding it, the dry run showed `log needs rotating` and the renames. Tightening the directory permissions also works.

**Config file writable by group or others:**

```
error: Ignoring /tmp/lab/app.conf because it is writable by group or others.
Handling 0 logs
```

This one is easy to miss, because logrotate exits with status 1 but nothing else happens: zero logs are handled. Files in `/etc/logrotate.d/` get the same treatment (`error: found error in file app, skipping`). Fix it with `sudo chmod 644` and make sure root owns the file.

## The short version

| Goal | Command |
|---|---|
| See what would happen, change nothing | `logrotate -d -s /tmp/lr-state CONFIG` |
| Make the dry run realistic | put an old date in the scratch state file |
| Rotate now, for real | `logrotate -f -s /tmp/lr-state CONFIG` |
| Watch a normal run in detail | `logrotate -v -s /tmp/lr-state CONFIG` |
| Insecure parent directory | add `su USER GROUP` to the rule |
| Config ignored | `chmod 644` it and make it root-owned |

See also the [cron guide](site:docs/sysadmin/cron.html) and [timers guide](site:docs/sysadmin/systemd-units-timers.html) for how the daily run is scheduled, and the [disk full runbook](site:docs/sysadmin/troubleshoot-disk-full.html) for when logs have already filled the disk.
