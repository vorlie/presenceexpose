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


# API JSON Response Schema

```json
{
  "success": true,
  "data": {
    "discord_user": {
      "id": "614807913302851594",
      "username": "vorlie",
      "discriminator": "0",
      "avatar": "https://cdn.discordapp.com/avatars/614807913302851594/0e7526c08860d0e6feaee8ad5536b341.png?size=1024",
      "bot": false,
      "public_flags": 4194560
    },
    "discord_status": "dnd",
    "activities": [
      {
        "type": 2,
        "name": "Spotify",
        "details": "One More",
        "state": "S3RL; Atef; hannah fortune; lowstattic",
        "assets": {
          "large_image": "https://i.scdn.co/image/ab67616d0000b2732b63524be39c33bb21569fbc",
          "large_text": "One More"
        },
        "album": "One More",
        "party": {
          "id": "spotify:614807913302851594"
        },
        "sync_id": "6WtHZDm7tHiFOw5Dfe26Pf",
        "timestamps": {
          "start": 1745598875497,
          "end": 1745599063382
        }
      },
      {
        "type": 0,
        "name": "Visual Studio Code",
        "timestamps": {
          "start": 1745597359356
        },
        "details": "🌟main.py • 727 lines",
        "assets": {
          "large_image": "https://media.discordapp.net/external/TDhIad0P3hmZt6e76lQ9-k1JX57-M_p8F7x_zqP6ar4/https/raw.githubusercontent.com/LeonardSSH/vscord/main/assets/icons/python.png",
          "large_text": "Editing a PYTHON file",
          "small_image": "https://media.discordapp.net/external/Joitre7BBxO-F2IaS7R300AaAcixAvPu3WD1YchRgdc/https/raw.githubusercontent.com/LeonardSSH/vscord/main/assets/icons/vscode.png",
          "small_text": "Visual Studio Code"
        },
        "flags": 1
      },
      {
        "type": 0,
        "name": "Counter-Strike 2",
        "timestamps": {
          "start": 1745596587805
        },
        "flags": 0
      }
    ],
    "client_status": {
      "desktop": true,
      "mobile": false,
      "web": false
    },
    "active_on_discord_mobile": false,
    "active_on_discord_desktop": true,
    "active_on_discord_web": false,
    "spotify": {
      "type": 2,
      "name": "Spotify",
      "details": "One More",
      "state": "S3RL; Atef; hannah fortune; lowstattic",
      "assets": {
        "large_image": "https://i.scdn.co/image/ab67616d0000b2732b63524be39c33bb21569fbc",
        "large_text": "One More"
      },
      "album": "One More",
      "party": {
        "id": "spotify:614807913302851594"
      },
      "sync_id": "6WtHZDm7tHiFOw5Dfe26Pf",
      "timestamps": {
        "start": 1745598875497,
        "end": 1745599063382
      }
    }
  }
}
```