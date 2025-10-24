"""
Test bot cold start time by monitoring on_ready event.
"""

import asyncio
import time

import discord
from discord.ext import commands

# Track startup timing
startup_times = {
    "start": time.time(),
    "imports_done": None,
    "ready": None,
}

print(f"[{time.time() - startup_times['start']:.3f}s] Starting imports...")

import database  # noqa: E402


startup_times["imports_done"] = time.time()
print(
    f"[{startup_times['imports_done'] - startup_times['start']:.3f}s] Imports complete"
)

# Create bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    startup_times["ready"] = time.time()

    print("\n=== Bot Startup Complete ===")
    print(
        f"Time to imports: {
            startup_times['imports_done'] -
            startup_times['start']:.3f}s")
    print(f"Time to on_ready: {startup_times['ready'] - startup_times['start']:.3f}s")
    print(f"Time in on_ready handler: {time.time() - startup_times['ready']:.3f}s")

    # Initialize database to measure this cost
    db_start = time.time()
    database.init_database()
    db_time = time.time() - db_start
    print(f"Database init: {db_time:.3f}s")

    # Check message count
    count_start = time.time()
    message_count = database.get_message_count()
    count_time = time.time() - count_start
    print(f"Message count query ({message_count} messages): {count_time:.3f}s")

    print(f"\nTotal cold start time: {time.time() - startup_times['start']:.3f}s")

    # Exit after measuring
    await bot.close()


# Note: This would need a real token to connect
print(f"[{time.time() - startup_times['start']:.3f}s] Bot object created")
print("\nNote: Cannot connect without valid token.")
print("Measuring on_ready() operations only...")


# Simulate on_ready operations
async def simulate_startup():
    print(
        f"\n[{
            time.time() -
            startup_times['start']:.3f}s] Simulating on_ready operations...")

    # Database init
    db_start = time.time()
    database.init_database()
    db_time = time.time() - db_start
    print(f"Database init: {db_time:.3f}s")

    # Database connection check
    check_start = time.time()
    database.check_database_connection()
    check_time = time.time() - check_start
    print(f"Database connection check: {check_time:.3f}s")

    # Message count
    count_start = time.time()
    message_count = database.get_message_count()
    count_time = time.time() - count_start
    print(f"Message count query ({message_count} messages): {count_time:.3f}s")

    print(f"\nTotal startup operations: {time.time() - startup_times['start']:.3f}s")


asyncio.run(simulate_startup())
