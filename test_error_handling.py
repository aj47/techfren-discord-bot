#!/usr/bin/env python3
"""
Test script for the standardized error handling implementation.
"""

import sys
import tempfile
import os
import sqlite3
import asyncio
from error_handler import (
    handle_database_error, 
    handle_async_database_error,
    log_error_with_context,
    ErrorSeverity,
    safe_execute,
    safe_execute_async
)

def test_database_error_decorator():
    """Test the database error decorator."""
    print("Testing database error decorator...")
    
    @handle_database_error
    def failing_database_function():
        raise sqlite3.OperationalError("Test database error")
    
    @handle_database_error
    def successful_database_function():
        return True
    
    # Test successful execution
    result = successful_database_function()
    assert result == True, "Successful function should return True"
    
    # Test error handling
    result = failing_database_function()
    assert result == False, "Failing function should return False due to decorator"
    
    print("✓ Database error decorator working correctly")

async def test_async_database_error_decorator():
    """Test the async database error decorator."""
    print("Testing async database error decorator...")
    
    @handle_async_database_error
    async def failing_async_database_function():
        raise sqlite3.DatabaseError("Test async database error")
    
    @handle_async_database_error
    async def successful_async_database_function():
        return True
    
    # Test successful execution
    result = await successful_async_database_function()
    assert result == True, "Successful async function should return True"
    
    # Test error handling
    result = await failing_async_database_function()
    assert result == False, "Failing async function should return False due to decorator"
    
    print("✓ Async database error decorator working correctly")

def test_safe_execute():
    """Test the safe_execute utility."""
    print("Testing safe_execute utility...")
    
    def successful_function(x, y):
        return x + y
    
    def failing_function():
        raise ValueError("Test error")
    
    # Test successful execution
    result = safe_execute(successful_function, 2, 3)
    assert result == 5, "Safe execute should return function result"
    
    # Test error handling with default return
    result = safe_execute(failing_function, default_return="error")
    assert result == "error", "Safe execute should return default on error"
    
    print("✓ Safe execute utility working correctly")

async def test_safe_execute_async():
    """Test the safe_execute_async utility."""
    print("Testing safe_execute_async utility...")
    
    async def successful_async_function(x, y):
        return x * y
    
    async def failing_async_function():
        raise ValueError("Test async error")
    
    # Test successful execution
    result = await safe_execute_async(successful_async_function, 3, 4)
    assert result == 12, "Safe execute async should return function result"
    
    # Test error handling with default return
    result = await safe_execute_async(failing_async_function, default_return="async_error")
    assert result == "async_error", "Safe execute async should return default on error"
    
    print("✓ Safe execute async utility working correctly")

def test_log_error_with_context():
    """Test the error logging utility."""
    print("Testing log_error_with_context...")
    
    # This function mainly tests that logging doesn't crash
    try:
        test_error = ValueError("Test error for logging")
        log_error_with_context(
            test_error, 
            "Test context",
            ErrorSeverity.MEDIUM,
            {"test_info": "additional context"}
        )
        print("✓ Error logging working correctly")
    except Exception as e:
        print(f"✗ Error logging failed: {e}")
        raise

async def main():
    """Run all tests."""
    print("Starting error handling tests...\n")
    
    test_database_error_decorator()
    await test_async_database_error_decorator()
    test_safe_execute()
    await test_safe_execute_async()
    test_log_error_with_context()
    
    print("\n✓ All error handling tests passed!")
    print("The standardized error handling implementation is working correctly.")

if __name__ == "__main__":
    asyncio.run(main())
