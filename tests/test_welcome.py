from services.welcome import parse_welcome_messages


SAMPLE = """\
# Welcome to Flockbot

Post each section below as a separate message in your Discord #rules channel.

---

**MESSAGE 1:**

## Welcome

Hello world.

---

**MESSAGE 2:**

## Rules

1. Be nice
2. Have fun

---

**MESSAGE 3:**

## Commands

- `/help` — get help
"""


def test_parse_welcome_messages():
    messages = parse_welcome_messages(SAMPLE)
    assert len(messages) == 3
    assert messages[0].startswith("## Welcome")
    assert "Hello world." in messages[0]
    assert messages[1].startswith("## Rules")
    assert messages[2].startswith("## Commands")


def test_parse_strips_message_labels():
    messages = parse_welcome_messages(SAMPLE)
    for msg in messages:
        assert "**MESSAGE" not in msg


def test_parse_actual_welcome_file():
    """Ensure the real discord-welcome.md parses into 3 messages."""
    from services.welcome import WELCOME_PATH

    text = WELCOME_PATH.read_text(encoding="utf-8")
    messages = parse_welcome_messages(text)
    assert len(messages) == 3
    assert "## Welcome" in messages[0]
    assert "## Skill Tiers" in messages[1]
    assert "## Other Commands" in messages[2]
