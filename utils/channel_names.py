"""Generate random adjective-animal channel names for temp voice channels."""

import random

ADJECTIVES = [
    "Angry", "Brave", "Caffeinated", "Chaotic", "Cheeky", "Chunky",
    "Clumsy", "Cranky", "Crispy", "Daring", "Dizzy", "Feisty",
    "Fluffy", "Funky", "Grumpy", "Hasty", "Hungry", "Jazzy",
    "Jolly", "Jumpy", "Lanky", "Lazy", "Lucky", "Mighty",
    "Moody", "Nerdy", "Noisy", "Nutty", "Perky", "Rowdy",
    "Rusty", "Salty", "Savage", "Shady", "Sketchy", "Slippery",
    "Sneaky", "Spicy", "Stormy", "Stubborn", "Tactical", "Toasty",
    "Tricky", "Turbo", "Unhinged", "Wacky", "Wiggly", "Wobbly",
    "Wonky", "Zesty",
]

ANIMALS = [
    "Alpaca", "Badger", "Capybara", "Chicken", "Chinchilla", "Corgi",
    "Coyote", "Crow", "Donkey", "Duckling", "Ferret", "Flamingo",
    "Frog", "Gecko", "Goat", "Hamster", "Hedgehog", "Hippo",
    "Iguana", "Koala", "Lemur", "Llama", "Lobster", "Moose",
    "Narwhal", "Newt", "Otter", "Owl", "Pangolin", "Parrot",
    "Pelican", "Penguin", "Pigeon", "Platypus", "Porcupine", "Possum",
    "Puffin", "Quokka", "Raccoon", "Salamander", "Seagull", "Sloth",
    "Squirrel", "Tapir", "Toucan", "Walrus", "Warthog", "Wombat",
    "Yak", "Zebra",
]


def generate_channel_name() -> str:
    """Return a random 'Adjective Animal' name for a temp voice channel."""
    return f"{random.choice(ADJECTIVES)} {random.choice(ANIMALS)}"
