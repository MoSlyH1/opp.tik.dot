"""Everything the feed can be filtered by, in one place.

Four dimensions, each multi-label (an item can be "Football" AND "Arabic" AND "'90s"):

  era      one per item (stored in Item.era)
  topic    t:<id>   what it is: football, documentaries, kids' cartoons, sci-fi, cars...
  region   r:<id>   which culture it comes from: Arabic, Lebanese, Latin, Japanese...
  channel  c:<id>   which TV channel / network it aired on: MTV, Spacetoon, LBC...

Topics, regions and channels are stored together in Item.labels as
"|t:football|r:arabic|r:egyptian|c:mbc|" so one LIKE filters any of them,
on Postgres and SQLite alike.

Bump TAXONOMY_VERSION whenever keywords change: the ingest job re-labels old items.
"""

TAXONOMY_VERSION = 4

# ---------------------------------------------------------------- eras

ERAS = ["50s", "60s", "70s", "80s", "90s", "00s"]
ERA_LABELS = {"50s": "'50s & before", "60s": "'60s", "70s": "'70s", "80s": "'80s",
              "90s": "'90s", "00s": "2000s"}
ERA_RANGES = {"50s": (1930, 1959), "60s": (1960, 1969), "70s": (1970, 1979),
              "80s": (1980, 1989), "90s": (1990, 1999), "00s": (2000, 2012)}
LEGACY_ERAS = {"classic": "80s"}  # v1-v3 used one bucket for everything before 1990

# ---------------------------------------------------------------- topics
# (id, label, group, keywords). Keywords are matched as whole words, case-insensitive.

TOPIC_GROUPS = ["Watch", "Sports", "Life & style", "Tech & play", "TV world"]

TOPICS = [
    ("music", "Music videos", "Watch", [
        "music video", "official video", "official music video", "videoclip", "video clip", "clip officiel",
        "song", "songs", "album", "band", "concert", "live performance", "single", "hip hop", "rap", "r&b",
        "rnb", "boy band", "girl group", "pop song", "pop music", "pop star", "britpop", "europop", "k-pop",
        "kpop", "j-pop", "jpop", "eurodance", "disco", "rock", "grunge", "metal", "techno", "house music",
        "karaoke", "top of the pops", "eurovision", "singer", "lyrics", "remix", "reggaeton", "salsa",
        "bachata", "cumbia", "samba", "bossa nova", "rai", "dabke", "tarab", "chanson", "schlager",
        "كليب", "أغنية", "اغنية", "اغاني", "أغاني", "مطرب", "حفلة",
        # artists people search for by name
        "fairuz", "fairouz", "nancy ajram", "haifa wehbe", "elissa", "amr diab", "om kalthoum",
        "umm kulthum", "abdel halim", "ragheb alama", "wadih el safi", "majida el roumi", "cheb khaled",
        "kadim al sahir", "kazem el saher", "tarkan", "shakira", "ricky martin", "selena", "backstreet boys",
        "nsync", "britney", "spice girls", "madonna", "michael jackson", "whitney houston", "mariah carey",
        "nirvana", "oasis", "blur", "tupac", "2pac", "notorious b.i.g", "eminem", "destiny's child",
        "aaliyah", "tlc", "celine dion", "abba", "queen", "bon jovi", "guns n' roses", "metallica",
        "prince", "beyonce", "beyoncé", "usher", "outkast", "linkin park", "avril lavigne",
        "فيروز", "عمرو دياب", "ام كلثوم", "أم كلثوم", "نانسي عجرم", "كاظم الساهر"]),
    ("movies", "Movies & trailers", "Watch", [
        "movie", "movies", "film", "films", "trailer", "trailers", "cinema", "box office", "blockbuster",
        "theatrical", "full movie", "movie scene", "film scene", "teaser", "bollywood", "nollywood",
        "فيلم", "افلام", "أفلام", "سينما", "película", "pelicula", "filme"]),
    ("tv", "TV shows", "Watch", [
        "tv show", "tv series", "television series", "sitcom", "episode", "theme song", "intro",
        "opening credits", "opening theme", "game show", "talk show", "quiz show", "variety show",
        "series finale", "season 1", "pilot episode", "برنامج", "مسلسل"]),
    ("kids", "Kids & cartoons", "Watch", [
        "cartoon", "cartoons", "animated", "animation", "kids", "children", "children's", "saturday morning",
        "nickelodeon", "nick jr", "cartoon network", "disney channel", "disney afternoon", "fox kids",
        "jetix", "toonami", "spacetoon", "sesame street", "teletubbies", "barney", "power rangers",
        "pokemon", "pokémon", "digimon", "tom and jerry", "looney tunes", "scooby", "rugrats", "spongebob",
        "dexter's laboratory", "powerpuff", "tiny toons", "ducktales", "animaniacs", "hey arnold",
        "doug", "arthur", "smurfs", "thundercats", "he-man", "transformers", "ninja turtles", "tmnt",
        "captain majid", "grendizer", "beyblade", "bakugan", "mr. men", "fraggle", "muppets",
        "كرتون", "كارتون", "رسوم متحركة", "سبيستون", "سبيس تون", "اطفال", "أطفال", "افتح يا سمسم",
        "dibujos animados", "desenho animado", "dessin animé", "dessins animés"]),
    ("anime", "Anime", "Watch", [
        "anime", "manga", "dragon ball", "dragonball", "sailor moon", "naruto", "one piece",
        "captain tsubasa", "grendizer", "evangelion", "gundam", "ghibli", "digimon", "yu-gi-oh",
        "yugioh", "slam dunk", "detective conan", "hunter x hunter", "cowboy bebop", "akira",
        "fullmetal", "inuyasha", "bleach", "rurouni kenshin", "kenshin", "voltron", "macross",
        "انمي", "أنمي"]),
    ("docs", "Documentaries", "Watch", [
        "documentary", "documentaries", "docu", "docuseries", "national geographic", "nat geo",
        "discovery channel", "history channel", "nature documentary", "wildlife", "planet earth", "attenborough",
        "behind the scenes", "making of", "the making of", "investigation", "biography",
        "وثائقي", "وثائقية", "documental", "documentaire", "dokumentation"]),
    ("scifi", "Sci-fi", "Watch", [
        "sci-fi", "scifi", "science fiction", "star trek", "star wars", "x-files", "alien", "aliens",
        "outer space", "robot", "robots", "cyberpunk", "matrix", "terminator", "back to the future",
        "blade runner", "doctor who", "stargate", "futuristic", "ufo", "ufos", "spaceship", "time travel",
        "babylon 5", "battlestar", "jurassic park", "independence day", "men in black", "dune",
        "خيال علمي", "ciencia ficción"]),
    ("horror", "Horror", "Watch", [
        "horror", "scary", "creepy", "ghost", "ghosts", "haunted", "slasher", "goosebumps",
        "are you afraid of the dark", "zombie", "zombies", "vampire", "exorcist", "nightmare on elm",
        "scream", "halloween", "رعب", "terror"]),
    ("comedy", "Comedy & sitcoms", "Watch", [
        "comedy", "comedies", "sitcom", "funny", "stand-up", "standup", "stand up comedy", "sketch",
        "prank", "pranks", "bloopers", "candid camera", "seinfeld", "fresh prince", "mr bean",
        "mr. bean", "saturday night live", "snl", "monty python", "laugh", "كوميدي", "كوميديا",
        "مضحك", "comedia", "humour"]),
    ("drama", "Soaps & telenovelas", "Watch", [
        "soap opera", "telenovela", "telenovelas", "novela", "drama series", "dizi", "mosalsal",
        "k-drama", "kdrama", "مسلسل", "دراما"]),
    ("football", "Football", "Sports", [
        "football", "soccer", "fifa", "world cup", "uefa", "champions league", "premier league", "la liga",
        "serie a", "bundesliga", "ligue 1", "euro 96", "euro 2000", "euro 2004", "euro 2008", "copa america",
        "afcon", "goal", "goals", "maradona", "pele", "pelé", "zidane", "ronaldinho", "ronaldo", "beckham",
        "baggio", "thierry henry", "figo", "del piero", "batistuta", "cantona", "maldini", "kaka", "messi",
        "free kick", "penalty shootout", "كرة القدم", "كرة قدم", "كأس العالم", "مونديال", "هدف", "اهداف",
        "أهداف", "fútbol", "futbol", "futebol", "calcio", "fußball", "fussball"]),
    ("basketball", "Basketball", "Sports", [
        "basketball", "nba", "michael jordan", "kobe", "shaq", "shaquille", "dream team", "slam dunk contest",
        "chicago bulls", "lakers", "magic johnson", "larry bird", "allen iverson", "كرة السلة"]),
    ("motorsport", "F1 & racing", "Sports", [
        "formula 1", "formula one", "f1", "grand prix", "schumacher", "senna", "prost", "hakkinen",
        "häkkinen", "nascar", "rally", "wrc", "le mans", "motogp", "indycar", "drifting", "drift",
        "touring car", "dakar", "فورمولا"]),
    ("combat", "Wrestling & fights", "Sports", [
        "wrestling", "wwf", "wwe", "wcw", "ecw", "smackdown", "raw is war", "wrestlemania", "royal rumble",
        "hulk hogan", "undertaker", "stone cold", "the rock", "boxing", "tyson", "muhammad ali", "ufc",
        "kickboxing", "karate", "kung fu", "martial arts", "مصارعة", "ملاكمة", "lucha libre"]),
    ("sports", "More sports", "Sports", [
        "sport", "sports", "olympics", "olympic", "tennis", "golf", "cricket", "baseball", "hockey",
        "gridiron", "super bowl", "skateboarding", "skate", "bmx", "surfing", "x games", "athletics",
        "marathon", "volleyball", "handball", "cycling", "tour de france", "wimbledon", "رياضة"]),
    ("cars", "Cars", "Life & style", [
        "car", "cars", "auto", "automobile", "automotive", "motor show", "top gear", "supercar", "sports car",
        "ferrari", "lamborghini", "porsche", "bmw", "mercedes", "mercedes-benz", "toyota", "honda", "nissan",
        "mitsubishi", "subaru", "chevrolet", "chevy", "ford", "mustang", "corvette", "jdm", "tuning",
        "drag race", "test drive", "pickup truck", "volkswagen", "vw", "peugeot", "renault", "fiat",
        "alfa romeo", "audi", "volvo", "lada", "سيارة", "سيارات", "coche", "voiture"]),
    ("style", "Style & fashion", "Life & style", [
        "fashion", "style", "outfit", "outfits", "runway", "hairstyle", "makeup", "clothing", "trend",
        "lookbook", "streetwear", "denim", "y2k aesthetic", "supermodel", "catwalk", "vogue", "models",
        "fashion show", "موضة", "أزياء", "ازياء", "moda"]),
    ("dance", "Dance", "Life & style", [
        "dance", "dancing", "choreography", "breakdance", "breakdancing", "b-boy", "macarena", "ballet",
        "dabke", "dabkeh", "belly dance", "moonwalk", "soul train", "dance floor", "رقص", "دبكة", "baile"]),
    ("food", "Food & cooking", "Life & style", [
        "food", "cooking", "recipe", "recipes", "chef", "kitchen", "cuisine", "baking", "fast food",
        "cooking show", "طبخ", "مطبخ", "وصفة", "cocina", "cuisine"]),
    ("travel", "Travel & places", "Life & style", [
        "travel", "tourism", "tourist", "city tour", "vacation", "holiday", "airline", "airport", "train",
        "trains", "street footage", "walking tour", "home video", "home movies", "camcorder", "سياحة", "سفر"]),
    ("tech", "Retro tech", "Tech & play", [
        "nokia", "motorola", "sony ericsson", "walkman", "discman", "ipod", "windows 95", "windows 98",
        "windows xp", "windows me", "macintosh", "imac", "dial-up", "dial up", "modem", "flip phone",
        "tamagotchi", "msn", "aol", "icq", "myspace", "geocities", "computer", "computers", "pager",
        "blackberry", "floppy", "cd-rom", "palm pilot", "pda", "vhs", "betamax", "cassette", "gadget",
        "gadgets", "internet", "commodore", "amiga", "اتاري"]),
    ("games", "Video games", "Tech & play", [
        "video game", "video games", "videogame", "gaming", "playstation", "ps1", "ps2",
        "nintendo", "n64", "snes", "nes", "super nintendo", "sega", "genesis", "mega drive", "dreamcast",
        "gameboy", "game boy", "gamecube", "xbox", "atari", "arcade", "gameplay", "doom", "quake", "mario",
        "sonic", "zelda", "street fighter", "mortal kombat", "tekken", "metal gear", "final fantasy",
        "crash bandicoot", "spyro", "counter-strike", "half-life", "العاب", "ألعاب", "بلايستيشن"]),
    ("ads", "Commercials", "TV world", [
        "commercial", "commercials", "ad", "ads", "advert", "adverts", "advertisement", "advertising",
        "promo", "jingle", "tv spot", "إعلان", "اعلان", "اعلانات", "إعلانات", "publicité", "publicidad",
        "comercial", "comerciales", "werbung", "reklam", "propaganda comercial"]),
    ("news", "News & broadcasts", "TV world", [
        "news", "newscast", "broadcast", "breaking news", "news report", "bulletin", "anchor", "nightly news",
        "evening news", "live coverage", "نشرة", "أخبار", "اخبار", "noticiero", "noticias", "journal télévisé",
        "tagesschau"]),
    ("idents", "Channel idents & bumpers", "TV world", [
        "ident", "idents", "bumper", "bumpers", "station id", "continuity", "test card", "sign off",
        "sign-off", "sign on", "startup", "closedown", "channel promo", "tv channel", "logo history",
        "intro channel", "شارة", "فاصل"]),
]
FALLBACK_TOPIC = ("culture", "Culture & misc")

# ---------------------------------------------------------------- regions / cultures
# (id, label, group, parent umbrella or None, keywords)

REGION_GROUPS = ["Americas", "Europe", "Middle East", "Asia", "Africa"]

REGIONS = [
    ("american", "American", "Americas", None, [
        "american", "america", "usa", "u.s.a", "hollywood", "new york", "los angeles", "super bowl",
        "saturday night live", "nbc", "cbs", "abc network", "fox network", "pbs", "thanksgiving"]),
    ("latin", "Latin American", "Americas", None, [
        "latin", "latino", "latina", "latinoamerica", "latinoamérica", "reggaeton", "salsa", "cumbia",
        "bachata", "merengue", "telenovela", "colombia", "colombian", "argentina", "argentine", "chile",
        "chilean", "peru", "peruvian", "venezuela", "venezuelan", "cuba", "cuban", "puerto rico",
        "dominican", "shakira", "ricky martin", "selena", "lucha libre", "mexico", "méxico", "mexican",
        "brazil", "brasil", "brazilian", "brasileiro", "samba", "bossa nova", "xuxa", "globo", "televisa",
        "chespirito", "el chavo", "telemundo", "univision", "años 80", "años 90", "anos 80", "anos 90"]),
    ("mexican", "Mexican", "Americas", "latin", [
        "mexico", "méxico", "mexican", "mexicano", "televisa", "chespirito", "el chavo", "lucha libre"]),
    ("brazilian", "Brazilian", "Americas", "latin", [
        "brazil", "brasil", "brazilian", "brasileiro", "samba", "bossa nova", "xuxa", "globo", "anos 80",
        "anos 90"]),
    ("european", "European", "Europe", None, [
        "europe", "european", "eurovision", "eurodance", "europop", "italo disco", "schlager", "eurosport"]),
    ("british", "British", "Europe", "european", [
        "british", "britain", "uk", "england", "london", "scotland", "irish", "bbc", "itv", "channel 4",
        "britpop", "top of the pops", "spice girls", "oasis", "premier league", "mr bean", "mr. bean"]),
    ("french", "French", "Europe", "european", [
        "france", "french", "français", "francais", "paris", "tf1", "canal+", "antenne 2", "chanson",
        "années 80", "années 90", "publicité", "dessin animé", "ligue 1"]),
    ("german", "German", "Europe", "european", [
        "germany", "german", "deutsch", "deutschland", "berlin", "zdf", "ard", "rtl", "viva", "80er",
        "90er", "werbung", "bundesliga", "schlager"]),
    ("italian", "Italian", "Europe", "european", [
        "italy", "italian", "italia", "italiano", "sanremo", "italo disco", "serie a", "calcio",
        "fiat", "ferrari", "alfa romeo"]),
    ("spanish", "Spanish", "Europe", "european", [
        "spain", "españa", "espana", "madrid", "barcelona", "tve", "la liga", "flamenco"]),
    ("russian", "Russian & Soviet", "Europe", None, [
        "russia", "russian", "soviet", "ussr", "cccp", "moscow", "lada", "советский", "россия"]),
    ("arabic", "Arabic", "Middle East", None, [
        "arab", "arabic", "arabian", "middle east", "khaleeji", "tarab", "dabke", "belly dance",
        "زمن الطيبين", "الزمن الجميل", "عربي", "العربية", "عرب"]),
    ("lebanese", "Lebanese", "Middle East", "arabic", [
        "lebanon", "lebanese", "beirut", "fairuz", "fairouz", "feiruz", "wadih el safi", "ragheb alama",
        "nancy ajram", "haifa wehbe", "elissa", "majida el roumi", "ziad rahbani", "sabah", "assi rahbani",
        "lbc", "future tv", "tele liban", "télé liban", "mtv lebanon", "لبنان", "لبناني", "بيروت", "فيروز",
        "تلفزيون لبنان"]),
    ("egyptian", "Egyptian", "Middle East", "arabic", [
        "egypt", "egyptian", "cairo", "amr diab", "adel imam", "adel emam", "om kalthoum", "umm kulthum",
        "abdel halim", "mohamed mounir", "ahmed zaki", "مصر", "مصري", "القاهرة", "عمرو دياب", "عادل امام",
        "عادل إمام", "ام كلثوم", "أم كلثوم", "عبد الحليم"]),
    ("gulf", "Gulf", "Middle East", "arabic", [
        "saudi", "kuwait", "kuwaiti", "emirates", "uae", "dubai", "abu dhabi", "qatar", "bahrain", "oman",
        "khaleeji", "mohammed abdu", "السعودية", "الكويت", "الإمارات", "الامارات", "قطر", "البحرين",
        "عمان", "خليجي", "زمن الطيبين"]),
    ("maghreb", "Maghreb", "Middle East", "arabic", [
        "morocco", "moroccan", "algeria", "algerian", "tunisia", "tunisian", "cheb khaled", "cheb mami",
        "rai", "المغرب", "الجزائر", "تونس"]),
    ("turkish", "Turkish", "Middle East", None, [
        "turkish", "turkey", "türk", "türkiye", "istanbul", "tarkan", "ajda pekkan", "yeşilçam",
        "yesilcam", "dizi", "trt", "reklam", "80'ler", "90'lar"]),
    ("persian", "Persian", "Middle East", None, [
        "iran", "iranian", "persian", "farsi", "googoosh", "tehran"]),
    ("asian", "Asian", "Asia", None, ["asia", "asian"]),
    ("japanese", "Japanese", "Asia", "asian", [
        "japan", "japanese", "tokyo", "j-pop", "jpop", "nhk", "fuji tv", "anime", "manga", "sega",
        "nintendo", "tokusatsu", "super sentai", "kamen rider", "godzilla"]),
    ("korean", "Korean", "Asia", "asian", [
        "korea", "korean", "seoul", "k-pop", "kpop", "k-drama", "kdrama", "kbs", "mbc korea", "sbs"]),
    ("chinese", "Chinese", "Asia", "asian", [
        "china", "chinese", "hong kong", "cantonese", "mandarin", "taiwan", "taiwanese", "c-pop", "cantopop",
        "jackie chan", "bruce lee", "jet li", "tvb", "shaw brothers", "kung fu"]),
    ("indian", "Indian", "Asia", "asian", [
        "india", "indian", "bollywood", "hindi", "tamil", "telugu", "malayalam", "shah rukh", "shahrukh",
        "amitabh", "doordarshan", "zee tv", "cricket world cup"]),
    ("seasian", "Southeast Asian", "Asia", "asian", [
        "thai", "thailand", "vietnam", "vietnamese", "philippines", "filipino", "pinoy", "indonesia",
        "indonesian", "malaysia", "malaysian", "singapore"]),
    ("african", "African", "Africa", None, [
        "africa", "african", "nigeria", "nigerian", "nollywood", "ghana", "ghanaian", "kenya", "kenyan",
        "south africa", "afrobeat", "afrobeats", "senegal", "ethiopia", "ethiopian", "congo", "cameroon",
        "afcon"]),
]

# Language codes (ISO 639-1/2, as Internet Archive and Dailymotion report them) -> regions.
LANG_REGIONS = {
    "ar": ["arabic"], "ara": ["arabic"], "arabic": ["arabic"],
    "fr": ["french"], "fre": ["french"], "fra": ["french"], "french": ["french"],
    "de": ["german"], "ger": ["german"], "deu": ["german"], "german": ["german"],
    "it": ["italian"], "ita": ["italian"], "italian": ["italian"],
    "es": ["latin"], "spa": ["latin"], "spanish": ["latin"],
    "pt": ["brazilian"], "por": ["brazilian"], "portuguese": ["brazilian"],
    "ru": ["russian"], "rus": ["russian"], "russian": ["russian"],
    "tr": ["turkish"], "tur": ["turkish"], "turkish": ["turkish"],
    "fa": ["persian"], "per": ["persian"], "fas": ["persian"], "persian": ["persian"],
    "ja": ["japanese"], "jpn": ["japanese"], "japanese": ["japanese"],
    "ko": ["korean"], "kor": ["korean"], "korean": ["korean"],
    "zh": ["chinese"], "chi": ["chinese"], "zho": ["chinese"], "chinese": ["chinese"],
    "hi": ["indian"], "hin": ["indian"], "ta": ["indian"], "hindi": ["indian"],
    "th": ["seasian"], "vi": ["seasian"], "id": ["seasian"], "tl": ["seasian"],
}
COUNTRY_REGIONS = {
    "US": "american", "MX": "mexican", "BR": "brazilian", "AR": "latin", "CO": "latin", "CL": "latin",
    "PE": "latin", "VE": "latin", "GB": "british", "IE": "british", "FR": "french", "DE": "german",
    "AT": "german", "IT": "italian", "ES": "spanish", "RU": "russian", "LB": "lebanese", "EG": "egyptian",
    "SA": "gulf", "AE": "gulf", "KW": "gulf", "QA": "gulf", "BH": "gulf", "OM": "gulf", "MA": "maghreb",
    "DZ": "maghreb", "TN": "maghreb", "SY": "arabic", "JO": "arabic", "IQ": "arabic", "PS": "arabic",
    "TR": "turkish", "IR": "persian", "JP": "japanese", "KR": "korean", "CN": "chinese", "HK": "chinese",
    "TW": "chinese", "IN": "indian", "TH": "seasian", "VN": "seasian", "PH": "seasian", "ID": "seasian",
    "MY": "seasian", "NG": "african", "GH": "african", "KE": "african", "ZA": "african", "SN": "african",
}

# ---------------------------------------------------------------- channels
# (id, label, keywords, implied topics, implied regions)

CHANNELS = [
    ("mtv", "MTV", [r"mtv(?! lebanon)", "mtv unplugged", "total request live", "trl", "yo! mtv raps"],
     ["music"], ["american"]),
    ("vh1", "VH1", ["vh1", "vh-1"], ["music"], ["american"]),
    ("cn", "Cartoon Network", ["cartoon network", "toonami", "boomerang"], ["kids"], ["american"]),
    ("nick", "Nickelodeon", ["nickelodeon", "nick jr", "nicktoons", "snick"], ["kids"], ["american"]),
    ("disney", "Disney Channel", ["disney channel", "disney afternoon", "toon disney", "jetix"], ["kids"],
     ["american"]),
    ("foxkids", "Fox Kids", ["fox kids"], ["kids"], ["american"]),
    ("spacetoon", "Spacetoon", ["spacetoon", "space toon", "سبيستون", "سبيس تون"], ["kids"], ["arabic"]),
    ("mbc", "MBC", ["mbc", "mbc1", "mbc 1", "mbc2", "mbc3", "ام بي سي"], [], ["gulf"]),
    ("lbc", "LBC", ["lbc", "lbci"], [], ["lebanese"]),
    ("futuretv", "Future TV", ["future tv", "تلفزيون المستقبل"], [], ["lebanese"]),
    ("teleliban", "Télé Liban", ["tele liban", "télé liban", "تلفزيون لبنان"], [], ["lebanese"]),
    ("mtvlb", "MTV Lebanon", ["mtv lebanon", "mtv lb"], [], ["lebanese"]),
    ("art", "ART", ["art channel", "arab radio and television", "art movies"], [], ["arabic"]),
    ("rotana", "Rotana", ["rotana", "روتانا"], ["music"], ["arabic"]),
    ("melody", "Melody", ["melody tv", "melody aflam", "ميلودي"], ["music"], ["egyptian"]),
    ("aljazeera", "Al Jazeera", ["al jazeera", "aljazeera", "الجزيرة"], ["news"], ["gulf"]),
    ("bbc", "BBC", ["bbc", "bbc one", "bbc two", "cbbc"], [], ["british"]),
    ("cnn", "CNN", ["cnn"], ["news"], ["american"]),
    ("discovery", "Discovery", ["discovery channel", "discovery kids", "animal planet"], ["docs"], []),
    ("natgeo", "National Geographic", ["national geographic", "nat geo"], ["docs"], []),
    ("eurosport", "Eurosport", ["eurosport"], ["sports"], ["european"]),
    ("espn", "ESPN", ["espn"], ["sports"], ["american"]),
    ("hbo", "HBO", ["hbo"], ["tv"], ["american"]),
    ("televisa", "Televisa", ["televisa", "canal de las estrellas"], [], ["mexican"]),
    ("globo", "Globo", ["rede globo", "tv globo", "globo"], [], ["brazilian"]),
    ("nhk", "NHK / Fuji TV", ["nhk", "fuji tv", "tv asahi"], [], ["japanese"]),
    ("tf1", "TF1 / Canal+", ["tf1", "canal+", "antenne 2", "france 2"], [], ["french"]),
    ("rai", "RAI", ["rai uno", "rai 1", "rai due", "rai tre"], [], ["italian"]),
    ("viva", "VIVA / ZDF", ["viva tv", "zdf", "ard", "rtl"], [], ["german"]),
]

# ---------------------------------------------------------------- lookups

TOPIC_IDS = [t[0] for t in TOPICS] + [FALLBACK_TOPIC[0]]
TOPIC_LABELS = {t[0]: t[1] for t in TOPICS} | {FALLBACK_TOPIC[0]: FALLBACK_TOPIC[1]}
REGION_IDS = [r[0] for r in REGIONS]
REGION_LABELS = {r[0]: r[1] for r in REGIONS}
REGION_PARENT = {r[0]: r[3] for r in REGIONS if r[3]}
CHANNEL_IDS = [c[0] for c in CHANNELS]
CHANNEL_LABELS = {c[0]: c[1] for c in CHANNELS}

# v1-v3 "category" values map straight onto topics.
LEGACY_CATEGORY = {"tv": "tv", "movies": "movies", "music": "music", "style": "style", "ads": "ads",
                   "tech": "tech", "games": "games", "culture": "culture"}

# Quick chips shown above the feed (the full list lives in the filter sheet).
QUICK = [("t", "kids"), ("t", "football"), ("t", "music"), ("t", "movies"), ("t", "docs"),
         ("t", "scifi"), ("t", "cars"), ("t", "anime"), ("r", "arabic"), ("r", "lebanese"),
         ("r", "american"), ("r", "european"), ("r", "latin"), ("r", "asian"), ("t", "ads"),
         ("t", "games"), ("t", "comedy"), ("t", "combat")]


def token_label(token: str) -> str:
    kind, _, ident = token.partition(":")
    return {"t": TOPIC_LABELS, "r": REGION_LABELS, "c": CHANNEL_LABELS}.get(kind, {}).get(ident, ident)


def meta() -> dict:
    """Shape served by /api/meta for the filter UI."""
    return {
        "eras": [{"id": e, "label": ERA_LABELS[e]} for e in ERAS],
        "topics": [{"id": t[0], "label": t[1], "group": t[2]} for t in TOPICS]
                  + [{"id": FALLBACK_TOPIC[0], "label": FALLBACK_TOPIC[1], "group": "TV world"}],
        "topic_groups": TOPIC_GROUPS,
        "regions": [{"id": r[0], "label": r[1], "group": r[2], "parent": r[3]} for r in REGIONS],
        "region_groups": REGION_GROUPS,
        "channels": [{"id": c[0], "label": c[1]} for c in CHANNELS],
        "quick": [{"dim": "topic" if k == "t" else "region", "id": i,
                   "label": TOPIC_LABELS[i] if k == "t" else REGION_LABELS[i]} for k, i in QUICK],
    }
