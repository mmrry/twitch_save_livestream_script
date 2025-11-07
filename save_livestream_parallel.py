#!/bin/env python3
import sys
import time
import subprocess
import re
import json
from multiprocessing import Process
from random import uniform
from time import gmtime, strftime
from pathlib import Path

MIN_WAIT = 2
MAX_WAIT = 11

# Split duration: 11 hours 38 minutes (41880 seconds)
SPLIT_SECONDS = 11 * 3600 + 38 * 60
CHECK_INTERVAL = 2000  # seconds between ffprobe checks

INVALID_CHARS = r'<>:"/\\|?*'
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename_windows(name: str, replacement="_") -> str:
    if not name:
        return "no_title"
    name = re.sub(r'[\U00010000-\U0010ffff]', '', name)

    def is_valid_char(c):
        code = ord(c)
        return (
            c == ' ' or
            (31 < code < 127 and c not in INVALID_CHARS) or
            'А' <= c <= 'я' or c in ('Ё', 'ё')
        )
    name = ''.join(c if is_valid_char(c) else replacement for c in name)
    name = name.strip(" .")
    name = name[:100]
    if name.upper() in RESERVED_NAMES:
        name = f"_{name}"
    return name or "stream_title"


def timestamp():
    return strftime("[%Y-%m-%d %H:%M:%S]", gmtime())


def log_error(message: str):
    with open("errors.log", "a", encoding='utf-8') as err_log:
        err_log.write(f"{timestamp()} {message}\n")


def is_stream_live(author_name, quality="best", proxy=None, twitch_proxy_playlist=None):
    cmd = [
        "streamlink", "--stream-url",
        "--twitch-disable-ads",
        f"https://www.twitch.tv/{author_name}", quality
    ]
    if proxy:
        cmd.insert(1, f"--http-proxy={proxy}")
    if twitch_proxy_playlist:
        cmd.insert(1, f"--twitch-proxy-playlist={twitch_proxy_playlist}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False


def get_file_duration(filepath):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        log_error(f"ffprobe error on {filepath}: {e}")
    return 0.0


def download(author_name, quality="best", proxy=None, twitch_proxy_playlist=None):
    uri = f"https://www.twitch.tv/{author_name}"

    while True:
        part_counter = 1  # reset counter when streamer goes offline and comes back
        current_time = timestamp()
        log_filename = f"{author_name}_{strftime('%Y%m%d_%H-%M-%S', gmtime())}[part{part_counter:02d}].log"

        if not is_stream_live(author_name, quality, proxy, twitch_proxy_playlist):
            wait_time = int(uniform(MIN_WAIT, MAX_WAIT))
            print(f"{timestamp()} Stream is offline {author_name}. Waiting {wait_time} sec...")
            time.sleep(wait_time)
            continue

        try:
            info_cmd = [
                "streamlink", "--json", "--twitch-low-latency", "--twitch-disable-ads", "--stream-segment-threads", "3", "--hls-live-restart", "--stream-segment-timeout", "15", "--stream-segment-attempts", "10",
                uri, quality
            ]
            if proxy:
                info_cmd.insert(1, f"--http-proxy={proxy}")
            if twitch_proxy_playlist:
                info_cmd.insert(1, f"--twitch-proxy-playlist={twitch_proxy_playlist}")

            info_result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=10)
            if info_result.returncode != 0:
                raise subprocess.CalledProcessError(info_result.returncode, info_cmd)

            stream_info = json.loads(info_result.stdout)
            original_title = stream_info.get('metadata', {}).get('title', 'no_title')
            clean_title = sanitize_filename_windows(original_title)

            while True:
                filename_format = (
                    r"{time:%Y%m%d %H-%M-%S} [" + author_name + r"] " + clean_title +
                    r" [" + quality + r"][{id}][part" + f"{part_counter:02d}" + r"].ts"
                )
                log_filename = f"{author_name}_{strftime('%Y%m%d_%H-%M-%S', gmtime())}[part{part_counter:02d}].log"

                print(f"{timestamp()} LIVE {author_name}. Recording: {clean_title} [part{part_counter:02d}]")

                with open(log_filename, "a", encoding='utf-8') as log_file:
                    log_file.write(f"{timestamp()} Starting recording for {author_name} ({clean_title}) part{part_counter:02d}\n")

                    cmd = [
                        "streamlink", "--twitch-low-latency", "--twitch-disable-ads", "--stream-segment-threads", "3", "--hls-live-restart", "--stream-segment-timeout", "15", "--stream-segment-attempts", "10", "-o", filename_format,
                        uri, quality
                    ]
                    if proxy:
                        cmd.insert(1, f"--http-proxy={proxy}")
                    if twitch_proxy_playlist:
                        cmd.insert(1, f"--twitch-proxy-playlist={twitch_proxy_playlist}")

                    proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
                    output_file = None
                    start_check = time.time()

                    try:
                        while True:
                            ret = proc.poll()

                            if output_file is None:
                                for f in Path(".").glob(f"*[{author_name}]*[{quality}]*part{part_counter:02d}.ts"):
                                    output_file = str(f)
                                    break

                            if output_file and (time.time() - start_check >= CHECK_INTERVAL):
                                start_check = time.time()
                                duration = get_file_duration(output_file)
                                if duration > SPLIT_SECONDS:
                                    log_file.write(f"{timestamp()} Duration {duration:.0f}s > {SPLIT_SECONDS}. Restarting recording for {author_name}\n")
                                    print(f"{timestamp()} Split: {author_name} file exceeded {SPLIT_SECONDS} seconds, restarting...")
                                    try:
                                        proc.terminate()
                                        try:
                                            proc.wait(timeout=5)
                                        except subprocess.TimeoutExpired:
                                            proc.kill()
                                            proc.wait()
                                    except Exception as e:
                                        log_error(f"{author_name} — Error terminating process: {e}")
                                    part_counter += 1
                                    break

                            if ret is not None:
                                log_file.write(f"{timestamp()} Recording process exited with code {ret}\n")
                                break

                            time.sleep(5)

                    except KeyboardInterrupt:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        print(f"{timestamp()} Stopped by User {author_name}.")
                        return

                    log_file.write(f"{timestamp()} Finished recording or restarted for {author_name}\n\n")

        except json.JSONDecodeError as e:
            log_error(f"{author_name} — ERROR parsing stream info: {str(e)}")
        except subprocess.TimeoutExpired:
            log_error(f"{author_name} — Timeout while checking stream info")
        except subprocess.CalledProcessError as e:
            log_error(f"{author_name} — ERROR streamlink: {str(e)}")
        except Exception as e:
            log_error(f"{author_name} — Unexpected error: {str(e)}")

        wait_time = int(uniform(MIN_WAIT, MAX_WAIT))
        print(f"{timestamp()} Stream ended or Error {author_name}. Restart after {wait_time} sec...\n")
        try:
            time.sleep(wait_time)
        except KeyboardInterrupt:
            print(f"{timestamp()} Stopped by User {author_name}.")
            return


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 save_livestream_parallel.py [--proxy http://IP:PORT] [--twitch-proxy-playlist=URL] <streamer1> ...")
        sys.exit(1)

    proxy = None
    twitch_proxy_playlist = None
    streamers = []

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--proxy" and i + 1 < len(args):
            proxy = args[i + 1]
            i += 2
        elif args[i].startswith("--twitch-proxy-playlist="):
            twitch_proxy_playlist = args[i].split("=", 1)[1]
            i += 1
        else:
            streamers.append(args[i])
            i += 1

    if not streamers:
        print("No streamers provided.")
        sys.exit(1)

    processes = []
    for name in streamers:
        p = Process(target=download, args=(name, "best", proxy, twitch_proxy_playlist))
        p.start()
        processes.append(p)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\nStop all processes...")
        for p in processes:
            p.terminate()


if __name__ == '__main__':
    main()
