import discord


def stats_embed(
    pubg_name: str,
    squad_adr: float | None,
    squad_tier: str | None,
    squad_matches: int,
    duo_adr: float | None,
    duo_tier: str | None,
    duo_matches: int,
    season: str | None,
    is_fallback_squad: bool = False,
    is_fallback_duo: bool = False,
) -> discord.Embed:
    embed = discord.Embed(title=f"Stats: {pubg_name}", color=0x1ABC9C)

    squad_val = _format_adr_line(squad_adr, squad_tier, squad_matches, is_fallback_squad)
    embed.add_field(name="Squad FPP", value=squad_val, inline=True)

    duo_val = _format_adr_line(duo_adr, duo_tier, duo_matches, is_fallback_duo)
    embed.add_field(name="Duo FPP", value=duo_val, inline=True)

    if season:
        embed.set_footer(text=f"Season: {season}")
    return embed


def _format_adr_line(
    adr: float | None, tier: str | None, matches: int, is_fallback: bool
) -> str:
    if adr is None:
        return "New"
    label = f"**{adr:.0f}** ADR ({tier})"
    suffix = f"\n{matches} matches"
    if is_fallback:
        suffix += " *(prev season)*"
    return label + suffix


def queue_embed(queue_type: str, players: list[dict]) -> discord.Embed:
    title = f"LFG {queue_type.capitalize()} Queue"
    embed = discord.Embed(title=title, color=0x3498DB)
    if not players:
        embed.description = "No players in queue."
        return embed
    lines = []
    for p in players:
        tier = p.get("tier") or "New"
        lines.append(f"**{p['pubg_name']}** — {tier}")
    embed.description = "\n".join(lines)
    return embed


def squad_embed(group: list[dict], group_num: int, queue_type: str) -> discord.Embed:
    title = f"{queue_type.capitalize()} #{group_num}"
    embed = discord.Embed(title=title, color=0x2ECC71)
    lines = []
    for p in group:
        tier = p.get("tier") or "New"
        lines.append(f"**{p['pubg_name']}** — {tier}")
    embed.description = "\n".join(lines)
    return embed


def leaderboard_embed(
    players: list[dict], mode: str, season: str | None
) -> discord.Embed:
    mode_label = "Squad FPP" if mode == "squad-fpp" else "Duo FPP"
    embed = discord.Embed(title=f"Leaderboard — {mode_label}", color=0xF1C40F)
    if not players:
        embed.description = "No players with stats yet."
        return embed
    lines = []
    for i, p in enumerate(players, 1):
        lines.append(f"**{i}.** {p['pubg_name']} — **{p['adr']:.0f}** ADR ({p['tier']})")
    embed.description = "\n".join(lines)
    if season:
        embed.set_footer(text=f"Season: {season}")
    return embed
