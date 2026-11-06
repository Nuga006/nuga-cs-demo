# Nuga CS Demo — 3D-клипы хайлайтов из самой CS2 (через HLAE + ffmpeg).
#
# Запускать на компьютере, где установлены CS2, HLAE и ffmpeg (Windows).
# Работает в два шага:
#
#   1) python clips3d.py prepare --match <id матча> --demo <файл демки>
#      → копирует демку в папку CS2 и пишет конфиг nuga_clips.cfg:
#        CS2 сама перематывает демку к каждому хайлайту, ставит камеру от лица
#        игрока и пишет видео через HLAE (mirv_streams).
#      Потом: запустить CS2 через HLAE → в консоли CS2: exec nuga_clips
#
#   2) python clips3d.py finish --match <id матча>
#      → забирает записанные куски, делает из них mp4 с понятными именами
#        (R07_ACE_nick.mp4) и общий ролик montage.mp4.
#
# Хайлайты берутся из уже сохранённого разбора matches/<id>.json.gz —
# те же ACE / 4K / 3K / клатчи, что видны на сайте.

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
MATCHES = BASE / "matches"
OUT = BASE / "clips3d"                 # сюда пишутся записи и готовые ролики (в .gitignore)

TICKRATE = 64                          # демки CS2 / FACEIT — 64 тика в секунду
STEAM64_BASE = 76561197960265728       # SteamID64 − это число = account id

# Сколько секунд захватывать вокруг момента
PRE_MULTI = 4.0      # до первого убийства мульти-килла
POST_MULTI = 2.0     # после последнего убийства
PRE_CLUTCH = 2.0     # до начала клатча (когда игрок остался один)
POST_CLUTCH = 1.5    # после конца раунда
MAX_CLIP = 75.0      # длиннее не пишем (долгие клатчи обрезаются с начала)

ORDER = {"ACE": 0, "1v5": 1, "1v4": 2, "4K": 3, "1v3": 4, "3K": 5, "1v2": 6, "1v1": 7}

DEFAULT_CS2 = r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive"


# ---------- общее ----------

def load_match(match: str) -> tuple[str, dict]:
    """Принимает id матча (12 символов) или путь к <id>.json.gz."""
    p = Path(match)
    if not p.exists():
        p = MATCHES / f"{match}.json.gz"
    if not p.exists():
        sys.exit(f"Не нашёл разбор: {p}\nСначала разбери демку на сайте, чтобы появился matches/<id>.json.gz")
    with gzip.open(p, "rt", encoding="utf-8") as f:
        data = json.load(f)
    mid = p.name.split(".")[0]
    return mid, data


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_")
    return s[:24] or "player"


def cs2_dir(arg: str | None) -> Path:
    d = Path(arg or os.environ.get("CS2_DIR") or DEFAULT_CS2)
    csgo = d / "game" / "csgo"
    if not csgo.is_dir():
        sys.exit(f"Не нашёл папку CS2: {csgo}\nУкажи путь: --cs2 \"...\\Counter-Strike Global Offensive\" "
                 "(или переменную CS2_DIR в .env / окружении)")
    return d


# ---------- 1. какие моменты записывать ----------

def build_clips(data: dict, types: set[str] | None, player: str | None, limit: int | None) -> list[dict]:
    players = data["players"]
    rounds = data["replay"]["rounds"]
    kill_events = data.get("kill_events", [])

    clips = []
    for h in data["replay"].get("highlights", []):
        if types and h["type"] not in types:
            continue
        pi, ri = h["player"], h["round"]
        p = players[pi]
        if player and player.lower() not in p["name"].lower():
            continue
        r = rounds[ri]
        if h["type"].startswith("1v"):
            start = h["tick"] - PRE_CLUTCH * TICKRATE
            end = r["end"] + POST_CLUTCH * TICKRATE
        else:
            my_kills = [e[1] for e in kill_events if e[0] == ri and e[2] == pi]
            first = min(my_kills, default=h["tick"])
            last = max(my_kills, default=h["tick"])
            start = first - PRE_MULTI * TICKRATE
            end = last + POST_MULTI * TICKRATE
        start = max(int(start), r["start"])
        end = int(end)
        if end - start > MAX_CLIP * TICKRATE:
            start = end - int(MAX_CLIP * TICKRATE)
        clips.append({
            "round": ri, "player": pi, "name": p["name"], "steamid": p["steamid"],
            "types": [h["type"]], "start": start, "end": end,
        })

    # Один раунд + один игрок (например 4K и 1v3 сразу) → один клип на общий отрезок
    merged: dict[tuple, dict] = {}
    for c in clips:
        key = (c["round"], c["player"])
        if key in merged:
            m = merged[key]
            m["types"] += c["types"]
            m["start"] = min(m["start"], c["start"])
            m["end"] = max(m["end"], c["end"])
        else:
            merged[key] = c
    clips = list(merged.values())
    for c in clips:
        c["types"].sort(key=lambda t: ORDER.get(t, 9))

    # Если просили не все — берём самые крутые
    if limit:
        clips.sort(key=lambda c: (ORDER.get(c["types"][0], 9), c["round"]))
        clips = clips[:limit]

    # Записываем строго по порядку демки — перемотка только вперёд
    clips.sort(key=lambda c: c["start"])
    # Если отрезки соседних клипов налезают друг на друга — подрезаем, иначе перемотка «назад» собьёт расписание
    for a, b in zip(clips, clips[1:]):
        if b["start"] < a["end"] + 3 * TICKRATE:
            a["end"] = max(a["start"] + TICKRATE, b["start"] - 3 * TICKRATE)
    for i, c in enumerate(clips):
        c["index"] = i
        c["file"] = f"{i + 1:02d}_R{c['round'] + 1:02d}_{'+'.join(c['types'])}_{safe_name(c['name'])}.mp4"
    return clips


# ---------- 2. конфиг для CS2 ----------

def cmd(f, tick: int, command: str):
    # mirv_cmd выполнит команду, когда демка дойдёт до этого тика
    f.write(f'mirv_cmd addAtTick {int(tick)} "{command}"\n')


def write_cfg(path: Path, demo_rel: str, clips: list[dict], fps: int, take_dir: str, hud: str):
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("// Nuga CS Demo — автозапись 3D-хайлайтов. Создано clips3d.py, править не нужно.\n")
        f.write("// Запуск: CS2 через HLAE → консоль → exec nuga_clips\n\n")
        f.write("mirv_cmd clear\n")
        f.write("mirv_cmd enabled 1\n\n")

        f.write("// --- запись: HLAE + встроенный ffmpeg-профиль ---\n")
        f.write(f'mirv_streams record name "{take_dir}"\n')
        f.write(f"mirv_streams record fps {fps}\n")
        f.write("mirv_streams record screen enabled 1\n")
        f.write("mirv_streams record screen settings afxFfmpegYuv420p\n")
        f.write("mirv_streams record startMovieWav 1\n\n")

        f.write("// --- картинка ---\n")
        f.write("demo_timescale 1\n")
        f.write("spec_show_xray 0\n")
        f.write("cl_draw_only_deathnotices 1\n" if hud == "killfeed" else
                "cl_drawhud 0\n" if hud == "none" else "cl_draw_only_deathnotices 0\n")
        f.write("volume 0.6\n\n")

        f.write("// --- расписание ---\n")
        first_jump = 160      # через ~2.5 с после загрузки демки прыгаем к первому моменту
        for i, c in enumerate(clips):
            acc = int(c["steamid"]) - STEAM64_BASE
            land = c["start"] - 2 * TICKRATE          # приземляемся за 2 с, чтобы игра успела прогрузить игроков
            jump_at = first_jump if i == 0 else clips[i - 1]["end"] + 8
            f.write(f"\n// #{i + 1}  раунд {c['round'] + 1}  {'+'.join(c['types'])}  {c['name']}"
                    f"  ({(c['end'] - c['start']) / TICKRATE:.0f} с)\n")
            cmd(f, jump_at, f"demo_gototick {land}")
            # Камера от лица игрока. Пишем несколько способов — какой-то сработает в текущей версии CS2.
            for t in (land + 16, c["start"] - 16):
                cmd(f, t, f"spec_player_by_accountid {acc}")
                cmd(f, t, f"spec_lock_to_accountid {acc}")
                cmd(f, t, "spec_mode 1")
            cmd(f, c["start"], f"echo NUGA clip {i + 1}/{len(clips)} {c['file']}")
            cmd(f, c["start"], "mirv_streams record start")
            cmd(f, c["end"], "mirv_streams record end")

        last = clips[-1]["end"] + 32
        cmd(f, last, "echo NUGA: ALL CLIPS DONE - run: python clips3d.py finish")
        cmd(f, last + 32, "disconnect")
        f.write(f'\nplaydemo "{demo_rel}"\n')


def prepare(args):
    mid, data = load_match(args.match)
    types = {t.strip().upper().replace("V", "v") for t in args.types.split(",")} if args.types else None
    clips = build_clips(data, types, args.player, args.max)
    if not clips:
        sys.exit("В этом матче нет подходящих хайлайтов (проверь --types / --player).")

    game = cs2_dir(args.cs2)
    csgo = game / "game" / "csgo"

    # Демку — в game/csgo/nuga/<id>.dem (распаковываем, если .gz / .zst)
    demo = Path(args.demo)
    if not demo.exists():
        sys.exit(f"Нет файла демки: {demo}")
    if demo.suffix in (".gz", ".zst"):
        from analyzer import prepare_demo
        demo = prepare_demo(demo)

    # Проверяем, что демка от этого же матча: название карты записано в начале файла .dem
    want_map = str(data.get("map") or "")
    with open(demo, "rb") as fh:
        head = fh.read(64 * 1024)
    if want_map and want_map.encode() not in head:
        found = re.search(rb"(de|cs|ar)_[a-z0-9_]{3,20}", head)
        sys.exit(f"Демка не от этого матча!\n"
                 f"  Разбор {mid} — карта {want_map}\n"
                 f"  Файл {args.demo} — карта {found.group().decode() if found else '?'}\n"
                 f"Укажи в --demo ту демку, которую загружал на сайт для этого матча.")

    (csgo / "nuga").mkdir(exist_ok=True)
    target = csgo / "nuga" / f"{mid}.dem"
    shutil.copyfile(demo, target)          # всегда перезаписываем — чтобы не осталась старая чужая демка

    work = OUT / mid
    raw = work / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)

    cfg = csgo / "cfg" / "nuga_clips.cfg"
    write_cfg(cfg, f"nuga/{mid}", clips, args.fps, raw.resolve().as_posix(), args.hud)
    (work / "manifest.json").write_text(json.dumps(
        {"match": mid, "map": data.get("map"), "fps": args.fps, "clips": clips},
        ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(c["end"] - c["start"] for c in clips) / TICKRATE
    print(f"Матч {mid} ({data.get('map')}): {len(clips)} клип(ов), ~{total:.0f} с видео\n")
    for c in clips:
        print(f"  {c['index'] + 1:2d}. раунд {c['round'] + 1:2d}  {'+'.join(c['types']):8s} "
              f"{c['name']:<20s} {(c['end'] - c['start']) / TICKRATE:4.0f} с")
    print(f"\nКонфиг: {cfg}")
    print(f"Демка:  {target}")
    print("\nДальше:")
    print("  1. Открой HLAE → File → Launch CS2 (в Launch options можно добавить -novid -insecure -w 1920 -h 1080)")
    print("  2. В CS2 открой консоль (~) и введи:  exec nuga_clips")
    print("  3. Не трогай мышь, пока в консоли не появится «NUGA: ALL CLIPS DONE»")
    print(f"  4. python clips3d.py finish --match {mid}")


# ---------- 3. сборка роликов ----------

VIDEO_EXT = (".mp4", ".mkv", ".mov", ".avi")


def ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit("Не нашёл ffmpeg. Скачай с https://www.gyan.dev/ffmpeg/builds/ и добавь в PATH "
                 "(или положи ffmpeg.exe рядом с clips3d.py).")
    return exe


def find_takes(raw: Path) -> list[Path]:
    """HLAE на каждый record start создаёт папку takeNNNN — по порядку записи."""
    takes = sorted([p for p in raw.rglob("*") if p.is_dir() and re.fullmatch(r"take\d+", p.name)],
                   key=lambda p: int(p.name[4:]))
    return takes


def finish(args):
    mid, _ = load_match(args.match)
    work = OUT / mid
    man_path = work / "manifest.json"
    if not man_path.exists():
        sys.exit(f"Нет {man_path} — сначала python clips3d.py prepare")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    clips = man["clips"]
    ff = ffmpeg_bin()

    takes = find_takes(work / "raw")
    if not takes:
        sys.exit(f"В {work / 'raw'} нет записей (take0000 …). Запись в CS2 не прошла — см. раздел «Если не работает» в README.")
    if len(takes) != len(clips):
        print(f"Внимание: клипов {len(clips)}, а записей {len(takes)} — сопоставляю по порядку.")

    done = []
    for c, take in zip(clips, takes):
        video = next((p for p in sorted(take.rglob("*")) if p.suffix.lower() in VIDEO_EXT), None)
        audio = next((p for p in sorted(take.rglob("*.wav"))), None)
        if not video:
            print(f"  ! {take.name}: нет видеофайла, пропускаю")
            continue
        out = work / c["file"]
        cmdline = [ff, "-y", "-loglevel", "error", "-i", str(video)]
        if audio:
            cmdline += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
        cmdline += ["-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
                    "-r", str(man["fps"]), "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
        subprocess.run(cmdline, check=True)
        done.append(out)
        print(f"  ✓ {out.name}")

    if len(done) > 1 and not args.no_montage:
        lst = work / "concat.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in done), encoding="utf-8")
        montage = work / "montage.mp4"
        # Все куски уже одного формата — склеиваем без пережатия
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", "-movflags", "+faststart", str(montage)], check=True, cwd=work)
        lst.unlink()
        print(f"  ✓ {montage.name} — все моменты подряд")

    if not args.keep_raw and done:
        shutil.rmtree(work / "raw", ignore_errors=True)
    print(f"\nГотово: {work}")


# ---------- командная строка ----------

def main():
    ap = argparse.ArgumentParser(description="3D-клипы хайлайтов из CS2 (HLAE + ffmpeg)")
    sub = ap.add_subparsers(dest="step", required=True)

    p = sub.add_parser("prepare", help="сделать конфиг записи для CS2")
    p.add_argument("--match", required=True, help="id матча (из ссылки /match/<id>) или путь к .json.gz")
    p.add_argument("--demo", required=True, help="файл демки этого матча (.dem / .dem.gz / .dem.zst)")
    p.add_argument("--cs2", help="папка «Counter-Strike Global Offensive»")
    p.add_argument("--player", help="только этот игрок (часть ника)")
    p.add_argument("--types", help="например ACE,4K,1v3 (по умолчанию все)")
    p.add_argument("--max", type=int, help="не больше N самых крутых моментов")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--hud", choices=["killfeed", "full", "none"], default="killfeed",
                   help="что оставить на экране (по умолчанию только киллфид)")
    p.set_defaults(func=prepare)

    f = sub.add_parser("finish", help="собрать записанные куски в mp4")
    f.add_argument("--match", required=True)
    f.add_argument("--crf", type=int, default=18, help="качество x264: меньше — лучше (18 почти без потерь)")
    f.add_argument("--no-montage", action="store_true", help="не склеивать общий ролик")
    f.add_argument("--keep-raw", action="store_true", help="не удалять сырые записи HLAE")
    f.set_defaults(func=finish)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
