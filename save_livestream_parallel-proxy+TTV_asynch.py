#!/bin/env python3
import sys
import asyncio
import re
import json
import urllib.request
from random import uniform
from time import gmtime, strftime
 
MIN_WAIT = 2
MAX_WAIT = 11
 
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
 
async def log_error(message: str):
    def _write():
        with open("errors.log", "a", encoding='utf-8') as err_log:
            err_log.write(f"{timestamp()} {message}\n")
    await asyncio.to_thread(_write)
 
def _check_twitch_gql(author_name: str) -> bool:
    url = "https://gql.twitch.tv/gql"
    payload = json.dumps([{
        "operationName": "StreamMetadata",
        "variables": {"channelLogin": author_name},
        "extensions": {"persistedQuery": {
            "version": 1,
            "sha256Hash": "059c4653b788f5bdb2f5a2d2a24b0ddc3831a15079001a3d927556a96fb0517f"
        }}
    }]).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            # stream == null если офлайн, object если онлайн
            return data[0]["data"]["user"]["stream"] is not None
    except Exception:
        return False
 
# Вместо is_stream_live через streamlink subprocess:
async def is_stream_live_fast(author_name: str) -> bool:
    # asyncio.to_thread — urllib не блокирует event loop
    return await asyncio.to_thread(_check_twitch_gql, author_name)
 
async def run_streamlink(args: list, timeout: int = 10):
    """Запускает streamlink асинхронно, возвращает (returncode, stdout, stderr)"""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise
 
async def download(author_name, quality="best", proxy=None, twitch_proxy_playlist=None):
    uri = f"https://www.twitch.tv/{author_name}"
    log_filename = f"{author_name}_{strftime('%Y%m%d_%H-%M-%S', gmtime())}.log"
 
    while True:
        # ← лёгкая проверка: просто HTTP GET, никаких subprocess
        if not await is_stream_live_fast(author_name):
            wait_time = int(uniform(MIN_WAIT, MAX_WAIT))
            print(f"{timestamp()} Stream is offline {author_name}. Waiting {wait_time} sec...", flush=True)
            await asyncio.sleep(wait_time)
            continue
 
        # стрим онлайн — теперь запускаем тяжёлый streamlink
        current_time = timestamp()
        try:
            info_cmd = [
                "streamlink", "--json", "--twitch-low-latency", "--twitch-disable-ads", "--stream-segment-threads", "3", "--hls-live-restart", "--stream-segment-timeout", "15", "--stream-segment-attempts", "10",
                uri, quality
            ]
            if proxy:
                info_cmd.insert(1, f"--http-proxy={proxy}")
            if twitch_proxy_playlist:
                info_cmd.insert(1, f"--twitch-proxy-playlist={twitch_proxy_playlist}")
 
            returncode, stdout, info_stderr = await run_streamlink(info_cmd, timeout=10)
            if returncode != 0:
                # HTTP сказал онлайн, streamlink не смог — редко, просто ждём
                await asyncio.sleep(int(uniform(MIN_WAIT, MAX_WAIT)))
                continue
 
            stream_info = json.loads(stdout)
            original_title = stream_info.get('metadata', {}).get('title', 'no_title')
            clean_title = sanitize_filename_windows(original_title)
 
            filename_format = r"{time:%Y%m%d %H-%M-%S} [" + author_name + r"] " + clean_title + r" [" + quality + r"][{id}].ts"
 
            cmd = [
                "streamlink", "--twitch-disable-ads", "--twitch-low-latency", "--stream-segment-threads", "3", "--hls-live-restart", "--stream-segment-timeout", "15", "--stream-segment-attempts", "10", "-o", filename_format,
                uri, quality
            ]
            if proxy:
                cmd.insert(1, f"--http-proxy={proxy}")
            if twitch_proxy_playlist:
                cmd.insert(1, f"--twitch-proxy-playlist={twitch_proxy_playlist}")
 
            print(f"{current_time} LIVE {author_name}. Recording: {clean_title}", flush=True)
 
            log_file = await asyncio.to_thread(open, log_filename, "a", encoding='utf-8')
            try:
                await asyncio.to_thread(log_file.write,
                    f"{current_time} Starting recording for {author_name} ({clean_title})\n")
                if info_stderr:
                    await asyncio.to_thread(log_file.write, info_stderr)
 
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
 
                async def pipe_to_log(stream):
                    async for line in stream:
                        try:
                            decoded = line.decode('utf-8')
                        except UnicodeDecodeError:
                            decoded = line.decode('cp1251', errors='replace')
                        await asyncio.to_thread(log_file.write, decoded)
                        await asyncio.to_thread(log_file.flush)
 
                await asyncio.gather(
                    pipe_to_log(proc.stdout),
                    pipe_to_log(proc.stderr)
                )
                await proc.wait()
                await asyncio.to_thread(log_file.write, f"{timestamp()} Finished recording\n\n")
            finally:
                await asyncio.to_thread(log_file.close)
 
        except json.JSONDecodeError as e:
            await log_error(f"{author_name} — ERROR parsing stream info: {str(e)}")
        except asyncio.TimeoutError:
            await log_error(f"{author_name} — Timeout while checking stream info")
        except Exception as e:
            await log_error(f"{author_name} — Unexpected error: {str(e)}")
 
        wait_time = int(uniform(MIN_WAIT, MAX_WAIT))
        print(f"{timestamp()} Stream ended or Error {author_name}. Restart after {wait_time} sec...\n", flush=True)
        try:
            await asyncio.sleep(wait_time)
        except asyncio.CancelledError:
            print(f"{timestamp()} Stopped by User {author_name}.", flush=True)
            return
 
async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 save_livestream_parallel-proxy+TTV.py [--proxy http://IP:PORT] [--twitch-proxy-playlist=URL] <streamer1> ...")
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
 
    tasks = [
        asyncio.create_task(download(name, "best", proxy, twitch_proxy_playlist))
        for name in streamers
    ]
 
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\nStop all processes...")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
 
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by User.")
