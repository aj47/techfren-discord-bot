"""
Profile bot startup to identify bottlenecks.
"""

import time

# Track import times
import_times = []


def track_import(module_name):
    start = time.time()
    __import__(module_name)
    elapsed = time.time() - start
    import_times.append((module_name, elapsed))
    print(f"{module_name}: {elapsed:.3f}s")


print("=== Profiling Bot Startup ===\n")

print("Core imports:")
track_import("discord")
track_import("asyncio")
track_import("re")

print("\nBot-specific imports:")
track_import("database")
track_import("logging_config")
track_import("llm_handler")
track_import("youtube_handler")
track_import("summarization_tasks")
track_import("config_validator")
track_import("command_handler")
track_import("thread_memory")
track_import("firecrawl_handler")
track_import("apify_handler")

print("\n=== Summary ===")
import_times.sort(key=lambda x: x[1], reverse=True)
print("\nSlowest imports:")
for module, duration in import_times[:10]:
    print(f"  {module}: {duration:.3f}s")

total = sum(t[1] for t in import_times)
print(f"\nTotal import time: {total:.3f}s")
