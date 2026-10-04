import random

# A carefully curated dictionary of 100% innocent, common, child-friendly English words.
# Roblox's CommunitySift / Two Hat filter aggressively tags numbers, alphanumeric codes,
# and strange strings (especially on <13 accounts).
# Common dictionary words separated by spaces are NEVER filtered or censored by Roblox.
FILTER_SAFE_WORDS = [
    "apple", "apron", "acorn", "amber", "anchor", "arrow", "autumn", "badge",
    "bamboo", "banana", "beacon", "blanket", "breeze", "bridge", "bronze", "bubble",
    "cabin", "cactus", "candle", "canyon", "castle", "cedar", "cherry", "cliff",
    "clover", "cloud", "comet", "compass", "copper", "coral", "cotton", "crater",
    "crystal", "dawn", "diamond", "dolphin", "dragon", "eagle", "emerald", "falcon",
    "feather", "field", "firefly", "forest", "frost", "galaxy", "garden", "glacier",
    "golden", "granite", "guitar", "harbor", "haven", "hazel", "island", "jasper",
    "jungle", "koala", "lagoon", "lantern", "leaf", "lemon", "lily", "lunar",
    "maple", "marble", "meadow", "meteor", "moon", "moss", "mountain", "nebula",
    "oasis", "ocean", "olive", "opal", "orbit", "otter", "owl", "palace",
    "panda", "panther", "parrot", "pebble", "penguin", "petal", "piano", "pine",
    "planet", "pocket", "polar", "prairie", "quartz", "rabbit", "rainbow", "raven",
    "river", "robin", "rocket", "ruby", "sailor", "sapphire", "shadow", "shell",
    "silver", "solar", "sparrow", "spring", "star", "stream", "summer", "sunshine",
    "swallow", "tiger", "timber", "topaz", "tulip", "turtle", "valley", "velvet",
    "violet", "volcano", "walnut", "water", "willow", "winter", "wizard", "wood"
]

def generate_safe_verification_code(word_count: int = 4) -> str:
    """
    Generates a censorship-proof verification code consisting of randomly selected
    safe words separated by spaces.
    Example: 'silver candle river guitar'
    """
    selected_words = random.sample(FILTER_SAFE_WORDS, word_count)
    return " ".join(selected_words)
