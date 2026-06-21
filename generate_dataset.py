"""
generate_dataset.py
--------------------
Generates a synthetic search-query dataset with 100,000+ entries.
Combines multiple domains: tech, e-commerce, entertainment, health, etc.
Output: data/queries.csv  (query, count)
"""

import csv
import random
import os
from itertools import product as iproduct
import sys
# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

random.seed(42)

# ──────────────────────────────────────────────
# 1.  Seed word-lists per domain
# ──────────────────────────────────────────────
TECH_PRODUCTS = [
    "iphone","samsung","macbook","dell laptop","hp laptop","lenovo","asus rog",
    "pixel phone","oneplus","xiaomi","realme","oppo","vivo","sony xperia",
    "ipad","surface pro","chromebook","gaming laptop","ultrabook","tablet",
    "airpods","galaxy buds","sony wh1000xm5","bose headphones","jabra",
    "apple watch","fitbit","garmin","samsung watch","xiaomi band",
    "nvidia rtx 4090","amd radeon","intel arc","gtx 1080","rtx 3060",
    "ryzen 9","intel i9","m2 chip","snapdragon","mediatek dimensity",
    "ssd 1tb","nvme drive","external hard disk","usb hub","thunderbolt dock",
    "mechanical keyboard","logitech mx keys","razer huntsman","corsair k70",
    "gaming mouse","logitech g pro","razer deathadder","steelseries rival",
    "monitor 4k","ultrawide monitor","oled tv","qled tv","projector",
    "router wifi 6","mesh network","tp link","netgear nighthawk","asus aimesh",
    "raspberry pi","arduino","esp32","jetson nano","microcontroller",
]

TECH_TUTORIALS = [
    "python tutorial","javascript tutorial","react tutorial","nodejs tutorial",
    "java tutorial","c++ tutorial","golang tutorial","rust tutorial",
    "machine learning tutorial","deep learning tutorial","pytorch tutorial",
    "tensorflow tutorial","data science course","sql tutorial","postgresql",
    "mongodb tutorial","redis tutorial","docker tutorial","kubernetes tutorial",
    "aws tutorial","azure tutorial","gcp tutorial","devops tutorial",
    "git tutorial","linux commands","bash scripting","powershell tutorial",
    "html css tutorial","tailwind css","bootstrap tutorial","vue js tutorial",
    "angular tutorial","svelte tutorial","next js tutorial","fastapi tutorial",
    "flask tutorial","django tutorial","spring boot tutorial","microservices",
    "system design interview","leetcode problems","coding interview prep",
    "data structures algorithms","dynamic programming","graph algorithms",
    "competitive programming","codeforces problems","hackerrank solutions",
]

ECOMMERCE = [
    "nike shoes","adidas sneakers","puma running shoes","new balance 990",
    "jordan 1","yeezy 350","vans old skool","converse chuck taylor",
    "levi jeans","h&m shirt","zara dress","mango blazer","uniqlo jacket",
    "fossil watch","casio g shock","seiko watch","titan watch",
    "samsung refrigerator","lg washing machine","bosch dishwasher","whirlpool",
    "instant pot","air fryer","coffee maker","espresso machine","blender",
    "yoga mat","dumbbell set","resistance bands","treadmill","cycle stand",
    "face wash","sunscreen spf50","moisturizer","vitamin c serum","retinol",
    "protein powder","creatine supplement","multivitamins","omega 3",
    "backpack","travel bag","laptop bag","handbag","wallet leather",
    "books fiction","self help books","python book","data science book",
]

ENTERTAINMENT = [
    "netflix shows","prime video movies","disney plus series","hulu originals",
    "breaking bad","game of thrones","stranger things","the witcher",
    "dune movie","oppenheimer","avatar 2","spiderman no way home","top gun",
    "taylor swift songs","ed sheeran album","drake playlist","weeknd songs",
    "spotify playlist","youtube music","apple music subscription",
    "minecraft tutorial","gta 5 cheats","call of duty warzone","valorant tips",
    "elden ring walkthrough","hogwarts legacy","cyberpunk 2077","red dead 2",
    "chess openings","sudoku puzzles","wordle game","crossword clues",
    "cricket live score","ipl schedule","fifa world cup","nba highlights",
    "manga online","anime streaming","one piece episodes","naruto filler list",
]

HEALTH = [
    "how to lose weight","keto diet plan","intermittent fasting","calorie deficit",
    "gym workout plan","home workout","push up variations","pull up bar exercises",
    "symptoms of diabetes","blood pressure normal range","cholesterol levels",
    "covid symptoms","flu vs cold","headache relief","back pain exercises",
    "meditation for beginners","yoga for anxiety","breathing exercises","sleep tips",
    "pregnancy symptoms","baby food chart","child vaccination schedule",
    "hair fall remedies","acne treatment","skin care routine","dark circles",
    "dentist near me","eye care tips","hearing loss symptoms","bone health",
]

GENERAL = [
    "how to make pasta","biryani recipe","pizza dough recipe","pancake recipe",
    "how to tie a tie","parallel parking tips","change car tire","oil change diy",
    "income tax return filing","gst registration","pan card apply","aadhaar update",
    "visa application usa","passport renewal","travel insurance","flight booking tips",
    "ielts preparation","gmat preparation","cat exam syllabus","upsc preparation",
    "resume writing tips","cover letter sample","linkedin profile tips","job interview",
    "how to invest in stocks","mutual funds beginner","sip calculator","fixed deposit",
    "home loan interest rate","credit card benefits","emi calculator","insurance plan",
    "interior design ideas","kitchen renovation","bathroom tiles","wall paint colors",
    "dog training tips","cat food brands","aquarium setup","bird care guide",
    "weather forecast","local news","stock market today","cryptocurrency prices",
]

# ──────────────────────────────────────────────
# 2.  Build base queries with counts
# ──────────────────────────────────────────────

def zipf_count(rank: int, total: int = 1_000_000) -> int:
    """Zipf-law count so popular queries have exponentially higher counts."""
    return max(1, int(total / (rank ** 1.1)))


def expand_queries():
    """Return list of (query, count) tuples."""
    base_pools = [
        TECH_PRODUCTS, TECH_TUTORIALS, ECOMMERCE, ENTERTAINMENT, HEALTH, GENERAL
    ]
    suffixes = [
        "", " 2024", " 2025", " review", " price", " best", " cheap",
        " near me", " online", " free", " download", " buy", " vs",
        " tutorial", " guide", " tips", " how to", " top 10",
        " alternatives", " comparison", " discount", " coupon",
    ]

    queries = {}

    for pool in base_pools:
        for q in pool:
            for suf in suffixes:
                full_q = (q + suf).strip().lower()
                if full_q not in queries:
                    queries[full_q] = 0

    # Generate multi-word combinations
    adjectives = ["best","top","cheap","free","new","used","refurbished",
                  "wireless","portable","mini","pro","ultra","gaming","smart","fast"]
    nouns = ["laptop","phone","headphones","charger","case","stand","adapter",
             "keyboard","mouse","monitor","camera","speaker","watch","tablet"]
    for adj in adjectives:
        for noun in nouns:
            q = f"{adj} {noun}"
            queries[q] = 0
            queries[f"{q} 2024"] = 0
            queries[f"{q} 2025"] = 0
            queries[f"best {q}"] = 0

    # ─── Alphabetic prefix completions ───────────────────────────
    # ensure we hit 100k by generating letter-combo starters
    letters = "abcdefghijklmnopqrstuvwxyz"
    two_letter = [a+b for a,b in iproduct(letters, letters)]
    topic_words = ["tutorial","review","price","download","buy","how","tips","guide",
                   "best","cheap","free","online","near me","app","software","tool"]
    for prefix in two_letter[:300]:          # first 300 two-letter combos
        for tw in topic_words[:6]:
            q = f"{prefix} {tw}"
            if q not in queries:
                queries[q] = 0

    return list(queries.keys())


def assign_counts(query_list):
    """Assign Zipf-distributed counts."""
    random.shuffle(query_list)
    result = []
    total = len(query_list)
    for rank, q in enumerate(query_list, start=1):
        count = zipf_count(rank, total=5_000_000)
        # add noise ±20 %
        noise = random.uniform(0.8, 1.2)
        count = max(1, int(count * noise))
        result.append((q, count))
    return result


# ──────────────────────────────────────────────
# 3.  Write CSV
# ──────────────────────────────────────────────

def main():
    os.makedirs("data", exist_ok=True)
    out_path = os.path.join("data", "queries.csv")

    print("Building query list …")
    query_list = expand_queries()
    print(f"  Raw unique queries: {len(query_list):,}")

    # Pad to ≥ 100 000 with numbered synthetic queries
    if len(query_list) < 100_000:
        extra_templates = [
            "how to {verb} {noun}",
            "{adj} {noun} for sale",
            "{noun} {year} model",
            "best {adj} {noun} under {price}",
            "{brand} {noun} review",
        ]
        verbs  = ["fix","install","use","setup","configure","update","upgrade","clean","repair","connect"]
        adj2   = ["affordable","lightweight","durable","professional","compact","ergonomic"]
        nouns2 = ["laptop","monitor","keyboard","router","printer","scanner","webcam","microphone"]
        brands = ["samsung","apple","dell","hp","lenovo","asus","acer","msi","razer","logitech"]
        years  = ["2023","2024","2025"]
        prices = ["5000","10000","20000","50000","1000","500","100"]

        i = len(query_list)
        seen = set(query_list)
        while len(query_list) < 120_000:
            v = random.choice(verbs)
            a = random.choice(adj2)
            n = random.choice(nouns2)
            b = random.choice(brands)
            y = random.choice(years)
            p = random.choice(prices)
            candidates = [
                f"how to {v} {n}",
                f"{a} {n} for sale",
                f"{b} {n} {y}",
                f"best {a} {n} under {p}",
                f"{b} {n} review {y}",
                f"{n} {i}",
            ]
            for c in candidates:
                if c not in seen:
                    query_list.append(c)
                    seen.add(c)
            i += 1

    print(f"  Total queries after padding: {len(query_list):,}")

    rows = assign_counts(query_list)
    # sort by count desc for CSV readability
    rows.sort(key=lambda x: -x[1])

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["query", "count"])
        writer.writerows(rows)

    print(f"[OK] Dataset written -> {out_path}  ({len(rows):,} rows)")


if __name__ == "__main__":
    main()
