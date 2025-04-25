# UV Quickstart Instructions

[UV](https://github.com/astral-sh/uv) is a fast Python package manager and workflow tool. Below are common commands to set up and run this project using UV.

## 1. Create a Virtual Environment

```sh
uv venv
```

## 2. Install Dependencies

```sh
uv pip install -r requirements.txt
```

## 3. Run the Application

```sh
uv run main.py
```

## 4. Configuration

You can configure the server by setting environment variables. Create a `.env` file in the project root or set variables in your shell.

- **Change the web server port (default: 5173):**
  ```
  PORT="8080"
  ```
- **Change the host (default: 0.0.0.0):**
  ```
  HOST="127.0.0.1"
  ```
- **Set your Discord bot token (required):**
  ```
  DISCORD_TOKEN="your_token_here"
  ```

Example `.env` file:
```
DISCORD_TOKEN="your_token_here"
PORT="8080"
HOST="127.0.0.1"
```

## 5. Additional Useful Commands

- **Install a new package:**
  ```sh
  uv pip install <package-name>
  ```
- **Upgrade all packages:**
  ```sh
  uv pip install -r requirements.txt --upgrade
  ```
- **List installed packages:**
  ```sh
  uv pip list
  ```
- **Remove a package:**
  ```sh
  uv pip uninstall <package-name>
  ```

For more information, see the [UV documentation](https://github.com/astral-sh/uv).
