# BitlyReader CLI 🚀

A world-class, premium interactive command-line interface (CLI) tool designed for power users to manage, explore, shorten, and analyze links via the **Bitly API v4**.

Built using modern, professional Python development practices, BitlyReader features a stunning terminal dashboard powered by `rich`, robust error handling, full unit test coverage, and strict code style compliance with `ruff`.

---

## Key Features ✨

1. **Stunning Interactive Dashboard**: Navigate accounts, groups, links, and analytics using clean menus and interactive prompts.
2. **Double Execution Modes**:
   - **Interactive Menu**: Multi-level navigation to explore account details, select groups, list links, view analytics, and export data.
   - **Direct CLI Arguments**: Fully scriptable flags for automation, headless shortening, or export tasks.
3. **Advanced Link Actions**:
   - **URL Shortening**: Shorten long URLs with support for custom titles, domains, and targeted groups.
   - **Interactive Analytics**: View aggregated click engagement metrics with custom warnings for plan limitations.
   - **Multi-Format Exporting**: Bulk export link details to `JSON` or `CSV` formats. Exports are neatly saved in a custom folder structured as `{group_name}_{date}/` using each link's unique hash as the filename.
4. **World-Class Engineering**:
   - Strict `ruff` configuration (checking 12 rule sets).
   - High-speed unit tests with 100% mock isolation.
   - Professional docstrings, comments, type hinting, and complete environment configuration using `uv`.

---

## Project Structure 📁

- `client.py`: Robust, typed HTTP client for the Bitly API v4 with custom exception handling.
- `main.py`: Interactive CLI entry point with parser flags, dashboard menus, and export helpers.
- `test_client.py`: Automated mock-based test suite.
- `pyproject.toml`: Modern Python metadata and strict linter/formatter configurations.
- `.env.example`: Configuration template for API tokens.
- `.gitignore`: Comprehensive ignore file to guarantee secret protection.

---

## Installation & Setup ⚙️

This project uses `uv` as its environment and package manager.

### Prerequisites
Make sure `uv` is installed on your machine. If you do not have it, install it via:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. Initialize the Environment
Clone the repository (or navigate to the project directory) and sync dependencies:
```bash
cd ~/Development/BitlyReader
uv sync
```

### 2. Configure the API Token
To communicate with Bitly, you need a **Generic Access Token**.
1. Log in to your Bitly account.
2. Go to **Settings** -> **API** (or visit [https://app.bitly.com/settings/api/](https://app.bitly.com/settings/api/)).
3. Enter your account password and click **Generate Token**.
4. Create a `.env` file in the project root:
   ```bash
   cp .env.example .env
   ```
5. Open `.env` and fill in your token:
   ```env
   BITLY_ACCESS_TOKEN=your_generated_access_token_here
   ```

---

## Usage Guide 🛠️

BitlyReader supports direct shebang execution on Linux/macOS, automatically invoking `uv run`.

### Interactive Menu Mode
Simply run the script with no arguments to launch the gorgeous interactive console dashboard:
```bash
./main.py
```

### Direct CLI Mode (Headless Automation)

* **List Bitlinks**:
  ```bash
  ./main.py --list
  ```

* **Shorten a Long URL**:
  ```bash
  ./main.py --shorten "https://github.com/google/deepmind"
  ```

* **Shorten a URL with a Custom Title**:
  ```bash
  ./main.py --shorten "https://github.com/google/deepmind" --title "Google DeepMind GitHub"
  ```

* **Check Link Analytics**:
  ```bash
  ./main.py --analytics "bit.ly/4omVThv"
  ```

* **Bulk Export Links (JSON)**:
  ```bash
  ./main.py --export json
  ```

* **Bulk Export Links (CSV)**:
  ```bash
  ./main.py --export csv
  ```

* **Specify a Target Group**:
  Pass the `--group-guid <guid>` flag to target a specific group instead of your default:
  ```bash
  ./main.py --list --group-guid Bq62eTU8gsX
  ```

---

## Verification & Testing 🧪

### Run Unit Tests
Execute the mock unit tests with direct script running:
```bash
./test_client.py
```
Or via standard unittest module:
```bash
uv run python -m unittest test_client.py -v
```

### Code Quality Check (Ruff)
Run formatting and linting checks to guarantee world-class quality standards:
```bash
uv run ruff check .
uv run ruff format --check .
```

To automatically resolve formatting or safe lint violations:
```bash
uv run ruff check --fix .
uv run ruff format .
```
