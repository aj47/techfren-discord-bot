"""
Utility functions for handling datetime operations consistently across the codebase.
All functions ensure proper timezone handling using UTC.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

def get_utc_now() -> datetime:
    """
    Get the current datetime in UTC.
    
    Returns:
        datetime: Current UTC datetime with timezone info
    """
    return datetime.now(timezone.utc)

def make_aware(dt: datetime) -> datetime:
    """
    Ensure a datetime object has timezone information.
    If it doesn't, assume it's UTC.
    
    Args:
        dt (datetime): The datetime object to make timezone-aware
        
    Returns:
        datetime: Timezone-aware datetime object
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_day_boundaries(date: datetime) -> Tuple[datetime, datetime]:
    """
    Get the start and end boundaries of a day in UTC.
    
    Args:
        date (datetime): The date to get boundaries for
        
    Returns:
        Tuple[datetime, datetime]: Start and end of the day in UTC
    """
    # Ensure date has timezone information
    date = make_aware(date)
    
    # Convert to UTC to ensure consistency
    date_utc = date.astimezone(timezone.utc)
    
    # Create start and end of day in UTC
    start_date = datetime(date_utc.year, date_utc.month, date_utc.day, 
                          0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(date_utc.year, date_utc.month, date_utc.day, 
                         23, 59, 59, 999999, tzinfo=timezone.utc)
    
    return start_date, end_date

def get_week_boundaries(start_date: datetime) -> Tuple[datetime, datetime]:
    """
    Get the start and end boundaries of a week in UTC.
    
    Args:
        start_date (datetime): The start date of the week
        
    Returns:
        Tuple[datetime, datetime]: Start and end of the week in UTC
    """
    # Ensure date has timezone information
    start_date = make_aware(start_date)
    
    # Convert to UTC to ensure consistency
    start_date_utc = start_date.astimezone(timezone.utc)
    
    # Create start of week in UTC
    start_of_week = datetime(start_date_utc.year, start_date_utc.month, start_date_utc.day, 
                            0, 0, 0, tzinfo=timezone.utc)
    
    # Create end of week in UTC (6 days, 23 hours, 59 minutes, 59 seconds, 999999 microseconds later)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    
    return start_of_week, end_of_week

def format_date_for_display(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """
    Format a datetime object for display purposes.
    
    Args:
        dt (datetime): The datetime to format
        format_str (str): The format string to use
        
    Returns:
        str: The formatted datetime string
    """
    # Ensure datetime has timezone info
    dt = make_aware(dt)
    return dt.strftime(format_str)

def parse_iso_datetime(iso_str: str) -> datetime:
    """
    Parse an ISO format datetime string to a datetime object with timezone info.
    
    Args:
        iso_str (str): ISO format datetime string
        
    Returns:
        datetime: Datetime object with timezone info
    """
    dt = datetime.fromisoformat(iso_str)
    return make_aware(dt)
