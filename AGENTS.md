# AGENTS.md

## Build/Lint/Test Commands
- Install dependencies: `pip install -r requirements.txt`
- Run all tests: `python -m pytest`
- Run single test: `python -m pytest test_file.py::test_name`
- Run tests with coverage: `python -m pytest --cov=.`
- Lint code: `pylint *.py`
- Format code: `black *.py`

## Code Style Guidelines
- Python 3.9+ required (asyncio.to_thread)
- Use type hints for function parameters and return values
- Follow PEP 8 for naming conventions (snake_case for functions/variables, PascalCase for classes)
- Use descriptive variable names
- Import standard library modules first, then third-party, then local imports
- Use absolute imports when possible
- Error handling: Use try/except blocks with specific exception types
- Logging: Use the logger from logging_config.py
- Database operations: Use context managers for connections
- Async operations: Use asyncio.to_thread for blocking operations
- Message splitting: Use split_long_message for responses over 1900 chars
- Rate limiting: Use check_rate_limit before processing commands
- Configuration: Use environment variables with .env file override