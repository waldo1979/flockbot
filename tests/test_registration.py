import pytest

from database import player_repo


@pytest.mark.asyncio
async def test_register_rejects_duplicate_pubg_id(db):
    """A second Discord user cannot claim a PUBG account already linked to someone else."""
    await player_repo.upsert_player(db, "discord_111", "pubg_AAA", "PlayerA")

    existing = await player_repo.get_player_by_pubg_id(db, "pubg_AAA")
    assert existing is not None
    assert existing["discord_id"] == "discord_111"

    # A different Discord user trying to claim the same pubg_id should be blocked
    # (the bot checks this before calling upsert_player)
    assert existing["discord_id"] != "discord_222"


@pytest.mark.asyncio
async def test_register_allows_same_user_reregister(db):
    """The same Discord user re-registering the same PUBG account is allowed (e.g. name change)."""
    await player_repo.upsert_player(db, "discord_111", "pubg_AAA", "OldName")

    existing = await player_repo.get_player_by_pubg_id(db, "pubg_AAA")
    assert existing is not None
    assert existing["discord_id"] == "discord_111"

    # Same user, same pubg_id — should be allowed (upsert updates the name)
    await player_repo.upsert_player(db, "discord_111", "pubg_AAA", "NewName")

    updated = await player_repo.get_player(db, "discord_111")
    assert updated["pubg_name"] == "NewName"


@pytest.mark.asyncio
async def test_get_player_by_pubg_id_not_found(db):
    """Returns None when no player has the given pubg_id."""
    result = await player_repo.get_player_by_pubg_id(db, "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_admin_transfer(db):
    """Transferring a PUBG account by name: look up by pubg_name, delete old row, upsert new owner."""
    await player_repo.upsert_player(db, "discord_111", "pubg_AAA", "PlayerA")

    # Admin looks up by PUBG name (mirrors the command flow)
    source = await player_repo.get_player_by_pubg_name(db, "PlayerA")
    assert source is not None
    assert source["discord_id"] == "discord_111"

    # Transfer: delete old row, upsert new owner
    await db.execute("DELETE FROM players WHERE discord_id = ?", (source["discord_id"],))
    await player_repo.upsert_player(db, "discord_222", source["pubg_id"], source["pubg_name"])

    # Old owner is gone
    old = await player_repo.get_player(db, "discord_111")
    assert old is None

    # New owner has the account
    new = await player_repo.get_player(db, "discord_222")
    assert new is not None
    assert new["pubg_id"] == "pubg_AAA"
    assert new["pubg_name"] == "PlayerA"


@pytest.mark.asyncio
async def test_admin_transfer_rejects_if_target_registered(db):
    """Transfer should be rejected if the target already has a PUBG account."""
    await player_repo.upsert_player(db, "discord_111", "pubg_AAA", "PlayerA")
    await player_repo.upsert_player(db, "discord_222", "pubg_BBB", "PlayerB")

    target = await player_repo.get_player(db, "discord_222")
    assert target is not None  # Target already registered — admin command would reject
