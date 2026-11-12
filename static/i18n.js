// Nuga CS Demo — язык сайта.
// Весь сайт написан по-русски. Этот файл переводит готовую страницу «на лету»: находит русский текст и подставляет
// перевод из словаря ниже. Новый язык — это ещё один словарь в DICT и строчка в LANGS, остальной код менять не нужно.
// Числа в словаре пишутся знаком #: «# матчей» подойдёт к «12 матчей» и превратится в «12 matches».
(() => {
  const LANGS = { ru: "RU", en: "EN" };
  const LOCALE = { ru: "ru-RU", en: "en-GB" };

  const EN = {
    // ----- Шапка и меню -----
    "Мой ник": "My nickname",
    "например Nuga_006": "e.g. Nuga_006",
    "Войти через Steam": "Sign in with Steam",
    "Войти": "Sign in",
    "Выйти": "Sign out",
    "Матчи": "Matches",
    "‹ Матчи": "‹ Matches",
    "Статистика": "Stats",
    "Рекорды": "Records",
    "Клипы": "Clips",
    "Лента": "Feed",
    "Профиль": "Profile",
    "Загрузить демо": "Upload demo",
    "⇪ Загрузить демо": "⇪ Upload demo",
    "Исследовать": "Explore",
    "Сравнение": "Compare",
    "Поиск игрока": "Player search",
    "Ещё": "More",
    "Наш Телеграм": "Our Telegram",
    "Конфиденциальность": "Privacy",
    "«Конфиденциальность»": "Privacy",
    "Nuga CS Demo · не связан с Valve и FACEIT": "Nuga CS Demo · not affiliated with Valve or FACEIT",
    "не связан с Valve и FACEIT": "not affiliated with Valve or FACEIT",
    "счёт и подсветка — со стороны": "score and highlighting from the side of",
    "введите, чтобы видеть счёт со своей стороны": "enter it to see scores from your side",
    "FACEIT # ур. ·": "FACEIT lvl # ·",
    "FACEIT - ур. ·": "FACEIT lvl - ·",
    "FACEIT не найден": "FACEIT not found",
    "Монеты": "Coins",
    "Мой профиль": "My profile",
    "Уведомления": "Notifications",
    "Закрыть": "Close",
    "Скрыть": "Hide",
    "Язык сайта": "Site language",
    "Не получилось войти через Steam — попробуйте ещё раз.": "Steam sign-in failed — please try again.",

    // ----- Установка приложения -----
    "Nuga CS Demo на телефоне": "Nuga CS Demo on your phone",
    "Установите как приложение — иконка на главном экране и полный экран.": "Install it as an app — home screen icon and full screen.",
    "Установить": "Install",
    "Нажмите": "Tap",
    "Поделиться": "Share",
    "⬆︎ внизу Safari →": "⬆︎ at the bottom of Safari →",
    "«На экран Домой»": "“Add to Home Screen”",

    // ----- Монеты -----
    "Загружаем...": "Loading...",
    "Не удалось загрузить баланс": "Could not load the balance",
    "Забрать ежедневный бонус +#": "Claim daily bonus +#",
    "Бонус уже получен — приходите завтра": "Bonus already claimed — come back tomorrow",
    "Бонус сегодня уже получен — приходите завтра": "Bonus already claimed today — come back tomorrow",
    "Разбор новой демки": "New demo analysis",
    "Открыть уже разобранный матч": "Open an already analysed match",
    "бесплатно": "free",
    "Ежедневный бонус": "Daily bonus",
    "Подарок при регистрации": "Sign-up gift",
    "Подарок за регистрацию": "Sign-up gift",
    "История": "History",
    "Ошибка": "Error",

    // ----- Матчи -----
    "Обновить список с FACEIT": "Refresh the list from FACEIT",
    "⟳ Обновить": "⟳ Refresh",
    "Все": "All",
    "Разобранные": "Analysed",
    "Неразобранные": "Not analysed",
    "Карта": "Map",
    "Все карты": "All maps",
    "Сортировка": "Sort",
    "Сначала новые": "Newest first",
    "Сначала старые": "Oldest first",
    "По рейтингу": "By rating",
    "Время": "Time",
    "Счёт": "Score",
    "Рейтинг": "Rating",
    "Хайлайты": "Highlights",
    "HLTV Rating 1.0 — есть у разобранных матчей": "HLTV Rating 1.0 — available for analysed matches",
    "Разобрано матчей: #": "Matches analysed: #",
    "Не удалось загрузить список матчей": "Could not load the match list",
    "Войдите через Steam — здесь появятся ваши матчи FACEIT и разборы.": "Sign in with Steam — your FACEIT matches and analyses will appear here.",
    "Пока нет разобранных матчей — загрузите демку.": "No analysed matches yet — upload a demo.",
    "Матчей не найдено.": "No matches found.",
    "Хайлайтов в матче": "Highlights in the match",
    "Удалить разбор, чтобы загрузить демку заново": "Delete the analysis to upload the demo again",
    "Найти демку этого матча и разобрать": "Find this match's demo and analyse it",
    "Загрузить": "Upload",
    "Загрузить ·": "Analyse ·",
    "Комната ↗": "Room ↗",
    "Загружен": "Uploaded",
    "· Матчей: #": "· Matches: #",
    "Сегодня": "Today",
    "Вчера": "Yesterday",
    "Без даты": "No date",
    "Разбираю…": "Analysing…",
    "⏳ Ищу демку и разбираю матч — это может занять около минуты…": "⏳ Looking for the demo and analysing the match — this can take about a minute…",
    "Нет связи с сервером": "No connection to the server",
    "Жду демку… (выбрать файл)": "Waiting for the demo… (choose a file)",
    "📥 Демки этого матча нет в «Загрузках». Откройте": "📥 This match's demo is not in Downloads. Open the",
    "комнату матча ↗": "match room ↗",
    "и нажмите «Watch demo» — как только файл скачается, разбор начнётся сам.": "and click “Watch demo” — the analysis starts by itself once the file is downloaded.",
    "Не удалось разобрать демку": "Could not analyse the demo",
    "Победа": "Win",
    "Поражение": "Loss",
    "Ничья": "Draw",
    "# раундов": "# rounds",
    "Моя команда": "My team",
    "Соперники": "Opponents",
    "Команда #": "Team #",

    // ----- Статистика -----
    "По всем разобранным матчам, где вы играли": "Across all analysed matches you played in",
    "Войдите через Steam — здесь появится ваша статистика по всем матчам.": "Sign in with Steam — your stats across all matches will appear here.",
    "Пока нет разобранных матчей с вашим ником — загрузите первую демку.": "No analysed matches with your nickname yet — upload your first demo.",
    "Отлично": "Excellent", "Хорошо": "Good", "Средне": "Average", "Плохо": "Poor",
    "Общее": "General",
    "Общая оценка игры по формуле HLTV. 1.00 — средний уровень.": "Overall performance by the HLTV formula. 1.00 is average.",
    "Убийства, делённые на смерти.": "Kills divided by deaths.",
    "Убийств за раунд.": "Kills per round.",
    "Средний урон за раунд.": "Average damage per round.",
    "Хедшоты, %": "Headshots, %",
    "Доля убийств в голову.": "Share of headshot kills.",
    "Раунды, где вы убили, ассистнули, выжили или вас разменяли.": "Rounds where you got a kill, an assist, survived or were traded.",
    "Дуэли": "Duels",
    "Открывающие дуэли, %": "Opening duels, %",
    "Сколько первых дуэлей раунда вы выиграли.": "How many opening duels you won.",
    "Размены, %": "Trades, %",
    "Доля ваших убийств, которыми вы отомстили за тиммейта в течение 5 секунд.": "Share of your kills that avenged a teammate within 5 seconds.",
    "Вас разменяли, %": "You were traded, %",
    "Доля ваших смертей, за которые тиммейт отомстил в течение 5 секунд.": "Share of your deaths avenged by a teammate within 5 seconds.",
    "Стрельба": "Shooting",
    "Точность, %": "Accuracy, %",
    "Попадания по противникам из всех выстрелов (без гранат и ножа).": "Hits on enemies out of all shots (no grenades or knife).",
    "Убийств за матч": "Kills per match",
    "Среднее число убийств за матч.": "Average kills per match.",
    "Урон гранатами за матч": "Utility damage per match",
    "Средний урон HE и молотовами за матч.": "Average HE and molotov damage per match.",
    "Мульти-киллы": "Multi-kills",
    "Раунды с двумя убийствами.": "Rounds with two kills.",
    "Раунды с тремя убийствами.": "Rounds with three kills.",
    "Раунды с четырьмя убийствами.": "Rounds with four kills.",
    "Эйсы": "Aces",
    "Раунды, где вы убили всю команду соперника.": "Rounds where you killed the whole enemy team.",
    "Особые убийства": "Special kills",
    "Без прицела": "No-scope",
    "Убийства из снайперской винтовки без прицела.": "Sniper rifle kills without scoping.",
    "Сквозь стены": "Wallbang",
    "Убийства прострелом.": "Kills through walls.",
    "Сквозь смок": "Through smoke",
    "Убийства через дым.": "Kills through smoke.",
    "В ослеплении": "While blind",
    "Убийства, когда вы были ослеплены.": "Kills while you were flashed.",
    "Бомба и MVP": "Bomb & MVP",
    "Сколько раз вы были лучшим игроком раунда.": "How many times you were the round MVP.",
    "Заложено бомб": "Bombs planted",
    "Сколько раз вы поставили бомбу.": "How many times you planted the bomb.",
    "Разминировано": "Defused",
    "Сколько раз вы разминировали бомбу.": "How many times you defused the bomb.",
    "Клатчи, %": "Clutches, %",
    "Клатчи": "Clutches",
    "Выигранные раунды, где вы остались один против нескольких.": "Rounds you won when left alone against several enemies.",
    "Матчей:": "Matches:",
    "#% побед": "#% wins",
    "за все": "over all",
    "за последние #": "over the last #",
    "10 уровень": "Level 10",
    "достигнут!": "reached!",
    "До # уровня:": "To level #:",
    "# ур.": "lvl #",
    "# матчей": "# matches",
    "# матч": "# match",
    "# матча": "# matches",
    "Тренд": "Trend",
    "по # из # матчей": "from # of # matches",
    "нет данных в старых разборах": "no data in old analyses",
    "Попытки клатчей считаются в # из # матчей — старые разборы их не содержат.": "Clutch attempts are counted in # of # matches — old analyses don't have them.",
    "Тренд по матчам": "Trend by match",
    "Карты: победы–поражения и средний Rating": "Maps: wins–losses and average Rating",
    "Нет данных": "No data",
    "График по матчам": "Chart by match",
    "Побед #%": "Wins #%",

    // ----- Рекорды -----
    "Личные рекорды по всем разобранным матчам. Нажмите на карточку, чтобы открыть матч.": "Personal records across all analysed matches. Click a card to open the match.",
    "Войдите через Steam, чтобы увидеть свои рекорды.": "Sign in with Steam to see your records.",
    "По # матчу": "From # match",
    "По # матчам": "From # matches",
    "Больше всего убийств": "Most kills",
    "Больше всего хедшотов": "Most headshots",
    "Самый высокий HS%": "Highest HS%",
    "Лучший K/D": "Best K/D",
    "Самый высокий ADR": "Highest ADR",
    "Самый высокий рейтинг": "Highest rating",
    "Больше всего ассистов": "Most assists",
    "Больше всего первых убийств": "Most first kills",
    "Больше всего клатчей": "Most clutches",
    "Больше всего урона гранатами": "Most utility damage",
    "Лучший KAST": "Best KAST",
    "Больше всего мульти-киллов": "Most multi-kills",
    "Пока нет данных": "No data yet",

    // ----- Клипы -----
    "Все яркие моменты из ваших разобранных матчей": "All the highlights from your analysed matches",
    "Мои": "Mine",
    "Все игроки": "All players",
    "все игроки": "all players",
    "Войдите через Steam, чтобы увидеть клипы своих матчей.": "Sign in with Steam to see clips from your matches.",
    "# ваших моментов": "# of your moments",
    "# всего в # матчах": "# total in # matches",
    "Нет клипов под этот фильтр.": "No clips match this filter.",
    "Пока нет клипов. Если матчи уже разобраны раньше — загрузите демку ещё раз, разбор обновится бесплатно.": "No clips yet. If your matches were analysed earlier, upload the demo again — the analysis updates for free.",
    "раунд #": "round #",
    "Раунд #": "Round #",
    "Сохранить в профиль": "Save to profile",

    // ----- Лента и профиль -----
    "Клипы, которые опубликовали игроки": "Clips published by players",
    "Подписки": "Following",
    "Подписчики": "Followers",
    "публикации": "posts",
    "подписчики": "followers",
    "подписки": "following",
    "Подписаться": "Follow",
    "✓ Вы подписаны": "✓ Following",
    "↗ Поделиться профилем": "↗ Share profile",
    "＋ Опубликовать клип": "＋ Publish a clip",
    "Опубликовать клип": "Publish a clip",
    "Опубликовать": "Publish",
    "Опубликованные": "Published",
    "Личные": "Private",
    "В личные": "To Private",
    "Изменить подпись": "Edit caption",
    "Удалить клип": "Delete clip",
    "Клип": "Clip",
    "Игрок": "Player",
    "Войдите через Steam — у вас появится профиль с клипами, подписчиками и подписками.": "Sign in with Steam to get a profile with clips, followers and following.",
    "Здесь лежат клипы, которые видите только вы.": "Clips that only you can see live here.",
    "Сохраняйте моменты кнопкой ＋ в «Клипах» и на вкладке «Хайлайты» матча.": "Save moments with the ＋ button in Clips and on a match's Highlights tab.",
    "Вы ещё ничего не опубликовали.": "You haven't published anything yet.",
    "Игрок пока не опубликовал клипы.": "This player hasn't published any clips yet.",
    "✅ Ссылка скопирована": "✅ Link copied",
    "Скопируйте ссылку:": "Copy the link:",
    "Войдите через Steam, чтобы подписываться.": "Sign in with Steam to follow players.",
    "Пока нет подписчиков.": "No followers yet.",
    "Пока нет подписок.": "Not following anyone yet.",
    "Удалить этот клип из профиля?": "Delete this clip from your profile?",
    "Подпись к клипу (можно оставить пустой):": "Clip caption (can be left empty):",
    "✅ Клип опубликован — его видят все, у кого есть ссылка на профиль.": "✅ Clip published — anyone with your profile link can see it.",
    "✅ Клип опубликован в профиле.": "✅ Clip published to your profile.",
    "✅ Клип сохранён в «Личные».": "✅ Clip saved to Private.",
    "Открыть профиль": "Open profile",
    "Войдите через Steam, чтобы сохранять клипы в профиль": "Sign in with Steam to save clips to your profile",
    "В «Личных» уже лежит клипов: # — их можно опубликовать на вкладке «Личные».": "You already have # clip(s) in Private — publish them on the Private tab.",
    "Моменты из ваших разобранных матчей": "Moments from your analysed matches",
    "Новых моментов нет. Разберите матч — эйсы, 4K, 3K и клатчи появятся здесь сами.": "No new moments. Analyse a match — aces, 4Ks, 3Ks and clutches will show up here.",
    "✓ Готово": "✓ Done",
    "Открыть момент в матче": "Open the moment in the match",
    "Открыть матч": "Open match",
    "⬇ Скачать видео": "⬇ Download video",
    "Здесь появятся клипы игроков, на которых вы подписаны.": "Clips from players you follow will appear here.",
    "Войдите через Steam и подпишитесь на игроков — их клипы появятся здесь.": "Sign in with Steam and follow players — their clips will appear here.",
    "Пока никто не опубликовал клипы. Будьте первым — откройте свой профиль и нажмите «Опубликовать клип».": "Nobody has published clips yet. Be the first — open your profile and click “Publish a clip”.",
    "✅ Уведомления приходят в Telegram": "✅ Notifications are sent to Telegram",
    "Отключить": "Turn off",
    "✈ Уведомления в Telegram": "✈ Telegram notifications",
    "Уведомления в Telegram": "Telegram notifications",
    "новые подписчики и клипы — сообщением от бота": "new followers and clips as a bot message",
    "Откройте бота и нажмите «Запустить» (Start) — после этого новые подписчики и клипы будут приходить вам в Telegram.": "Open the bot and press Start — new followers and clips will then be sent to you in Telegram.",
    "✈ Открыть бота": "✈ Open the bot",
    "подписался на вас": "started following you",
    "опубликовал клип": "published a clip",
    "Не удалось загрузить уведомления": "Could not load notifications",
    "Пока пусто. Здесь появятся новые подписчики и клипы тех, на кого вы подписаны.": "Nothing yet. New followers and clips from players you follow will appear here.",
    "только что": "just now",
    "# мин назад": "# min ago",
    "# ч назад": "# h ago",
    "# дн назад": "# d ago",
    "Профиль не найден": "Profile not found",
    "Клип не найден": "Clip not found",
    "На себя подписаться нельзя": "You can't follow yourself",
    "Видео не найдено": "Video not found",
    "В этом матче нет такого момента": "There is no such moment in this match",
    "В профиле уже # клипов — удалите лишние": "Your profile already has # clips — delete some first",
    "Telegram-бот пока не подключён": "The Telegram bot is not connected yet",
    "＋ Сохранить в профиль": "＋ Save to profile",
    "✓ В профиле": "✓ In profile",
    "3D-клип": "3D clip",

    // ----- Сравнение -----
    "До 5 игроков FACEIT — по последним 20 матчам каждого": "Up to 5 FACEIT players — over each one's last 20 matches",
    "Основные показатели": "Key stats",
    "Победы, %": "Wins, %",
    "Убийств за раунд": "Kills per round",
    "Командная игра": "Teamplay",
    "Ассистов за матч": "Assists per match",
    "MVP за матч": "MVPs per match",
    "Из разобранных демок": "From analysed demos",
    "ADR (демки)": "ADR (demos)",
    "Игрок не найден": "Player not found",
    "Игрок не найден на FACEIT": "Player not found on FACEIT",
    "Войдите через Steam, чтобы сравнивать игроков.": "Sign in with Steam to compare players.",
    "Вы · # матчей FACEIT · # демок": "You · # FACEIT matches · # demos",
    "# матчей FACEIT": "# FACEIT matches",
    "# демок": "# demos",
    "Вы": "You",
    "лучший по #": "best in #",
    "Убрать из сравнения": "Remove from comparison",
    "Добавить игрока": "Add player",
    "ещё # из #": "# more of #",
    "Добавьте ещё хотя бы одного игрока, чтобы сравнить статистику.": "Add at least one more player to compare stats.",
    "Загружаем статистику...": "Loading stats...",
    "«Из разобранных демок» считается по вашим разобранным матчам, где был этот игрок (число демок — под ником). Если демок нет, там прочерк.": "“From analysed demos” is based on your analysed matches featuring this player (demo count is under the nickname). A dash means there are no demos.",
    "это вы": "that's you",
    "Добавить": "Add",
    "Ник на FACEIT": "FACEIT nickname",
    "Игроки из ваших матчей": "Players from your matches",
    "Разберите пару матчей — здесь появятся ваши тиммейты и соперники.": "Analyse a couple of matches — your teammates and opponents will appear here.",

    // ----- Загрузка -----
    "Демку можно скачать в комнате матча на FACEIT кнопкой «Watch demo»": "Download the demo in the FACEIT match room with the “Watch demo” button",
    "Войдите через Steam, чтобы разбирать демки и видеть свои матчи.": "Sign in with Steam to analyse demos and see your matches.",
    "При регистрации —": "On sign-up —",
    "20 монет": "20 coins",
    "в подарок.": "as a gift.",
    "Выберите файл": "Choose a file",
    "или перетащите его сюда": "or drop it here",
    ".dem, .dem.gz или .dem.zst · до 700 МБ": ".dem, .dem.gz or .dem.zst · up to 700 MB",
    "Разбор новой демки — 2": "New demo analysis — 2",
    ". Уже разобранные матчи открываются бесплатно.": ". Already analysed matches open for free.",
    "Загружаем последний кусочек и разбираем демку... это может занять до минуты": "Uploading the last chunk and analysing the demo... this can take up to a minute",
    "Готово!": "Done!",
    "Открываем матч...": "Opening the match...",
    "Матч не найден": "Match not found",
    "Нужен файл .dem, .dem.gz или .dem.zst": "A .dem, .dem.gz or .dem.zst file is required",
    "Файл слишком большой": "The file is too large",
    "Демка слишком большая": "The demo is too large",
    "Загрузка не найдена — начните заново": "Upload not found — start again",
    "Не хватает монет: разбор стоит #. Заберите ежедневный бонус!": "Not enough coins: an analysis costs #. Claim your daily bonus!",
    "Войдите через Steam, чтобы разбирать демки": "Sign in with Steam to analyse demos",
    "Сервер сейчас занят разбором других демок — попробуйте через пару минут": "The server is busy analysing other demos — try again in a couple of minutes",
    "Слишком много запросов — подождите # сек.": "Too many requests — wait # sec.",
    "Удалить можно только свой разбор": "You can only delete your own analysis",
    "Нет связи с FACEIT": "No connection to FACEIT",
    "У этого матча на FACEIT уже нет демки (они хранятся несколько недель)": "FACEIT no longer has this match's demo (they are kept for a few weeks)",
    "Не удалось скачать демку с FACEIT": "Could not download the demo from FACEIT",

    // ----- Поиск игрока -----
    "Профиль и последние матчи любого игрока FACEIT": "Profile and recent matches of any FACEIT player",
    "Введите ник на FACEIT": "Enter a FACEIT nickname",
    "Найти": "Search",
    "Разбор →": "Analysis →",
    "Выберите скачанную демку этого матча": "Choose the downloaded demo of this match",
    "Разобран": "Analysed",
    "профиль FACEIT ↗": "FACEIT profile ↗",
    "Уровень #": "Level #",
    "Уровень -": "Level -",
    "Чтобы разобрать матч: «Комната ↗» → «Watch demo» скачает демку → нажмите «Загрузить» в строке этого матча.": "To analyse a match: “Room ↗” → “Watch demo” downloads the demo → click “Upload” in that match's row.",
    "Нет матчей CS2": "No CS2 matches",

    // ----- FAQ -----
    "Частые вопросы": "Frequently asked questions",
    "Где взять демку матча?": "Where do I get a match demo?",
    "Откройте матч на FACEIT (кнопка «Комната» в списке матчей), нажмите «Watch demo» — скачается файл": "Open the match on FACEIT (the “Room” button in the match list) and click “Watch demo” — it downloads a",
    ". Его и загружайте, переименовывать не нужно.": " file. Upload it as is, no renaming needed.",
    "Сколько стоит разбор?": "How much does an analysis cost?",
    "Разбор новой демки — 2 монеты. При регистрации дарим 20 монет, каждый день можно забрать бонус +3. Матч, который уже кто-то разобрал, открывается бесплатно.": "A new demo analysis costs 2 coins. You get 20 coins on sign-up and can claim a +3 bonus every day. A match someone has already analysed opens for free.",
    "Что значит Rating, KAST, FK–FD?": "What do Rating, KAST and FK–FD mean?",
    "— общая оценка игры по формуле HLTV, 1.00 — средний уровень.": "— overall performance by the HLTV formula, 1.00 is average.",
    "— процент раундов, где вы убили, ассистнули, выжили или вас разменяли.": "— percentage of rounds where you got a kill, an assist, survived or were traded.",
    "— первые убийства и первые смерти в раундах.": "— first kills and first deaths in rounds.",
    "Можно ли поделиться матчем?": "Can I share a match?",
    "Да — на странице матча есть кнопка «Скопировать ссылку». Смотреть по ссылке можно без входа.": "Yes — the match page has a “Copy link” button. The link works without signing in.",
    "Безопасен ли вход через Steam?": "Is signing in with Steam safe?",
    "Пароль вводится только на сайте Steam. Мы получаем лишь ваш Steam ID — по нему находим профиль FACEIT.": "You enter your password only on the Steam website. We receive just your Steam ID and use it to find your FACEIT profile.",
    "Какие данные вы храните?": "What data do you store?",
    "Steam ID, открытый профиль FACEIT, монеты и разборы матчей. Из демок храним только 6 последних (для 3D-клипов), старые удаляются сами. Паролей мы не видим. Подробно — на странице": "Steam ID, public FACEIT profile, coins and match analyses. We keep only the 6 most recent demos (for 3D clips); older ones are deleted automatically. We never see passwords. Details are on the",
    "Почему матч не открывается в CS2?": "Why won't the match open in CS2?",
    "CS2 открывает только демки текущей версии игры. После крупного обновления старые демки могут перестать запускаться.": "CS2 only opens demos of the current game version. After a major update old demos may stop working.",
    "Аккаунт": "Account",
    "Удалятся аккаунт, монеты, история и список ваших матчей. Разборы матчей останутся — в них статистика всех участников.": "Your account, coins, history and match list will be deleted. Match analyses stay — they contain every participant's stats.",
    "Удалить мой аккаунт": "Delete my account",
    "Точно удалить? Нажмите ещё раз": "Really delete? Click again",
    "Не получилось — попробуйте ещё раз": "That didn't work — try again",

    // ----- Страница матча -----
    "Таблица": "Scoreboard",
    "Раунды": "Rounds",
    "Реплей": "Replay",
    "Статистика игроков": "Player stats",
    "Матрица дуэлей": "Duel matrix",
    "Число слева — сколько раз игрок строки убил игрока столбца, справа — наоборот.": "The left number is how many times the row player killed the column player, the right one is the reverse.",
    "Экономика по раундам": "Economy by round",
    "Высота столбика — стоимость закупки команды": "Bar height is the team's buy value",
    "П": "P", "Э": "E", "Ф": "F",
    "— пистолетка ·": "— pistol ·",
    "— эко ·": "— eco ·",
    "— форс ·": "— force ·",
    "— фулл-бай": "— full buy",
    "Зелёная метка — команда выиграла раунд · клик — открыть раунд в реплее": "Green mark — the team won the round · click to open the round in the replay",
    "Киллфид раунда": "Round killfeed",
    "Пока никого не убили": "No kills yet",
    "заложил бомбу": "planted the bomb",
    "разминировал бомбу": "defused the bomb",
    "Бомба взорвалась": "The bomb exploded",
    "🎬 — скачать 2D-клип момента · 🎮 — 3D-клип: момент из самой CS2": "🎬 — download a 2D clip of the moment · 🎮 — 3D clip: the moment from CS2 itself",
    "Разбор игрока": "Player breakdown",
    "Где убивал": "Kill positions",
    "Где умирал": "Death positions",
    "🔗 Скопировать ссылку на матч": "🔗 Copy match link",
    "🗑 Удалить разбор": "🗑 Delete analysis",
    "Раунды, где игрок убил, ассистнул, выжил или его разменяли": "Rounds where the player got a kill, an assist, survived or was traded",
    "Первые убийства – первые смерти в раунде": "First kills – first deaths in a round",
    "Урон гранатами (HE и молотовы)": "Utility damage (HE and molotovs)",
    "HLTV Rating 1.0: 1.00 — средний уровень": "HLTV Rating 1.0: 1.00 is average",
    "Удалить разбор этого матча?": "Delete this match's analysis?",
    "Матч вернётся в «Неразобранные». Ту же демку можно будет загрузить заново бесплатно.": "The match returns to “Not analysed”. You can upload the same demo again for free.",
    "после #-го раунда · итог #:#": "after round # · total #:#",
    "Выберите игрока": "Choose a player",
    "В списке слева или кликните по нику в таблице статистики — покажем его хитмап, оружие, дуэли и лучшие моменты.": "Pick one in the list on the left or click a nickname in the stats table — we'll show the heatmap, weapons, duels and best moments.",
    "Оружие матча": "Match weapons",
    "Оружие": "Weapons",
    "Лучшие моменты": "Best moments",
    "AI-разбор": "AI review",
    "🤖 Получить советы от AI · #": "🤖 Get tips from AI · #",
    "🤖 Разобрать мою форму · #": "🤖 Review my form · #",
    "AI-разбор формы": "AI form review",
    "AI посмотрит ваши последние # матчей и найдёт, что повторяется: сильные и слабые карты, привычки, тренды.": "AI will look at your last # matches and find what repeats: strong and weak maps, habits, trends.",
    "AI изучает ваши матчи… обычно #–# секунд": "AI is studying your matches… usually #–# seconds",
    "Для разбора формы нужно хотя бы # разобранных матча, в которых вы играли": "A form review needs at least # analysed matches you played in",
    "Не хватает монет: AI-разбор стоит #. Заберите ежедневный бонус!": "Not enough coins: an AI review costs #. Claim your daily bonus!",
    "AI-разбор (повторно — бесплатно)": "AI review (free when reopened)",
    "Среднее по сайту: #": "Site average: #",
    "Гранаты": "Grenades",
    "Брошено смоков": "Smokes thrown",
    "Брошено флешек": "Flashes thrown",
    "Брошено HE": "HE thrown",
    "Брошено молотовов": "Molotovs thrown",
    "Ослеплено врагов": "Enemies flashed",
    "Секунд слепоты врагов": "Enemy blind seconds",
    "Ослеплено своих": "Teammates flashed",
    "Флеш-ассисты": "Flash assists",
    "Урон гранатами": "Utility damage",
    "В скобках — среднее по команде": "In brackets — team average",
    "Этот матч разобран старой версией — загрузите демку снова (бесплатно), чтобы увидеть гранаты.": "This match was analysed by an older version — upload the demo again (free) to see grenades.",
    "Флешек за матч": "Flashes per match",
    "Ослеплено врагов за матч": "Enemies flashed per match",
    "Ослеплено своих за матч": "Teammates flashed per match",
    "Сколько флешек вы бросаете в среднем за матч.": "How many flashes you throw per match on average.",
    "Враги, ослеплённые вашими флешками хотя бы на секунду.": "Enemies blinded by your flashes for at least a second.",
    "Убийства тиммейтов по врагам, которых вы ослепили.": "Teammate kills on enemies you blinded.",
    "Тиммейты, ослеплённые вашими флешками. Чем меньше, тем лучше.": "Teammates blinded by your flashes. Fewer is better.",
    "Этот матч": "This match",
    "Все мои матчи на карте": "All my matches on this map",
    "Собираю ваши матчи на этой карте…": "Collecting your matches on this map…",
    "🖼 Карточка матча": "🖼 Match card",
    "Вы, матчей: #": "You, # matches",
    "смоки": "smokes", "флешки": "flashes", "молотовы": "molotovs",
    "В этом разборе не записано, кто бросал гранаты — загрузите демку снова (бесплатно).": "This analysis doesn't record who threw grenades — upload the demo again (free).",
    "За какую сторону сильнее": "Which side you're stronger on",
    "Победы": "Wins", "Первые дуэли": "Opening duels",
    "Закуп: сколько пользы": "Buys: how much value",
    "Пистолетки": "Pistol rounds", "Эко": "Eco", "Форс": "Force buy", "Полный закуп": "Full buy",
    "Эко — снаряжение дешевле $2000, форс — до $4000, полный — от $4000.": "Eco — equipment under $2000, force — up to $4000, full — $4000 and more.",
    "Когда умирал в раунде": "When you died in the round",
    "Первые 20 секунд": "First 20 seconds", "20–60 секунд": "20–60 seconds", "После минуты": "After a minute",
    "Много ранних смертей — возможно, слишком агрессивные выходы на старте раунда.": "Lots of early deaths — your round-start peeks may be too aggressive.",
    "Время от конца закупки. Всего смертей: #.": "Time from the end of buy time. Total deaths: #.",
    "Стак": "Stack", "Тиммейт": "Teammate", "Матчей": "Matches", "Ваш Rating": "Your Rating",
    "Пока нет тиммейтов, с которыми вы сыграли хотя бы # разобранных матча.": "No teammates with at least # analysed matches together yet.",
    "Лидеры недели": "Leaders of the week",
    "Средний Rating": "Average Rating",
    "Пока никого": "Nobody yet",
    "За последние # дней по всем разобранным матчам сайта. В рейтинге — игроки, сыгравшие хотя бы # матча.": "Last # days across all analysed matches on the site. The rating list includes players with at least # matches.",
    "Не удалось загрузить лидеров": "Couldn't load the leaders",
    "Ачивки": "Achievements",
    "Личные рекорды": "Personal records",
    "Войдите через Steam, чтобы получать ачивки и монеты за них.": "Sign in with Steam to earn achievements and coins for them.",
    "Не удалось загрузить ачивки": "Couldn't load achievements",
    "Награда получена": "Reward claimed",
    "Забрать +#": "Claim +#",
    "Первый разбор": "First analysis", "Разберите свой первый матч": "Analyse your first match",
    "Десятка": "Top ten", "# разобранных матчей": "# analysed matches",
    "Четыре из пяти": "Four of five", "Сделайте 4K": "Get a 4K",
    "Эйс": "Ace", "Убейте всю команду соперника в одном раунде": "Kill the whole enemy team in one round",
    "Клатчер": "Clutcher", "Выиграйте # клатча": "Win # clutches",
    "Ослепитель": "Flashbang master", "# флеш-ассистов": "# flash assists",
    "Солнце в глаза": "Sun in your eyes", "Ослепите # врагов": "Blind # enemies",
    "Звезда матча": "Match star", "Сыграйте матч с рейтингом # и выше": "Play a match with a rating of # or higher",
    "Открывашка": "Opener", "# первых убийств в одном матче": "# opening kills in one match",
    "ПОБЕДА": "VICTORY",
    "ПОРАЖЕНИЕ": "DEFEAT",
    "НИЧЬЯ": "DRAW",
    "ЛУЧШИЙ ИГРОК МАТЧА": "PLAYER OF THE MATCH",
    "AI изучает матч… обычно #–# секунд": "AI is studying the match… usually #–# seconds",
    "AI-разбор не настроен: добавьте ANTHROPIC_API_KEY в файл .env": "AI review is not set up: add ANTHROPIC_API_KEY to the .env file",
    "AI сейчас перегружен — попробуйте через минуту": "AI is busy right now — try again in a minute",
    "AI отказался разбирать этот матч": "AI declined to review this match",
    "AI вернул пустой ответ": "AI returned an empty answer",
    "Нет связи с AI": "No connection to AI",
    "Нет убийств": "No kills",
    "Раунд #: $#": "Round #: $#",
    "все игроки: # убийств на карте": "all players: # kills on the map",
    "все игроки: # смертей на карте": "all players: # deaths on the map",
    "# убийства": "# kills",
    "# убийств": "# kills",
    "клатч # против #": "# vs # clutch",
    "В этом матче не нашлось мульти-киллов и клатчей": "No multi-kills or clutches found in this match",
    "Скачать 2D-клип": "Download 2D clip",
    "3D-клип: записать и показать момент из самой CS2": "3D clip: record and show the moment from CS2 itself",
    "3D-запись из CS2": "3D recording from CS2",
    "Компиляция · раунд · монтаж": "Compilation · round · montage",
    "Этот браузер не умеет записывать видео — попробуйте Chrome": "This browser can't record video — try Chrome",
    "● Идёт запись клипа (~# сек). Не переключайте вкладку.": "● Recording the clip (~# sec). Don't switch tabs.",

    // ----- 3D-запись -----
    "⚙ Записать другое": "⚙ Record another",
    "← Назад к настройкам": "← Back to settings",
    "Показать команды, чтобы открыть момент в CS2 вручную": "Show commands to open the moment in CS2 manually",
    "3D-запись работает только на компьютере, где запущен сайт и установлена CS2.": "3D recording only works on the computer that runs the site and has CS2 installed.",
    "3D-клипы записываются только на компьютере, где запущен сайт": "3D clips are recorded only on the computer that runs the site",
    "Войдите через Steam, чтобы записывать видео из CS2": "Sign in with Steam to record video from CS2",
    "Этот момент": "This moment",
    "Компиляция": "Compilation",
    "все хайлайты одним видео": "all highlights in one video",
    "Раунд целиком": "Whole round",
    "от начала до смерти": "from start to death",
    "Монтаж": "Montage",
    "выбрать убийства": "pick kills",
    "Раунд": "Round",
    "Раунд # — убийств: #": "Round # — kills: #",
    "Убийства: выбрано": "Kills: selected",
    "из #": "of #",
    "Выбрать все": "Select all",
    "Сбросить": "Reset",
    "· в голову": "· headshot",
    "Что записать": "What to record",
    "Качество": "Quality",
    "Частота кадров": "Frame rate",
    "Формат": "Format",
    "Интерфейс (HUD)": "Interface (HUD)",
    "Весь": "Full",
    "Только киллфид": "Killfeed only",
    "Без HUD": "No HUD",
    "Рентген (игроки сквозь стены)": "X-ray (players through walls)",
    "Выкл": "Off",
    "Вкл": "On",
    "Голосовой чат": "Voice chat",
    "Обе команды": "Both teams",
    "Свои": "Teammates",
    "Противники": "Enemies",
    "Камера противника (убийство его глазами)": "Enemy camera (the kill through their eyes)",
    "После каждого убийства": "After each kill",
    "После всех убийств": "After all kills",
    "● Записать": "● Record",
    "Откроется окно CS2 — игра сама покажет и запишет видео. Ничего нажимать не нужно. CS2 и FACEIT AC перед записью закройте.": "A CS2 window will open — the game plays and records the video by itself. You don't need to press anything. Close CS2 and FACEIT AC before recording.",
    "Отметьте хотя бы одно убийство": "Select at least one kill",
    "Запускаю CS2…": "Starting CS2…",
    "Окно CS2 лучше не трогать, пока идёт запись.": "Better not to touch the CS2 window while recording.",
    "Идёт запись…": "Recording…",
    "Не получилось записать видео": "Could not record the video",
    "Копировать": "Copy",
    "Скопируйте:": "Copy:",
    "Уже идёт запись другого клипа — дождитесь её конца": "Another clip is being recorded — wait until it finishes",
    "Слишком длинное видео — выберите меньше моментов": "The video is too long — pick fewer moments",
    "Для такой записи у игрока нет моментов": "The player has no moments for this kind of recording",

    // ----- Главная страница (лендинг) -----
    "Возможности": "Features",
    "Как это работает": "How it works",
    "Открыть приложение": "Open the app",
    "Открыть": "Open",
    "● Разбор матчей CS2": "● CS2 match analysis",
    "разбор матчей CS2": "CS2 match analysis",
    "Твой матч —": "Your match —",
    "как": "in the",
    "на ладони": "palm of your hand",
    "Загрузи демку с FACEIT и через минуту увидишь рейтинг каждого игрока, лучшие моменты, экономику раундов и 2D-реплей всей игры.": "Upload a FACEIT demo and in a minute you'll see every player's rating, the best moments, round economy and a 2D replay of the whole game.",
    "Начать бесплатно →": "Start for free →",
    "Бесплатный старт —": "Free start —",
    "при регистрации и бонус каждый день.": "on sign-up and a bonus every day.",
    "показателей": "metrics",
    "реплей раундов": "round replay",
    "клипы хайлайтов": "highlight clips",
    "Клип готов": "Clip ready",
    "4K · Mirage · раунд 9": "4K · Mirage · round 9",
    "Всё, что было в матче": "Everything that happened in the match",
    "Не нужно пересматривать демку целиком — сайт сам найдёт, что важно.": "No need to rewatch the whole demo — the site finds what matters.",
    "Статистика уровня HLTV": "HLTV-grade stats",
    "Rating, ADR, KAST, entry-дуэли, урон гранатами и матрица дуэлей «кто кого».": "Rating, ADR, KAST, entry duels, utility damage and a who-killed-whom duel matrix.",
    "2D-реплей": "2D replay",
    "Каждый раунд на радаре: движение, взгляд, HP, гранаты, выстрелы и бомба.": "Every round on the radar: movement, view direction, HP, grenades, shots and the bomb.",
    "Эйсы, 4K и выигранные клатчи находятся автоматически — в один клик к моменту.": "Aces, 4Ks and won clutches are found automatically — one click to the moment.",
    "Скачай видео любого хайлайта и отправь друзьям или выложи в сторис.": "Download a video of any highlight and send it to friends or post it to your story.",
    "Экономика": "Economy",
    "Пистолетки, эко, форсы и фулл-баи по раундам — видно, где сломалась игра.": "Pistols, ecos, forces and full buys by round — see where the game broke down.",
    "Твой прогресс": "Your progress",
    "Хитмапы, любимое оружие, винрейт по картам и график рейтинга по матчам.": "Heatmaps, favourite weapons, win rate by map and a rating chart by match.",
    "Три шага": "Three steps",
    "Никаких программ и настроек — всё в браузере, с компьютера или телефона.": "No software or setup — everything in the browser, on a computer or phone.",
    "Найди матч": "Find a match",
    "Введи свой ник FACEIT — увидишь ELO и последние игры со ссылкой на каждую.": "Enter your FACEIT nickname to see your ELO and recent games with a link to each.",
    "Загрузи демку": "Upload the demo",
    "Нажми «Watch demo» на FACEIT и перетащи файл на сайт. Даже 200 МБ — не проблема.": "Click “Watch demo” on FACEIT and drop the file on the site. Even 200 MB is no problem.",
    "Разбирай": "Analyse",
    "Таблица, раунды, реплей и хайлайты готовы. Поделись ссылкой на матч с командой.": "Scoreboard, rounds, replay and highlights are ready. Share the match link with your team.",
    "Готов разобрать свой матч?": "Ready to analyse your match?",
    "Это бесплатно. Первая демка — прямо сейчас.": "It's free. Your first demo — right now.",
    "Открыть Nuga CS Demo →": "Open Nuga CS Demo →",
    "© 2026 Nuga CS Demo · сделано Nuga006": "© 2026 Nuga CS Demo · made by Nuga006",
    "· Проект не связан с Valve и FACEIT.": "· This project is not affiliated with Valve or FACEIT.",
    "✈ Наш Телеграм": "✈ Our Telegram",
  };

  // Фразы с именами и другим меняющимся текстом
  const EN_RX = [
    [/^Ищем (.+)\.\.\.$/, "Searching for $1..."],
    [/^Загружаем (.+)\.\.\.$/, "Uploading $1..."],
    [/^Не удалось удалить: (.+)$/, "Could not delete: $1"],
    [/^Не удалось разобрать демку: (.+)$/, "Could not analyse the demo: $1"],
    [/^Разбор матча ?(.*)$/, "Match analysis $1"],
    [/^Ошибка сервера \((\d+)\)$/, "Server error ($1)"],
    [/^FACEIT ответил ошибкой (\d+)$/, "FACEIT returned error $1"],
    [/^✅ Клип сохранён: (.+)$/, "✅ Clip saved: $1"],
    [/^Лучшая пятёрка: вы, (.+) — (\d+)% побед за (\d+) матча\.$/, "Best five: you, $1 — $2% wins in $3 matches."],
    [/^Вы, матчей: (\d+): (\d+) убийств на карте$/, "You, $1 matches: $2 kills on the map"],
    [/^Вы, матчей: (\d+): (\d+) смертей на карте$/, "You, $1 matches: $2 deaths on the map"],
    [/^(.+): (\d+) убийств на карте$/, "$1: $2 kills on the map"],
    [/^(.+): (\d+) смертей на карте$/, "$1: $2 deaths on the map"],
    [/^Нет картинки радара: положите её в (.+)$/, "No radar image: put it in $1"],
    [/^Для карты (.+) пока нет настроек радара — показываем без фона\.$/, "No radar settings for $1 yet — showing without a background."],
    [/^(.+) — открыть$/, "$1 — open"],
    [/^Сегодня, (.+)$/, "Today, $1"],
    [/^Вчера, (.+)$/, "Yesterday, $1"],
    [/^(.+) — в CS2$/, "$1 — in CS2"],
  ];

  const DICT = { en: [EN, EN_RX] };

  let lang = "ru";
  try { lang = localStorage.getItem("nuga.lang") || "ru"; } catch { /* нет доступа к хранилищу — остаёмся на русском */ }
  if (!LANGS[lang]) lang = "ru";
  const [dict, rules] = DICT[lang] || [null, null];
  const CYR = /[А-Яа-яЁё]/;

  function lookup(core) {
    if (dict[core] != null) return dict[core];
    const nums = [];
    const key = core.replace(/\d+(?:[.,]\d+)?/g, (n) => (nums.push(n), "#"));
    if (nums.length && dict[key] != null) { let i = 0; return dict[key].replace(/#/g, () => nums[i++] ?? ""); }
    for (const [re, to] of rules) if (re.test(core)) return core.replace(re, to);
    return null;
  }

  // Перевод одной строки. null — переводить нечего или фразы нет в словаре
  function tr(text) {
    if (!dict || !text || !CYR.test(text)) return null;
    const m = text.match(/^(\s*)([\s\S]*?)(\s*)$/);
    const core = m[2].replace(/\s+/g, " ");
    let out = lookup(core);
    if (out == null && core.includes(" · ")) {           // «Mirage · раунд 5 · 3 нояб.» — переводим по частям
      let hit = false;
      out = core.split(" · ").map((part) => { const t = CYR.test(part) ? lookup(part.trim()) : null; if (t != null) hit = true; return t ?? part; }).join(" · ");
      if (!hit) out = null;
    }
    if (out == null && core.includes("\n")) out = null;
    return out == null ? null : m[1] + out + m[3];
  }

  const ATTRS = ["title", "placeholder", "aria-label"];
  const skip = (node) => {
    const p = node.nodeType === 1 ? node : node.parentElement;
    return !p || p.closest("script, style, [data-noi18n]");
  };

  function translate(root) {
    if (!dict) return;
    if (root.nodeType === 3) {
      if (!skip(root)) { const t = tr(root.nodeValue); if (t != null) root.nodeValue = t; }
      return;
    }
    if (root.nodeType !== 1 || skip(root)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) { if (!skip(n)) { const t = tr(n.nodeValue); if (t != null) n.nodeValue = t; } }
    for (const e of [root, ...root.querySelectorAll("[title], [placeholder], [aria-label]")]) {
      for (const a of ATTRS) {
        const v = e.getAttribute?.(a);
        if (v) { const t = tr(v); if (t != null) e.setAttribute(a, t); }
      }
    }
  }

  if (dict) {
    document.documentElement.lang = lang;
    // Даты: «3 нояб.» → «3 Nov»
    for (const name of ["toLocaleDateString", "toLocaleString", "toLocaleTimeString"]) {
      const orig = Date.prototype[name];
      Date.prototype[name] = function (loc, opts) { return orig.call(this, loc === "ru-RU" ? LOCALE[lang] : loc, opts); };
    }
    // Окна confirm / alert / prompt
    const lines = (s) => String(s ?? "").split("\n").map((l) => tr(l) ?? l).join("\n");
    for (const name of ["alert", "confirm", "prompt"]) {
      const orig = window[name].bind(window);
      window[name] = (msg, ...rest) => orig(lines(msg), ...rest);
    }
    // Заголовок вкладки
    const fixTitle = () => {
      const out = document.title.split(" — ").map((part) => tr(part) ?? part).join(" — ");
      if (out !== document.title) document.title = out;
    };
    const titleEl = document.querySelector("title");
    if (titleEl) new MutationObserver(fixTitle).observe(titleEl, { childList: true, characterData: true, subtree: true });
    fixTitle();

    new MutationObserver((list) => {
      for (const m of list) {
        if (m.type === "characterData") translate(m.target);
        else if (m.type === "attributes") { const v = m.target.getAttribute(m.attributeName); const t = v && !skip(m.target) ? tr(v) : null; if (t != null) m.target.setAttribute(m.attributeName, t); }
        else m.addedNodes.forEach(translate);
      }
    }).observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    translate(document.documentElement);
    document.addEventListener("DOMContentLoaded", () => translate(document.documentElement));
  }

  // ---------- Переключатель языка: появляется в элементе с атрибутом data-lang-slot ----------
  function mountSwitch() {
    const slot = document.querySelector("[data-lang-slot]");
    if (!slot || slot.firstChild) return;
    const sel = document.createElement("select");
    sel.setAttribute("data-noi18n", "");
    sel.title = lang === "en" ? "Site language" : "Язык сайта";
    sel.style.cssText = "background:#1b1e26;color:inherit;border:1px solid #262a33;border-radius:999px;padding:6px 8px;font:inherit;" +
      "font-size:13px;font-weight:700;cursor:pointer;flex:none";
    sel.innerHTML = Object.entries(LANGS).map(([k, v]) => `<option value="${k}"${k === lang ? " selected" : ""}>${v}</option>`).join("");
    sel.addEventListener("change", () => {
      try { localStorage.setItem("nuga.lang", sel.value); } catch { /* ничего */ }
      location.reload();
    });
    slot.appendChild(sel);
  }
  mountSwitch();
  document.addEventListener("DOMContentLoaded", mountSwitch);

  window.NugaLang = { lang, tr: (s) => tr(s) ?? s };
})();
