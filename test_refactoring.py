"""
Test script to verify the refactored functions in database.py
"""

import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
import database

class TestDatabaseRefactoring(unittest.TestCase):
    """Test the refactored database functions"""

    @patch('database.get_channel_messages_for_timeframe')
    def test_get_channel_messages_for_day(self, mock_get_timeframe):
        """Test that get_channel_messages_for_day calls the helper function with correct parameters"""
        # Setup
        channel_id = "123456789"
        date = datetime(2023, 5, 15)
        expected_start = datetime(2023, 5, 15, 0, 0, 0)
        expected_end = datetime(2023, 5, 15, 23, 59, 59, 999999)
        expected_desc = "2023-05-15"

        # Call the function
        database.get_channel_messages_for_day(channel_id, date)

        # Assert
        mock_get_timeframe.assert_called_once()
        args, _ = mock_get_timeframe.call_args
        self.assertEqual(args[0], channel_id)
        self.assertEqual(args[1], expected_start)
        self.assertEqual(args[2], expected_end)
        self.assertEqual(args[3], expected_desc)

    @patch('database.get_channel_messages_for_timeframe')
    def test_get_channel_messages_for_week(self, mock_get_timeframe):
        """Test that get_channel_messages_for_week calls the helper function with correct parameters"""
        # Setup
        channel_id = "123456789"
        start_date = datetime(2023, 5, 15)  # A Monday
        expected_end = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
        expected_desc = "the week starting 2023-05-15"

        # Call the function
        database.get_channel_messages_for_week(channel_id, start_date)

        # Assert
        mock_get_timeframe.assert_called_once()
        args, _ = mock_get_timeframe.call_args
        self.assertEqual(args[0], channel_id)
        self.assertEqual(args[1], start_date)
        self.assertEqual(args[2], expected_end)
        self.assertEqual(args[3], expected_desc)

if __name__ == "__main__":
    unittest.main()
