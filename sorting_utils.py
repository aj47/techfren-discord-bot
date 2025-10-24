"""
Sorting algorithms and utilities for Discord bot data processing.

This module provides efficient sorting implementations for various bot operations.
While Python's built-in Timsort is excellent, these implementations are useful for:
- Learning algorithm concepts
- Custom sorting requirements
- Performance optimization for specific data patterns
"""

from typing import List, Dict, Any, Optional
import heapq


# ============================================================================
# QUICK SORT - Best general-purpose algorithm for your bot
# ============================================================================

def quick_sort(
        items: List[Any],
        key: Optional[str] = None,
        reverse: bool = False) -> List[Any]:
    """
    Quick Sort implementation - O(n log n) average case.

    Best for: General-purpose sorting of messages, channels, users (100-10000 items)

    Args:
        items: List of items to sort
        key: Dictionary key to sort by (e.g., 'created_at', 'message_count')
        reverse: Sort in descending order if True

    Returns:
        Sorted list

    Example:
        messages = quick_sort(messages, key='created_at')
        active_users = quick_sort(users, key='message_count', reverse=True)
    """
    if len(items) <= 1:
        return items

    pivot = items[len(items) // 2]
    pivot_value = pivot.get(key) if key and isinstance(pivot, dict) else pivot

    def get_value(item):
        return item.get(key) if key and isinstance(item, dict) else item

    if reverse:
        left = [x for x in items if get_value(x) > pivot_value]
        middle = [x for x in items if get_value(x) == pivot_value]
        right = [x for x in items if get_value(x) < pivot_value]
    else:
        left = [x for x in items if get_value(x) < pivot_value]
        middle = [x for x in items if get_value(x) == pivot_value]
        right = [x for x in items if get_value(x) > pivot_value]

    return quick_sort(left, key, reverse) + middle + quick_sort(right, key, reverse)


# ============================================================================
# MERGE SORT - Stable and predictable performance
# ============================================================================

def merge_sort(
        items: List[Any],
        key: Optional[str] = None,
        reverse: bool = False) -> List[Any]:
    """
    Merge Sort implementation - O(n log n) worst case (stable).

    Best for: When you need guaranteed performance, preserving order of equal elements

    Args:
        items: List of items to sort
        key: Dictionary key to sort by
        reverse: Sort in descending order if True

    Returns:
        Sorted list

    Example:
        channels = merge_sort(channels, key='message_count', reverse=True)
    """
    if len(items) <= 1:
        return items

    mid = len(items) // 2
    left = merge_sort(items[:mid], key, reverse)
    right = merge_sort(items[mid:], key, reverse)

    return _merge(left, right, key, reverse)


def _merge(
        left: List[Any],
        right: List[Any],
        key: Optional[str],
        reverse: bool) -> List[Any]:
    """Helper function for merge sort."""
    result = []
    i = j = 0

    def get_value(item):
        return item.get(key) if key and isinstance(item, dict) else item

    while i < len(left) and j < len(right):
        left_val = get_value(left[i])
        right_val = get_value(right[j])

        if (left_val <= right_val) != reverse:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    result.extend(left[i:])
    result.extend(right[j:])
    return result


# ============================================================================
# INSERTION SORT - Best for small datasets
# ============================================================================

def insertion_sort(
        items: List[Any],
        key: Optional[str] = None,
        reverse: bool = False) -> List[Any]:
    """
    Insertion Sort implementation - O(n²) but efficient for small lists.

    Best for: Small datasets (< 50 items), top-N users, nearly sorted data

    Args:
        items: List of items to sort
        key: Dictionary key to sort by
        reverse: Sort in descending order if True

    Returns:
        Sorted list (in-place modification)

    Example:
        top_users = insertion_sort(active_users[:10], key='message_count', reverse=True)
    """
    items_copy = items.copy()

    def get_value(item):
        return item.get(key) if key and isinstance(item, dict) else item

    for i in range(1, len(items_copy)):
        current = items_copy[i]
        current_val = get_value(current)
        j = i - 1

        while j >= 0:
            compare_val = get_value(items_copy[j])
            if (compare_val > current_val) == reverse:
                break
            items_copy[j + 1] = items_copy[j]
            j -= 1

        items_copy[j + 1] = current

    return items_copy


# ============================================================================
# BUCKET SORT - For time-based grouping
# ============================================================================

def bucket_sort_by_hour(
        messages: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """
    Bucket Sort by hour of day - O(n + k) where k=24.

    Best for: Grouping messages by hour for time-based analysis

    Args:
        messages: List of message dictionaries with 'created_at' datetime field

    Returns:
        Dictionary mapping hour (0-23) to list of messages

    Example:
        hourly_messages = bucket_sort_by_hour(messages)
        peak_hour = max(hourly_messages.items(), key=lambda x: len(x[1]))[0]
    """
    buckets = {hour: [] for hour in range(24)}

    for msg in messages:
        created_at = msg.get('created_at')
        if created_at and hasattr(created_at, 'hour'):
            hour = created_at.hour
            buckets[hour].append(msg)

    return buckets


def bucket_sort_by_day_of_week(
        messages: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """
    Bucket Sort by day of week - O(n + k) where k=7.

    Args:
        messages: List of message dictionaries with 'created_at' datetime field

    Returns:
        Dictionary mapping weekday (0=Monday, 6=Sunday) to list of messages
    """
    buckets = {day: [] for day in range(7)}

    for msg in messages:
        created_at = msg.get('created_at')
        if created_at and hasattr(created_at, 'weekday'):
            day = created_at.weekday()
            buckets[day].append(msg)

    return buckets


# ============================================================================
# HEAP-BASED TOP-N SELECTION
# ============================================================================


def get_top_n(items: List[Dict[str, Any]], n: int, key: str,
              reverse: bool = True) -> List[Dict[str, Any]]:
    """
    Get top N items efficiently using heap - O(n + k log n).

    Best for: Finding top-N most active users, channels, etc.

    Args:
        items: List of items
        n: Number of top items to return
        key: Dictionary key to compare by
        reverse: True for largest values, False for smallest

    Returns:
        List of top N items

    Example:
        top_10_users = get_top_n(users, n=10, key='message_count')
    """
    if reverse:
        return heapq.nlargest(n, items, key=lambda x: x.get(key, 0))
    else:
        return heapq.nsmallest(n, items, key=lambda x: x.get(key, 0))


def get_top_n_tuples(items: List[tuple], n: int, reverse: bool = True) -> List[tuple]:
    """
    Get top N from list of tuples - O(n + k log n).

    Example:
        user_counts = [('user1', 50), ('user2', 30), ('user3', 80)]
        top_users = get_top_n_tuples(user_counts, n=2)  # [('user3', 80), ('user1', 50)]
    """
    if reverse:
        return heapq.nlargest(n, items, key=lambda x: x[1])
    else:
        return heapq.nsmallest(n, items, key=lambda x: x[1])


# ============================================================================
# SMART SORT - Automatic algorithm selection
# ============================================================================

def smart_sort(
        items: List[Any],
        key: Optional[str] = None,
        reverse: bool = False) -> List[Any]:
    """
    Automatically choose the best sorting algorithm based on data size.

    - Small (< 20): Insertion Sort
    - Medium (20-1000): Quick Sort
    - Large (> 1000): Merge Sort (guaranteed performance)

    Args:
        items: List of items to sort
        key: Dictionary key to sort by
        reverse: Sort in descending order if True

    Returns:
        Sorted list

    Example:
        messages = smart_sort(messages, key='created_at')
    """
    size = len(items)

    if size < 20:
        return insertion_sort(items, key, reverse)
    elif size < 1000:
        return quick_sort(items, key, reverse)
    else:
        return merge_sort(items, key, reverse)


# ============================================================================
# CONVENIENCE FUNCTIONS FOR DISCORD BOT
# ============================================================================

class MessageSorter:
    """Specialized sorting functions for Discord message data."""

    @staticmethod
    def by_timestamp(messages: List[Dict[str, Any]],
                     reverse: bool = False) -> List[Dict[str, Any]]:
        """Sort messages by creation timestamp."""
        return quick_sort(messages, key='created_at', reverse=reverse)

    @staticmethod
    def by_author(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort messages by author name."""
        return quick_sort(messages, key='author_name', reverse=False)

    @staticmethod
    def by_content_length(messages: List[Dict[str, Any]],
                          reverse: bool = True) -> List[Dict[str, Any]]:
        """Sort messages by content length (longest first by default)."""
        messages_with_length = [
            {**msg, '_length': len(msg.get('content', ''))}
            for msg in messages
        ]
        sorted_msgs = quick_sort(messages_with_length, key='_length', reverse=reverse)
        # Remove temporary _length key
        for msg in sorted_msgs:
            msg.pop('_length', None)
        return sorted_msgs

    @staticmethod
    def by_hour(messages: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
        """Group messages by hour of day."""
        return bucket_sort_by_hour(messages)


class UserSorter:
    """Specialized sorting functions for user data."""

    @staticmethod
    def by_activity(users: List[Dict[str, Any]],
                    reverse: bool = True) -> List[Dict[str, Any]]:
        """Sort users by activity/message count."""
        return quick_sort(users, key='message_count', reverse=reverse)

    @staticmethod
    def top_n(users: List[Dict[str, Any]], n: int,
              key: str = 'message_count') -> List[Dict[str, Any]]:
        """Get top N most active users efficiently."""
        return get_top_n(users, n, key, reverse=True)


class ChannelSorter:
    """Specialized sorting functions for channel data."""

    @staticmethod
    def by_activity(channels: List[Dict[str, Any]],
                    reverse: bool = True) -> List[Dict[str, Any]]:
        """Sort channels by message count."""
        return merge_sort(channels, key='message_count', reverse=reverse)

    @staticmethod
    def by_name(channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort channels alphabetically by name."""
        return quick_sort(channels, key='channel_name', reverse=False)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Example 1: Sort messages by timestamp
    messages = [
        {'id': '1', 'content': 'Hello', 'created_at': '2024-01-01 10:00:00'},
        {'id': '2', 'content': 'Hi', 'created_at': '2024-01-01 09:00:00'},
        {'id': '3', 'content': 'Hey', 'created_at': '2024-01-01 11:00:00'},
    ]
    sorted_messages = MessageSorter.by_timestamp(messages)
    print("Messages sorted by timestamp:", sorted_messages)

    # Example 2: Get top 5 users
    users = [
        {'name': 'Alice', 'message_count': 50},
        {'name': 'Bob', 'message_count': 30},
        {'name': 'Charlie', 'message_count': 80},
        {'name': 'David', 'message_count': 45},
    ]
    top_users = UserSorter.top_n(users, n=2)
    print("Top 2 users:", top_users)

    # Example 3: Smart sort automatically chooses best algorithm
    data = list(range(100, 0, -1))
    sorted_data = smart_sort(data)
    print("Smart sorted:", sorted_data[:5], "...")
