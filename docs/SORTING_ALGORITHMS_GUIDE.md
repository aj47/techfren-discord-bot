# Sorting Algorithms for Discord Bot

## 📊 **Where to Use Sorting Algorithms in Your Code**

### **1. Quick Sort - BEST FOR YOUR USE CASE** ⭐
**Time Complexity:** O(n log n) average, O(n²) worst
**Space Complexity:** O(log n)
**Best for:** General-purpose sorting, medium to large datasets

#### **Use Cases in Your Bot:**
```python
# ✅ Sorting messages by timestamp (most common operation)
# File: database.py - get_channel_messages_for_hours()
def quick_sort_messages(messages, key='created_at', reverse=False):
    """Sort messages using QuickSort algorithm."""
    if len(messages) <= 1:
        return messages
    
    pivot = messages[len(messages) // 2]
    pivot_value = pivot.get(key)
    
    if reverse:
        left = [x for x in messages if x.get(key) > pivot_value]
        middle = [x for x in messages if x.get(key) == pivot_value]
        right = [x for x in messages if x.get(key) < pivot_value]
    else:
        left = [x for x in messages if x.get(key) < pivot_value]
        middle = [x for x in messages if x.get(key) == pivot_value]
        right = [x for x in messages if x.get(key) > pivot_value]
    
    return quick_sort_messages(left, key, reverse) + middle + quick_sort_messages(right, key, reverse)

# Usage:
# messages = quick_sort_messages(messages, key='created_at', reverse=False)
```

---

### **2. Merge Sort - STABLE & PREDICTABLE**
**Time Complexity:** O(n log n) always
**Space Complexity:** O(n)
**Best for:** When you need guaranteed O(n log n) performance, stable sorting

#### **Use Cases:**
```python
# ✅ Sorting active users/channels with guaranteed performance
# File: summarization_tasks.py
def merge_sort_channels(channels, key='message_count', reverse=True):
    """Stable sort for channel activity data."""
    if len(channels) <= 1:
        return channels
    
    mid = len(channels) // 2
    left = merge_sort_channels(channels[:mid], key, reverse)
    right = merge_sort_channels(channels[mid:], key, reverse)
    
    return merge(left, right, key, reverse)

def merge(left, right, key, reverse):
    result = []
    i = j = 0
    
    while i < len(left) and j < len(right):
        left_val = left[i].get(key, 0)
        right_val = right[j].get(key, 0)
        
        if (left_val <= right_val) != reverse:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    
    result.extend(left[i:])
    result.extend(right[j:])
    return result

# Usage:
# active_channels = merge_sort_channels(active_channels, 'message_count', reverse=True)
```

---

### **3. Insertion Sort - SMALL DATASETS**
**Time Complexity:** O(n²)
**Space Complexity:** O(1)
**Best for:** Small datasets (< 50 items), nearly sorted data

#### **Use Cases:**
```python
# ✅ Sorting small lists like top users (< 10 items)
# File: command_abstraction.py - active_users list
def insertion_sort_users(users, key='message_count', reverse=True):
    """Efficient for small user lists."""
    for i in range(1, len(users)):
        current = users[i]
        current_val = current.get(key, 0)
        j = i - 1
        
        while j >= 0:
            compare_val = users[j].get(key, 0)
            if (compare_val > current_val) == reverse:
                break
            users[j + 1] = users[j]
            j -= 1
        
        users[j + 1] = current
    
    return users

# Usage:
# top_users = insertion_sort_users(active_users[:10], 'message_count', reverse=True)
```

---

### **4. Bucket Sort - NUMERIC RANGES**
**Time Complexity:** O(n + k) where k is number of buckets
**Space Complexity:** O(n + k)
**Best for:** Uniformly distributed numeric data

#### **Use Cases:**
```python
# ✅ Sorting messages by hour of day (0-23)
# File: llm_handler.py - for time-based analysis
def bucket_sort_by_hour(messages):
    """Sort messages into hourly buckets."""
    buckets = [[] for _ in range(24)]
    
    for msg in messages:
        created_at = msg.get('created_at')
        if hasattr(created_at, 'hour'):
            hour = created_at.hour
            buckets[hour].append(msg)
    
    # Flatten buckets
    sorted_messages = []
    for bucket in buckets:
        sorted_messages.extend(bucket)
    
    return sorted_messages

# Usage:
# messages_by_hour = bucket_sort_by_hour(messages)
```

---

### **5. Radix Sort - INTEGER IDs**
**Time Complexity:** O(d * n) where d is number of digits
**Space Complexity:** O(n + k)
**Best for:** Sorting integer IDs, timestamps as integers

#### **Use Cases:**
```python
# ✅ Sorting message IDs (Discord snowflakes are large integers)
# File: database.py
def radix_sort_ids(messages, key='id'):
    """Sort by Discord message IDs (snowflakes)."""
    if not messages:
        return messages
    
    # Convert to integers
    items = [(int(msg.get(key, 0)), msg) for msg in messages]
    
    # Find maximum number to know number of digits
    max_num = max(item[0] for item in items)
    
    exp = 1
    while max_num // exp > 0:
        items = counting_sort_by_digit(items, exp)
        exp *= 10
    
    return [item[1] for item in items]

def counting_sort_by_digit(items, exp):
    n = len(items)
    output = [None] * n
    count = [0] * 10
    
    for i in range(n):
        index = (items[i][0] // exp) % 10
        count[index] += 1
    
    for i in range(1, 10):
        count[i] += count[i - 1]
    
    i = n - 1
    while i >= 0:
        index = (items[i][0] // exp) % 10
        output[count[index] - 1] = items[i]
        count[index] -= 1
        i -= 1
    
    return output

# Usage:
# sorted_messages = radix_sort_ids(messages, key='id')
```

---

### **6. Heap Sort / Priority Queue**
**Time Complexity:** O(n log n)
**Space Complexity:** O(1)
**Best for:** Finding top-K items, priority-based processing

#### **Use Cases:**
```python
# ✅ Finding top N most active users efficiently
# File: llm_handler.py - for summary statistics
import heapq

def get_top_n_users(messages, n=5):
    """Get top N most active users using min-heap."""
    user_counts = {}
    
    for msg in messages:
        user = msg.get('author_name', 'Unknown')
        if not msg.get('is_bot', False):
            user_counts[user] = user_counts.get(user, 0) + 1
    
    # Use heap to efficiently get top N
    return heapq.nlargest(n, user_counts.items(), key=lambda x: x[1])

# Usage:
# top_users = get_top_n_users(messages, n=10)
```

---

## 🎯 **Recommended Implementation Plan**

### **Priority 1: Replace Python's Built-in Sort (Optional)**
```python
# Current code uses:
messages.sort(key=lambda x: x['created_at'])

# Can be replaced with QuickSort for educational purposes:
messages = quick_sort_messages(messages, key='created_at')
```

### **Priority 2: Add to database.py**
```python
# Add sorting utilities module
class MessageSorter:
    """Efficient sorting algorithms for message data."""
    
    @staticmethod
    def by_timestamp(messages, reverse=False):
        """Quick sort by timestamp."""
        return quick_sort_messages(messages, 'created_at', reverse)
    
    @staticmethod
    def by_author(messages):
        """Sort messages by author name."""
        return quick_sort_messages(messages, 'author_name', reverse=False)
    
    @staticmethod
    def by_length(messages, reverse=True):
        """Sort by message content length."""
        return sorted(messages, key=lambda x: len(x.get('content', '')), reverse=reverse)
```

### **Priority 3: Chart Data Sorting**
```python
# File: chart_renderer.py
# Add sorting for chart data points
def sort_chart_data(data, sort_by='value'):
    """Sort chart data points efficiently."""
    if len(data) < 50:
        return insertion_sort_users(data, key=sort_by)
    else:
        return quick_sort_messages(data, key=sort_by)
```

---

## ⚡ **Performance Comparison for Your Use Cases**

| Algorithm | Best Use Case | Your Data Size | Recommended? |
|-----------|--------------|----------------|--------------|
| **Quick Sort** | Messages (100-10000) | ✅ Perfect | ⭐⭐⭐⭐⭐ |
| **Merge Sort** | Active channels (10-100) | ✅ Good | ⭐⭐⭐⭐ |
| **Insertion Sort** | Top users (<20) | ✅ Perfect | ⭐⭐⭐⭐⭐ |
| **Bucket Sort** | Hour-based grouping | ✅ Perfect | ⭐⭐⭐⭐ |
| **Radix Sort** | Message IDs | ✅ Good | ⭐⭐⭐ |
| **Heap Sort** | Top-N queries | ✅ Perfect | ⭐⭐⭐⭐⭐ |
| **Bubble Sort** | ❌ Never | Too slow | ⭐ |
| **Selection Sort** | ❌ Never | Too slow | ⭐ |

---

## 🚀 **Quick Start: Add to Your Bot**

Create a new file: `sorting_utils.py`
```python
"""Efficient sorting algorithms for Discord bot data processing."""

def quick_sort(items, key=None, reverse=False):
    """General-purpose quick sort implementation."""
    # Implementation above
    pass

def merge_sort(items, key=None, reverse=False):
    """Stable merge sort implementation."""
    # Implementation above
    pass

def insertion_sort(items, key=None, reverse=False):
    """Insertion sort for small lists."""
    # Implementation above
    pass

def bucket_sort_by_hour(messages):
    """Bucket sort for time-based grouping."""
    # Implementation above
    pass
```

Then import and use:
```python
from sorting_utils import quick_sort, insertion_sort

# In your database.py or llm_handler.py
messages = quick_sort(messages, key='created_at')
top_users = insertion_sort(top_users, key='message_count', reverse=True)
```

---

## 📝 **Note:**
Python's built-in `sorted()` and `.sort()` use **Timsort** (hybrid of merge sort and insertion sort), which is already excellent for most cases. Implementing custom algorithms is mainly for:
1. **Learning purposes** - Understanding how algorithms work
2. **Custom sorting logic** - Special business rules
3. **Performance optimization** - Specific use cases where you know data characteristics

For production, Python's built-in sorting is usually the best choice unless you have specific requirements!
