# save_livestream.py

Main idea from [https://github.com/mrwnwttk/livestream_scripts](https://github.com/mrwnwttk/livestream_scripts/blob/main/save_livestream.py).

Requires `streamlink` and `python3` to be installed and in your respective PATH environment variable.

Script always monitor for all (multiple streamers) when livestream start.

Have options:
* `--proxy http://IP:PORT`
* `--twitch-proxy-playlist=https://[TTV-LOL-PRO v1 server]`

For `twitch-proxy-playlist` option _(TTV-LOL-PRO v1)_ you need to patch streamlink - https://github.com/2bc4/streamlink-ttvlol

https://wiki.cdn-perfprod.com/v1/must-read/proxies

TTV-LOL-PRO v1 servers:
* https://lb-eu.cdn-perfprod.com (Europe)
* https://lb-eu2.cdn-perfprod.com (Europe 2)
* https://lb-eu3.cdn-perfprod.com (Europe 3, using Russia-only proxies)
* https://lb-eu4.cdn-perfprod.com (Europe 4)
* https://lb-eu5.cdn-perfprod.com (Europe 5)
* https://lb-na.cdn-perfprod.com (NA)
* https://lb-as.cdn-perfprod.com (Asia)
* https://lb-sa.cdn-perfprod.com (SA)

luminous-ttv servers:
* https://eu.luminous.dev (Europe 1) Russia
* https://eu2.luminous.dev (Europe 2) Ukraine
* https://eu3.luminous.dev (Europe 3) Bulgaria
* https://as.luminous.dev (Asia) Kazakhstan

Current wait time (in seconds):
* MIN_WAIT = 2
* MAX_WAIT = 11

Current streamlink options:
* --twitch-low-latency
* --twitch-disable-ads
* --stream-segment-threads=3
* --hls-live-restart
* --stream-segment-timeout=15
* --stream-segment-attempts=10

You can change it, see doc - https://streamlink.github.io/cli.html 

Script <ins>don't record in 2k\4k resoluion</ins> because it's only available through GraphQL. Streamlink use Twitch API.

2K VOD donwload:
```
.\yt-dlp.exe --proxy socks5://<proxy>  --add-headers Authorization:"OAuth TOKEN" https://www.twitch.tv/videos/<VOD ID>
```


Example:
```
$ python3 save_livestream_parallel.py [--proxy http://IP:PORT] [--twitch-proxy-playlist=URL] <streamer1> <streamer2> ...

[2025-08-08 13:06:46] Stream is offline <streamer 1>.. Waiting 7 sec...
[2025-08-08 13:06:44] LIVE <streamer 2>. Recording: <NAME>
[2025-08-08 13:06:50] Stream is offline <streamer 3>.. Waiting 9 sec...

[...]
```

### To Do:
* save_livestream_parallel-proxy+TTV.py: check --twitch-proxy-playlist and --proxy if its get real data and alive 
