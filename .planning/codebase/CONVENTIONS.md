# Coding Conventions

## Import Style
- Standard library imports first, then third-party, then local
- `from` imports preferred over bare module imports
- `Optional` type hint from `typing`

## Naming
- `snake_case` for functions and variables
- `PascalCase` for classes (dataclasses)
- `SCREAMING_SNAKE_CASE` for constants
- Private functions prefixed with `_`

## Type Hints
- Used consistently on function parameters and return types
- `Optional[str]` for nullable fields
- `list[dict]` style (Python 3.9+)
- Dataclass fields use type annotations

## Docstring Style
- Google/docstring style not enforced — most functions have a brief `"""Purpose"""` block
- Args documented with `Args:` section where non-trivial
- Returns documented with `Returns:` section

## Error Handling Patterns
- Try/except with specific exception types (not bare `except:`)
- Fallback chains (LLM → hardcoded → empty)
- Silent degradation preferred over crashing
- Errors logged with `logger.warning()` or `logger.error()`
- Browser cleanup in `finally` block (`driver.quit()`)

## Logging
- Module-level logger via `logging.getLogger(__name__)`
- Pipeline progress printed to stdout via `print()`
- Debug info via `logger.info()`, `logger.warning()`, `logger.error()`

## Configuration Pattern
- `.env` file loaded by `python-dotenv` in `config/settings.py`
- `get_settings()` returns a dict
- Constants defined at module top (e.g., `DEFAULT_MAX_PAGES = 5`)
- Environment-specific overrides via `os.getenv()`

## Function Signature Conventions
- Required positional params first
- Optional params with defaults
- `output_dir: Optional[str] = None` resolved inside function
- `model: str = DEFAULT_MODEL` for LLM model selection

## File Organization
- One primary class or function per module
- Helper/private functions at bottom of file
- Constants at top after imports
- CLI entry point in `if __name__ == "__main__":` at bottom

## Commit Conventions
- Descriptive imperative subject line
- Code-oriented, not feature-oriented messages
- Co-authored-by trailer for Claude-generated code
