#!/usr/bin/env python3
"""Private X server and exclusive, project-local Wine prefix."""
import argparse
import fcntl
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from runtime import STATE, KEYBOARD_PREFIX, SETTINGS_PREFIX, ORGANIZE_PREFIX, executable, wine_env, wineserver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', choices=['keyboard', 'settings', 'organize', 'none'], default='keyboard')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command: parser.error('command required after --')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    prefix = {'keyboard': KEYBOARD_PREFIX, 'settings': SETTINGS_PREFIX, 'organize': ORGANIZE_PREFIX, 'none': None}[args.prefix]
    lock = None
    if prefix:
        lock = (STATE / (prefix.name + '.lock')).open('a')
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Wine prefix already in use: ' + str(prefix))
    env = wine_env(prefix, args.prefix == 'settings') if prefix else dict(os.environ)
    env.pop('WAYLAND_DISPLAY', None)
    env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    if args.prefix == 'settings':
        env['MESA_LOADER_DRIVER_OVERRIDE'] = 'llvmpipe'

    # Never allow Xvfb to hijack display :0 (used by Xwayland/real display). Pick 95-120.
    disp_num = 95
    for d in range(95, 120):
        if not Path(f'/tmp/.X11-unix/X{d}').exists() and not Path(f'/tmp/.X{d}-lock').exists():
            disp_num = d
            break

    screen_geom = '1280x800x24' if args.prefix == 'settings' else '1280x800x24'
    read_fd, write_fd = os.pipe()
    child = None
    with (STATE / 'xvfb.log').open('a') as log:
        xvfb = subprocess.Popen([executable('xvfb', 'Xvfb'), f':{disp_num}', '-displayfd', str(write_fd),
            '-screen', '0', screen_geom, '-nolisten', 'tcp', '-ac'],
            pass_fds=(write_fd,), stdout=log, stderr=log)
        os.close(write_fd)
        def stop(signum, frame):
            if child and child.poll() is None: child.terminate()
            else: raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(read_fd, selectors.EVENT_READ)
                if not selector.select(10): raise RuntimeError('Xvfb startup timed out')
                display = os.read(read_fd, 32).decode().strip()
            if not display.isdecimal(): raise RuntimeError('Xvfb failed; see work/xvfb.log')
            env['DISPLAY'] = ':' + display
            env['DOUBAO_PRIVATE_DISPLAY'] = '1'
            child = subprocess.Popen(command, env=env)
            return child.wait()
        finally:
            if child and child.poll() is None:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
            try:
                if prefix:
                    subprocess.run([wineserver(), '-k'], env=env, stdout=log, stderr=log, timeout=10)
                    subprocess.run([wineserver(), '-w'], env=env, stdout=log, stderr=log, timeout=10)
            finally:
                xvfb.terminate()
                try: xvfb.wait(timeout=5)
                except subprocess.TimeoutExpired: xvfb.kill(); xvfb.wait()
                os.close(read_fd)


if __name__ == '__main__':
    os.umask(0o077)
    raise SystemExit(main())
