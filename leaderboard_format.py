"""
Rendering for the /leaderboard command.

Kept out of bot.py so the wording of each board is importable and testable
without booting the bot (importing bot.py connects to Discord).

There are three boards and they answer three different questions:

* all-time (default) — everything a member has earned. Spending never lowers
  it, so buying a role colour does not cost a member their rank.
* balance — what is left to spend right now.
* spenders — who has actually used their points, which is the behaviour the
  economy wants to encourage.
"""

from typing import Any, Dict, List

# The board a member picks in Discord, and the ordering it maps to. Kept here
# rather than inline in the command so a test can prove the choice Discord
# sends ('spenders') is the ordering the formatter switches on ('spent') — an
# inline dict let a test pass with the friendly name while the live command
# sent the canonical one, and the spenders board came out with the all-time
# footer.
BOARD_ORDERS = {
    "all-time": "lifetime",
    "balance": "balance",
    "spenders": "spent",
}

BOARD_ORDERINGS = ("lifetime", "balance", "spent")


def order_for(board: str) -> str:
    """Map a /leaderboard board choice to the ordering database uses."""
    return BOARD_ORDERS.get(board, "lifetime")


def format_leaderboard_message(leaderboard: List[Dict[str, Any]], order_by: str) -> str:
    """Render a leaderboard as a Discord message.

    Args:
        leaderboard: rows as database.get_leaderboard returns them, already in
            rank order for the requested board
        order_by: 'lifetime' (all-time), 'balance' or 'spent' (spenders)
    """
    if order_by not in BOARD_ORDERINGS:
        raise ValueError(f"Unknown leaderboard ordering: {order_by!r}")

    if order_by == "lifetime":
        message = f"🏆 **Top {len(leaderboard)} contributors** — points earned all-time\n\n"
    elif order_by == "balance":
        message = f"💰 **Top {len(leaderboard)} balances** — points left to spend\n\n"
    else:
        message = f"💸 **Top {len(leaderboard)} spenders** — points used in the server\n\n"

    for idx, entry in enumerate(leaderboard, 1):
        balance = entry['total_points']
        lifetime = entry.get('lifetime_points', balance)
        spent = entry.get('spent', lifetime - balance)

        # Add medal emojis for top 3
        if idx == 1:
            medal = "🥇"
        elif idx == 2:
            medal = "🥈"
        elif idx == 3:
            medal = "🥉"
        else:
            medal = f"{idx}."

        if order_by == "lifetime":
            detail = f"{lifetime} earned · {balance} left"
        elif order_by == "balance":
            detail = f"{balance} left · {lifetime} earned"
        else:
            detail = f"{spent} spent · {balance} left"

        message += f"{medal} **{entry['author_name']}**: {detail}\n"

    if order_by == "spent":
        message += "\nPoints are spent on a role colour, a GIF bypass or frenbot access."
    elif order_by == "balance":
        message += (
            "\nThis board ranks on what is left in the wallet. The default board — "
            "all-time earned — is the one that shows who has contributed most."
        )
    else:
        message += (
            "\nRanked on everything a member has earned — spending points never lowers it. "
            "Pick the 'biggest spenders' board to see who is using theirs."
        )

    return message
