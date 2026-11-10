# Nuga CS Demo — клипы хайлайтов из самой CS2 (через HLAE + ffmpeg).
#
# Одна команда делает всё сама:
#
#   python clips3d.py record --demo путь\к\демке.dem.zst --player Nuga
#
#   1) разбирает демку и находит моменты (ACE / 4K / 3K / клатчи — те же, что на сайте);
#   2) запускает CS2 через HLAE, открывает демку, ставит камеру от лица игрока
#      и записывает каждый момент (управление — через консоль игры по сети, нажимать ничего не нужно);
#   3) собирает из записей mp4: по одному на момент и общий montage.mp4.
#
# Готовые ролики лежат в clips3d\<id матча>\.
# Нужны на компьютере: CS2 (Steam), HLAE (https://www.advancedfx.org) и ffmpeg.
# Пока идёт запись, окно CS2 трогать не нужно. FACEIT AC должен быть закрыт.
#
# Настройки игры не меняются: CS2 запускается с отдельной папкой конфигов (clips3d\_cfg).

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
MATCHES = BASE / "matches"
OUT = BASE / "clips3d"                 # сюда пишутся записи и готовые ролики (в .gitignore)

TICKRATE = 64                          # демки CS2 / FACEIT — 64 тика в секунду
STEAM64_BASE = 76561197960265728       # SteamID64 − это число = account id
NETCON_PORT = 29730                    # порт консоли CS2 (только на этом компьютере)

# Сколько секунд захватывать вокруг момента
PRE_MULTI = 4.0      # до первого убийства мульти-килла
PRE_NEXT = 2.5       # до каждого следующего убийства (долгие паузы между фрагами вырезаются)
POST_MULTI = 2.0     # после каждого убийства
PRE_CLUTCH = 2.0     # до начала клатча (когда игрок остался один)
POST_CLUTCH = 1.5    # после конца раунда
MAX_CLIP = 75.0      # длиннее не пишем (долгие клатчи обрезаются с начала)
LEAD = 3.0           # за сколько секунд до момента перематываем демку (игра успевает прогрузиться)

ORDER = {"ACE": 0, "1v5": 1, "1v4": 2, "4K": 3, "1v3": 4, "3K": 5, "1v2": 6, "2K": 7, "1v1": 8, "1K": 9}


ON_SAY = None        # сюда сайт подставляет свою функцию, чтобы показывать ход записи на странице


def say(text: str = "") -> None:
    if ON_SAY:
        ON_SAY(text)
        return
    print(text, flush=True)


# ---------- разбор демки ----------

def file_id(path: Path) -> str:
    """Отпечаток файла — тот же id, что у матча на сайте."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()[:12]


def unpack_demo(demo: Path, target: Path) -> None:
    """Кладёт демку в target как обычный .dem (распаковывает .gz / .zst)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    if demo.suffix == ".gz":
        with gzip.open(demo, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
    elif demo.suffix == ".zst":
        import zstandard
        with open(demo, "rb") as src, open(tmp, "wb") as dst:
            zstandard.ZstdDecompressor().copy_stream(src, dst)
    else:
        shutil.copyfile(demo, tmp)
    tmp.replace(target)


def load_analysis(mid: str, dem: Path) -> dict:
    """Разбор матча: берём сохранённый (clips3d/<id>/analysis.json.gz), иначе разбираем демку сами."""
    cache = OUT / mid / "analysis.json.gz"
    if cache.exists():
        with gzip.open(cache, "rt", encoding="utf-8") as f:
            return json.load(f)
    say("Разбираю демку (около минуты)…")
    sys.path.insert(0, str(BASE))
    from analyzer import analyze_demo
    data = analyze_demo(dem)
    slim = {"map": data["map"], "rounds": data["rounds"], "kill_events": data["kill_events"],
            "players": [{"name": p["name"], "steamid": p["steamid"], "team": p["team"]} for p in data["players"]],
            "replay": {"rounds": [{"start": r["start"], "end": r["end"]} for r in data["replay"]["rounds"]],
                       "highlights": data["replay"]["highlights"]}}
    cache.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache, "wt", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    with gzip.open(cache, "rt", encoding="utf-8") as f:
        return json.load(f)


# ---------- какие моменты записывать ----------

def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_")
    return s[:24] or "player"


def build_clips(data: dict, types: set[str] | None, player: str | None, limit: int | None, min_kills: int) -> list[dict]:
    players = data["players"]
    rounds = data["replay"]["rounds"]
    kill_events = data.get("kill_events", [])

    # Убийства каждого игрока по раундам: (раунд, игрок) → тики
    by_round: dict[tuple, list[int]] = {}
    for e in kill_events:
        if e[2] is not None:
            by_round.setdefault((e[0], e[2]), []).append(e[1])

    found = []       # (раунд, игрок, тип, отрезки [начало, конец])
    for (ri, pi), ticks in by_round.items():
        if len(ticks) < min_kills:
            continue
        ticks = sorted(ticks)
        kind = "ACE" if len(ticks) >= 5 else f"{len(ticks)}K"
        segs = [[t - (PRE_MULTI if i == 0 else PRE_NEXT) * TICKRATE, t + POST_MULTI * TICKRATE] for i, t in enumerate(ticks)]
        found.append((ri, pi, kind, segs))
    for h in data["replay"].get("highlights", []):
        if h["type"].startswith("1v"):              # выигранные клатчи — целиком, до конца раунда
            r = rounds[h["round"]]
            end = r["end"] + POST_CLUTCH * TICKRATE
            start = max(h["tick"] - PRE_CLUTCH * TICKRATE, end - MAX_CLIP * TICKRATE)
            found.append((h["round"], h["player"], h["type"], [[start, end]]))

    # Один раунд + один игрок (например 4K и 1v3 сразу) → один клип
    merged: dict[tuple, dict] = {}
    for ri, pi, kind, segs in found:
        p = players[pi]
        if types and kind not in types:
            continue
        if player and player.lower() not in p["name"].lower():
            continue
        c = merged.setdefault((ri, pi), {"round": ri, "player": pi, "name": p["name"], "steamid": p["steamid"],
                                         "types": [], "segs": []})
        c["types"].append(kind)
        c["segs"] += [[max(int(a), rounds[ri]["start"]), int(b)] for a, b in segs]
    clips = list(merged.values())
    for c in clips:
        c["types"].sort(key=lambda t: ORDER.get(t, 9))
        # Склеиваем отрезки, которые пересекаются или идут почти подряд (пауза меньше 2 секунд)
        segs = []
        for a, b in sorted(c["segs"]):
            if segs and a <= segs[-1][1] + 2 * TICKRATE:
                segs[-1][1] = max(segs[-1][1], b)
            else:
                segs.append([a, b])
        c["segs"] = segs
        c["start"], c["end"] = segs[0][0], segs[-1][1]
        c["length"] = sum(b - a for a, b in segs) / TICKRATE

    if limit:                                        # просили не все — берём самые крутые
        clips.sort(key=lambda c: (ORDER.get(c["types"][0], 9), c["round"]))
        clips = clips[:limit]

    clips.sort(key=lambda c: c["start"])             # по порядку демки
    for i, c in enumerate(clips):
        c["index"] = i
        c["file"] = f"{i + 1:02d}_R{c['round'] + 1:02d}_{'+'.join(c['types'])}_{safe_name(c['name'])}.mp4"
    return clips


# ---------- где что установлено ----------

def find_steam() -> Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            p = Path(winreg.QueryValueEx(k, "SteamPath")[0])
            if p.exists():
                return p
    except Exception:
        pass
    p = Path(r"C:\Program Files (x86)\Steam")
    return p if p.exists() else None


def find_cs2(arg: str | None) -> Path:
    """Папка «Counter-Strike Global Offensive». Ищем во всех библиотеках Steam."""
    candidates = [Path(x) for x in (arg, os.environ.get("CS2_DIR")) if x]
    steam = find_steam()
    if steam:
        libs = [steam]
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            libs += [Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore"))]
        candidates += [lib / "steamapps" / "common" / "Counter-Strike Global Offensive" for lib in libs]
    for d in candidates:
        if (d / "game" / "bin" / "win64" / "cs2.exe").exists():
            return d
    sys.exit("Не нашёл CS2. Укажи папку: --cs2 \"...\\Counter-Strike Global Offensive\"")


def find_hlae(arg: str | None) -> Path:
    candidates = [Path(x) for x in (arg, os.environ.get("HLAE_DIR")) if x]
    candidates += [Path(r"D:\HLAE"), Path(r"C:\HLAE"), Path(r"C:\Program Files (x86)\HLAE"), Path(r"C:\Program Files\HLAE")]
    for d in candidates:
        if (d / "HLAE.exe").exists() and (d / "x64" / "AfxHookSource2.dll").exists():
            return d
    sys.exit("Не нашёл HLAE. Скачай с https://www.advancedfx.org и укажи папку: --hlae \"D:\\HLAE\"")


def ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit("Не нашёл ffmpeg. Установи: winget install Gyan.FFmpeg (и открой терминал заново).")
    return exe


def running(name: str) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"], capture_output=True, text=True, errors="ignore").stdout
    return name.lower() in out.lower()


# ---------- консоль CS2 по сети ----------

class Console:
    """Консоль CS2 (ключ запуска -netconport): шлём команды и читаем, что печатает игра."""

    def __init__(self, port: int, wait: float = 180):
        end = time.time() + wait
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
                break
            except OSError:
                if time.time() > end or not running("cs2.exe") and time.time() > end - wait + 40:
                    raise RuntimeError("CS2 не запустилась или не открыла консоль")
                time.sleep(2)
        self.sock.settimeout(0.25)
        self.buf = ""
        self.log = None

    def read(self) -> str:
        try:
            data = self.sock.recv(65536)
        except socket.timeout:
            return ""
        except OSError:
            raise RuntimeError("Связь с CS2 пропала — игра закрылась или вылетела")
        if not data:
            raise RuntimeError("Связь с CS2 пропала — игра закрылась или вылетела")
        text = data.decode("utf-8", errors="replace")
        if self.log:
            self.log.write(text)
            self.log.flush()
        return text

    def cmd(self, *lines: str) -> None:
        for line in lines:
            self.sock.sendall(line.encode("utf-8") + b"\n")
            time.sleep(0.05)

    def wait_for(self, pattern: str, timeout: float) -> str | None:
        """Ждём, пока игра напечатает строку с pattern. Возвращает эту строку или None по таймауту."""
        rx = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            self.buf += self.read()
            *lines, self.buf = self.buf.split("\n")
            for line in lines:
                if rx.search(line):
                    return line
        return None

    def quiet(self, seconds: float) -> None:
        """Просто читаем вывод указанное время (чтобы не копился)."""
        end = time.time() + seconds
        while time.time() < end:
            self.read()
        self.buf = ""


# ---------- запись в CS2 ----------

def launch_cs2(cs2: Path, hlae: Path, width: int, height: int) -> None:
    steam = find_steam()
    if not running("steam.exe"):
        if not steam:
            sys.exit("Steam не запущен. Запусти Steam и повтори.")
        say("Запускаю Steam…")
        subprocess.Popen([str(steam / "steam.exe"), "-silent"])
        time.sleep(25)
    cfg_home = OUT / "_cfg"                       # отдельная папка настроек — свои настройки игры не трогаем
    cfg_home.mkdir(parents=True, exist_ok=True)
    cmdline = (f"-steam -insecure +sv_lan 1 -console -novid -sw -w {width} -h {height} "
               f"-afxDisableSteamStorage -netconport {NETCON_PORT} -afxFixNetCon")
    say("Запускаю CS2 через HLAE…")
    subprocess.Popen([str(hlae / "HLAE.exe"), "-customLoader", "-noGui", "-autoStart",
                      "-hookDllPath", str(hlae / "x64" / "AfxHookSource2.dll"),
                      "-programPath", str(cs2 / "game" / "bin" / "win64" / "cs2.exe"),
                      "-cmdLine", cmdline,
                      "-addEnv", f"USRLOCALCSGO={cfg_home}"])


def spec_cmds(c: dict) -> list[str]:
    """Камера от первого лица на игрока (в CS2 игрок выбирается по нику)."""
    name = re.sub(r'[";]', "", c["name"])
    return [f'spec_player "{name}"', "spec_mode 1"]


def record_clips(con: Console, demo_rel: str, clips: list[dict], raw: Path, fps: int, hud: str) -> int:
    """Открывает демку и по очереди записывает клипы. Возвращает, сколько записано."""
    con.quiet(6)                                   # даём главному меню догрузиться
    hud_cmds = {"full": ["cl_draw_only_deathnotices 0", "cl_drawhud 1"],
                "killfeed": ["cl_drawhud 1", "cl_draw_only_deathnotices 1"],
                "none": ["cl_drawhud 0"]}[hud]
    con.cmd(f'mirv_streams record name "{raw.resolve().as_posix()}"',
            f"mirv_streams record fps {fps}",
            "mirv_streams record screen enabled 1",
            "mirv_streams record screen settings afxFfmpegYuv420p",
            "mirv_streams record startMovieWav 1",
            "demo_ui_mode 0", "spec_show_xray 0", "r_show_build_info 0", "volume 0.5", "snd_mute_losefocus 0",
            "cl_hud_telemetry_frametime_show 0", "cl_hud_telemetry_ping_show 0",
            "cl_hud_telemetry_net_misdelivery_show 0", "cl_hud_telemetry_net_quality_graph_show 0",
            "cl_hud_telemetry_serverrecvmargin_graph_show 0",
            *hud_cmds)
    say("Открываю демку…")
    con.cmd(f'playdemo "{demo_rel}"')
    if not con.wait_for(r"Demo Skipping finished|Host activate: Playing Demo", 120):
        raise RuntimeError("Демка не открылась за 2 минуты")
    con.quiet(8)

    done = 0
    for i, c in enumerate(clips):
        say(f"  [{i + 1}/{len(clips)}] раунд {c['round'] + 1}  {'+'.join(c['types'])}  {c['name']}  ({c['length']:.0f} с)…")
        for j, (start, end) in enumerate(c["segs"]):
            land = max(start - int(LEAD * TICKRATE), 1)
            con.cmd("demo_pause", "mirv_cmd clear", "mirv_cmd enabled 1", "demo_timescale 1", f"demo_gototick {land}")
            if not con.wait_for(r"Demo Skipping finished", 90):
                raise RuntimeError("Перемотка демки не закончилась")
            con.quiet(1.0)                         # игроки прогрузились — можно ставить камеру
            marker = f"NUGA_CLIP_DONE_{i}_{j}"
            for t in (land + 48, start - 48, start - 8):       # повторяем: после перемотки камера может сброситься
                for line in spec_cmds(c):
                    con.cmd(f"mirv_cmd addAtTick {t} {line}")
            con.cmd(*spec_cmds(c),
                    f"mirv_cmd addAtTick {start} mirv_streams record start",
                    f"mirv_cmd addAtTick {end} mirv_streams record end",
                    f"mirv_cmd addAtTick {end + 2} echo {marker}",
                    "demo_resume")
            # Запись идёт не в реальном времени (игра рисует каждый кадр), поэтому ждём с большим запасом
            if not con.wait_for(marker, 60 + (LEAD + (end - start) / TICKRATE) * 12):
                con.cmd("mirv_streams record end")
                raise RuntimeError("Клип не дописался — запись остановлена")
            con.cmd("demo_pause")
            con.quiet(1.0)
        done += 1
    return done


def record(args):
    demo = Path(args.demo)
    if not demo.exists():
        sys.exit(f"Нет файла демки: {demo}")
    ffmpeg_bin()
    cs2 = find_cs2(args.cs2)
    hlae = find_hlae(args.hlae)
    if running("cs2.exe"):
        sys.exit("CS2 уже запущена — закрой её и повтори (нужен запуск через HLAE).")
    try:
        width, height = (int(x) for x in args.res.lower().split("x"))
    except ValueError:
        sys.exit("Разрешение пиши так: --res 1920x1080")

    mid = file_id(demo)
    work = OUT / mid
    work.mkdir(parents=True, exist_ok=True)
    target = cs2 / "game" / "csgo" / "nuga" / f"{mid}.dem"
    if not target.exists():
        say("Копирую демку в папку CS2…")
        unpack_demo(demo, target)

    data = load_analysis(mid, target)
    types = {t.strip().upper().replace("V", "v") for t in args.types.split(",")} if args.types else None
    clips = build_clips(data, types, args.player, args.max, args.min_kills)
    if not clips:
        names = ", ".join(p["name"] for p in data["players"])
        sys.exit("Подходящих моментов нет. Попробуй --min-kills 2 (или 1 — все убийства), другой --player.\n"
                 f"Игроки в демке: {names}")

    total = sum(c["length"] for c in clips)
    say(f"Матч {mid} ({data.get('map')}): {len(clips)} клип(ов), ~{total:.0f} с видео")
    for c in clips:
        say(f"  {c['index'] + 1:2d}. раунд {c['round'] + 1:2d}  {'+'.join(c['types']):8s} {c['name']:<20s} "
            f"{c['length']:4.0f} с")
    if args.dry_run:
        return

    error = capture(cs2, hlae, f"nuga/{mid}", clips, work, data.get("map"), args.fps, args.hud, width, height)
    if error:
        say(f"\nОШИБКА: {error}")
    assemble(work, args.crf, args.no_montage, args.keep_raw)


CRASH_HINT = ("CS2 вылетела при открытии демки — игра не может прочитать именно этот файл (бывает с отдельными "
              "демками, HLAE тут ни при чём). Проверь, открывается ли демка в самой CS2 (консоль: playdemo). "
              "Если нет — клип из этого матча сделать не выйдет, пока Valve не починит.")


def capture(cs2: Path, hlae: Path, demo_rel: str, clips: list[dict], work: Path, map_name, fps: int, hud: str,
            width: int, height: int) -> str | None:
    """Запускает CS2, записывает клипы в work/raw и закрывает игру. Возвращает текст ошибки или None."""
    raw = work / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    raw.mkdir(parents=True)
    (work / "manifest.json").write_text(json.dumps(
        {"map": map_name, "fps": fps, "clips": clips}, ensure_ascii=False, indent=2), encoding="utf-8")

    launch_cs2(cs2, hlae, width, height)
    con = None
    error = None
    try:
        con = Console(NETCON_PORT)
        con.log = open(work / "console.log", "w", encoding="utf-8", errors="replace")
        done = record_clips(con, demo_rel, clips, raw, fps, hud)
        say(f"Записано клипов: {done}")
    except RuntimeError as e:
        error = str(e)
        time.sleep(3)
        if "пропала" in error or not running("cs2.exe"):
            error = CRASH_HINT
    finally:
        if con:
            try:
                con.cmd("mirv_streams record end", "disconnect", "quit")
            except OSError:
                pass
            if con.log:
                con.log.close()
        end = time.time() + 25                      # ждём, пока игра закроется и ffmpeg допишет файлы
        while running("cs2.exe") and time.time() < end:
            time.sleep(1)
        if running("cs2.exe"):                      # иногда CS2 зависает при выходе — закрываем сами
            subprocess.run(["taskkill", "/F", "/IM", "cs2.exe"], capture_output=True)
    return error


# ---------- сборка роликов ----------

VIDEO_EXT = (".mp4", ".mkv", ".mov", ".avi")


def find_takes(raw: Path) -> list[Path]:
    """HLAE на каждый record start создаёт папку takeNNNN — по порядку записи."""
    return sorted([p for p in raw.rglob("*") if p.is_dir() and re.fullmatch(r"take\d+", p.name)],
                  key=lambda p: int(p.name[4:]))


def finish(args):
    if not assemble(OUT / args.match, args.crf, args.no_montage, args.keep_raw):
        sys.exit(1)


def assemble(work: Path, crf: int = 18, no_montage: bool = False, keep_raw: bool = False) -> list[Path]:
    """Собирает mp4 из записей в work/raw по списку из manifest.json. Возвращает готовые файлы."""
    man_path = work / "manifest.json"
    if not man_path.exists():
        say(f"Нет {man_path} — сначала python clips3d.py record")
        return []
    man = json.loads(man_path.read_text(encoding="utf-8"))
    clips = man["clips"]
    ff = ffmpeg_bin()

    takes = find_takes(work / "raw")
    if not takes:
        say(f"В {work / 'raw'} нет записей — запись в CS2 не прошла (см. {work / 'console.log'}).")
        return []

    say("Собираю ролики…")
    done = []
    pos = 0
    for c in clips:
        mine, pos = takes[pos:pos + len(c["segs"])], pos + len(c["segs"])       # записи идут по порядку отрезков
        parts = []
        for take in mine:
            files = sorted(p for p in take.rglob("*") if p.is_file())
            video = next((p for p in files if p.suffix.lower() in VIDEO_EXT), None)
            audio = next((p for p in files if p.suffix.lower() == ".wav"), None)
            if video and audio and video.stat().st_size > 10_000:
                parts.append((video, audio))
        if not parts or len(parts) != len(c["segs"]):
            say(f"  ! {c['file']}: записалось не всё, пропускаю")
            continue
        out = work / c["file"]
        cmdline = [ff, "-y", "-loglevel", "error"]
        for video, audio in parts:
            cmdline += ["-i", str(video), "-i", str(audio)]
        # Склеиваем отрезки клипа (видео из HLAE + звук отдельным файлом)
        streams = "".join(f"[{2 * k}:v:0][{2 * k + 1}:a:0]" for k in range(len(parts)))
        cmdline += ["-filter_complex", f"{streams}concat=n={len(parts)}:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
                    "-r", str(man["fps"]), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out)]
        subprocess.run(cmdline, check=True)
        done.append(out)
        say(f"  ✓ {out.name}")

    if len(done) > 1 and not no_montage:
        lst = work / "concat.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in done), encoding="utf-8")
        montage = work / "montage.mp4"
        # Все куски уже одного формата — склеиваем без пережатия
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", "-movflags", "+faststart", str(montage)], check=True, cwd=work)
        lst.unlink()
        say(f"  ✓ {montage.name} — все моменты подряд")

    if not keep_raw and done and len(done) == len(clips):     # сырые записи удаляем, только если всё собралось
        shutil.rmtree(work / "raw", ignore_errors=True)
    say(f"\nГотово: {work}" if done else "\nНи одного ролика не получилось.")
    return done


# ---------- командная строка ----------

def main():
    ap = argparse.ArgumentParser(description="Клипы хайлайтов из CS2 (HLAE + ffmpeg)")
    sub = ap.add_subparsers(dest="step", required=True)

    p = sub.add_parser("record", help="записать хайлайты демки в CS2 и собрать mp4")
    p.add_argument("--demo", required=True, help="файл демки (.dem / .dem.gz / .dem.zst)")
    p.add_argument("--player", help="только этот игрок (часть ника)")
    p.add_argument("--types", help="например ACE,4K,1v3 (по умолчанию все)")
    p.add_argument("--min-kills", type=int, default=3, help="мульти-килл от стольких убийств за раунд (3; можно 2 или 1)")
    p.add_argument("--max", type=int, help="не больше N самых крутых моментов")
    p.add_argument("--res", default="1920x1080", help="размер видео (по умолчанию 1920x1080)")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--hud", choices=["full", "killfeed", "none"], default="full",
                   help="что оставить на экране: весь интерфейс, только киллфид или ничего")
    p.add_argument("--crf", type=int, default=18, help="качество x264: меньше — лучше (18 почти без потерь)")
    p.add_argument("--no-montage", action="store_true", help="не склеивать общий ролик")
    p.add_argument("--keep-raw", action="store_true", help="не удалять сырые записи HLAE")
    p.add_argument("--dry-run", action="store_true", help="только показать список моментов, игру не запускать")
    p.add_argument("--cs2", help="папка «Counter-Strike Global Offensive» (обычно находится сама)")
    p.add_argument("--hlae", help="папка HLAE (обычно находится сама)")
    p.set_defaults(func=record)

    f = sub.add_parser("finish", help="заново собрать mp4 из уже записанных кусков")
    f.add_argument("--match", required=True, help="id матча — имя папки в clips3d")
    f.add_argument("--crf", type=int, default=18)
    f.add_argument("--no-montage", action="store_true")
    f.add_argument("--keep-raw", action="store_true")
    f.set_defaults(func=finish)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
