import discord
import fastapi
from fastapi.staticfiles import StaticFiles
import uvicorn
import asyncio
import os
import json
import logging
import websockets  # For exceptions
from dotenv import load_dotenv
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from typing import Dict, Any, Optional, Set

load_dotenv()  # Load environment variables from .env file

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuration ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
HOST = os.getenv("HOST", "0.0.0.0")  # Listen on all network interfaces by default
PORT = int(os.getenv("PORT", "5173"))  # Port for the web server
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables or .env file")

# --- Discord Bot Setup ---
intents = discord.Intents.default()
intents.presences = True  # Enable Presence Intent
intents.members = True  # Enable Server Members Intent

client = discord.Client(intents=intents)

# --- Shared State ---
# Dictionary mapping WebSocket connection to a set of subscribed user IDs
websocket_subscriptions: Dict[WebSocket, Set[int]] = {}
# Dictionary to store user presence data {user_id: presence_dict}
user_presences: Dict[int, Dict[str, Any]] = {}
# Lock for concurrent access to shared state
state_lock = asyncio.Lock()

# --- FastAPI Setup ---
app = fastapi.FastAPI()

# --- Helper Functions ---


def format_activity(activity: discord.Activity) -> Optional[Dict[str, Any]]:
    """Formats a Discord activity object into a serializable dictionary."""
    if not activity:
        return None

    # Basic info common to most activities
    activity_dict = {
        "type": activity.type.value,  # Integer type code
        "name": activity.name,
    }
    timestamps = {}  # Initialize timestamp dict

    # --- Safely Process Timestamps ---
    # Check if start/end attributes EXIST before accessing
    if hasattr(activity, "start") and activity.start:
        timestamps["start"] = int(activity.start.timestamp() * 1000)  # Milliseconds
    if hasattr(activity, "end") and activity.end:
        timestamps["end"] = int(activity.end.timestamp() * 1000)  # Milliseconds

    # --- Add type-specific details ---
    if isinstance(activity, discord.Game):  # Type 0 - Playing
        # Timestamps handled above if they existed
        if hasattr(activity, "details") and activity.details:
            activity_dict["details"] = activity.details
        if hasattr(activity, "state") and activity.state:
            activity_dict["state"] = activity.state
    elif isinstance(activity, discord.Streaming):  # Type 1 - Streaming
        activity_dict.update(
            {
                "url": activity.url,
                "details": activity.details,
                "state": activity.state,
            }
        )
    elif isinstance(activity, discord.Spotify):  # Type 2 - Listening to Spotify
        # Spotify always has start/end, handled by hasattr check above
        assets = {}
        if activity.album_cover_url:
            assets["large_image"] = activity.album_cover_url
            assets["large_text"] = activity.album
        activity_dict.update(
            {
                "type": 2,  # Ensure type is Listening
                "details": activity.title,
                "state": "; ".join(activity.artists),
                "assets": assets,
                "album": activity.album,
                "party": {"id": activity.party_id} if activity.party_id else None,
                "sync_id": activity.track_id,  # Lanyard uses sync_id for track_id
            }
        )
        activity_dict["name"] = "Spotify"  # Lanyard standard
    elif (
        isinstance(activity, discord.Activity)
        and activity.type == discord.ActivityType.watching
    ):  # Type 3 - Watching
        # Generic activities might have start/end, handled above
        if hasattr(activity, "details") and activity.details:
            activity_dict["details"] = activity.details
        if hasattr(activity, "state") and activity.state:
            activity_dict["state"] = activity.state
    elif isinstance(activity, discord.CustomActivity):  # Type 4 - Custom Status
        # Custom activities DO NOT have start/end
        activity_dict.update(
            {
                "state": activity.state,
                "emoji": {
                    "name": activity.emoji.name,
                    "id": str(activity.emoji.id) if activity.emoji.id else None,
                    "animated": activity.emoji.animated,
                }
                if activity.emoji
                else None,
            }
        )
        timestamps = {}  # Ensure timestamps are empty for custom status
    elif (
        isinstance(activity, discord.Activity)
        and activity.type == discord.ActivityType.competing
    ):  # Type 5 - Competing
        # Competing might have start/end?
        if hasattr(activity, "details") and activity.details:
            activity_dict["details"] = activity.details
        if hasattr(activity, "state") and activity.state:
            activity_dict["state"] = activity.state

    # --- Add common optional fields AFTER type-specific processing ---
    if timestamps:  # Add timestamps dict if it has entries
        activity_dict["timestamps"] = timestamps

    # Add generic details/state if present and not already handled by specific type
    # (Check again to catch types not explicitly listed, e.g. generic Activity)
    if (
        hasattr(activity, "details")
        and activity.details
        and "details" not in activity_dict
    ):
        activity_dict["details"] = activity.details
    if hasattr(activity, "state") and activity.state and "state" not in activity_dict:
        # Check if state is already set (e.g. by CustomActivity) to avoid overwriting
        pass  # activity_dict["state"] = activity.state

    # Assets (common for games/rich presence) - Check existence before adding
    assets_dict = {}
    if hasattr(activity, "large_image_url") and activity.large_image_url:
        assets_dict["large_image"] = (
            activity.large_image_url
        )  # Using URL for simplicity
        if hasattr(activity, "large_image_text") and activity.large_image_text:
            assets_dict["large_text"] = activity.large_image_text
    if hasattr(activity, "small_image_url") and activity.small_image_url:
        assets_dict["small_image"] = activity.small_image_url
        if hasattr(activity, "small_image_text") and activity.small_image_text:
            assets_dict["small_text"] = activity.small_image_text
    if assets_dict:  # Only add 'assets' key if we found any
        activity_dict["assets"] = assets_dict

    # Party info
    if (
        hasattr(activity, "party")
        and activity.party
        and isinstance(activity.party, dict)
    ):
        party_data = {}
        if "id" in activity.party:
            party_data["id"] = activity.party["id"]
        if "size" in activity.party:
            party_data["size"] = activity.party["size"]
        if party_data:
            activity_dict["party"] = party_data

    if (
        hasattr(activity, "flags") and activity.flags is not None
    ):  # Check flags exist and aren't None
        # Check if flags is the Enum object or already an int
        if isinstance(activity.flags, int):
            activity_dict["flags"] = activity.flags  # Use the int directly
        elif hasattr(
            activity.flags, "value"
        ):  # Check if it has a .value attribute (like an Enum)
            activity_dict["flags"] = activity.flags.value  # Get the integer value
        else:
            # Log unexpected type if necessary
            logger.warning(
                f"Unexpected type for activity.flags: {type(activity.flags)}, value: {activity.flags}"
            )
    return activity_dict


def format_presence(
    member: Optional[discord.Member], fallback_user: Optional[discord.User] = None
) -> Dict[str, Any]:
    """Formats a Discord Member object's presence into a Lanyard-like dictionary."""

    user_obj = (
        member if member else fallback_user
    )  # Prioritize member object for user info if available

    # Construct offline state if member is None or status is offline
    # Use the member's status directly
    if not member or member.status == discord.Status.offline:
        # Ensure we use the user_obj determined above for details
        return {
            "discord_user": {
                "id": str(user_obj.id) if user_obj else "unknown",
                "username": user_obj.name if user_obj else "unknown",
                "discriminator": user_obj.discriminator if user_obj else "0000",
                "avatar": user_obj.avatar.url if user_obj and user_obj.avatar else None,
                "bot": user_obj.bot if user_obj else False,
                "public_flags": user_obj.public_flags.value if user_obj else 0,
            },
            "discord_status": "offline",
            "activities": [],
            "client_status": {},
            "active_on_discord_mobile": False,
            "active_on_discord_desktop": False,
            "active_on_discord_web": False,
            "spotify": None,
        }

    # Format online presence using the Member object directly
    # user_obj is guaranteed to be the 'member' here since member is not None
    formatted = {
        "discord_user": {
            "id": str(member.id),
            "username": member.name,
            "discriminator": member.discriminator,
            "avatar": member.avatar.url if member.avatar else None,
            "bot": member.bot,
            "public_flags": member.public_flags.value,
        },
        "discord_status": str(member.status),  # Access status directly
        "activities": [
            act_data for act in member.activities if (act_data := format_activity(act))
        ],  # Access activities directly
        "client_status": {  # Access client statuses directly
            "desktop": str(member.desktop_status) != "offline",
            "mobile": str(member.mobile_status) != "offline",
            "web": str(member.web_status) != "offline",
        },
        "active_on_discord_mobile": str(member.mobile_status) != "offline",
        "active_on_discord_desktop": str(member.desktop_status) != "offline",
        "active_on_discord_web": str(member.web_status) != "offline",
    }

    # Extract Spotify info if present and format it specifically for the 'spotify' key
    # Access activities directly from the member
    spotify_activity = next(
        (act for act in member.activities if isinstance(act, discord.Spotify)), None
    )
    formatted["spotify"] = (
        format_activity(spotify_activity) if spotify_activity else None
    )

    return formatted


async def notify_subscribed_clients(user_id: int, presence_data: Dict[str, Any]):
    """Sends presence update to clients subscribed to this user_id."""
    if not presence_data:
        logger.warning(f"Attempted to notify with invalid presence data for {user_id}")
        return

    message_payload = {
        "op": OP_EVENT,  # Event OP Code
        "t": "PRESENCE_UPDATE",  # Event Type
        "d": presence_data,  # Event Data
    }
    message_str = json.dumps(message_payload)
    logger.debug(f"Broadcasting presence update for user {user_id}")

    disconnected_clients = []
    # Iterate safely over a copy of items
    # Lock needed here if another task could modify the dict during iteration
    async with state_lock:
        subscriptions_copy = list(websocket_subscriptions.items())

    for websocket, subscribed_ids in subscriptions_copy:
        if user_id in subscribed_ids:
            try:
                await websocket.send_text(message_str)
                # logger.debug(f"Sent presence update for {user_id} to {websocket.client}")
            except (
                WebSocketDisconnect,
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError,
            ):
                logger.info(
                    f"Client {websocket.client} disconnected during broadcast for user {user_id}."
                )
                disconnected_clients.append(websocket)
            except Exception as e:
                logger.error(
                    f"Error sending message to WebSocket {websocket.client} for user {user_id}: {e}"
                )
                disconnected_clients.append(
                    websocket
                )  # Assume dead on other errors too

    # Clean up disconnected clients
    if disconnected_clients:
        async with state_lock:
            for client_ws in disconnected_clients:
                if client_ws in websocket_subscriptions:
                    del websocket_subscriptions[client_ws]
                    logger.info(
                        f"Removed disconnected client {client_ws.client} from subscriptions. Count: {len(websocket_subscriptions)}"
                    )


async def update_presence_state(user_id: int, presence_data: Dict[str, Any]):
    """Updates the shared presence dictionary and notifies relevant websockets."""
    async with state_lock:
        if not presence_data:
            logger.warning(
                f"Received invalid presence data for {user_id}, not updating state."
            )
            return

        user_presences[user_id] = presence_data
        logger.debug(f"Updated presence cache for user {user_id}")

    # Notify outside the lock to avoid holding it during network I/O
    asyncio.create_task(notify_subscribed_clients(user_id, presence_data))


# --- Discord Event Handlers ---
@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user.name} ({client.user.id})")
    logger.info("Bot is ready and listening for presence updates.")


@client.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    """Called when a member's presence changes."""
    if after.bot:  # Ignore bots
        return

    logger.debug(
        f"Presence update for: {after.name} ({after.id}) Status: {after.status}"
    )
    try:
        # Pass both presence and user for robust formatting
        presence_data = format_presence(after)
        # Update state and notify websockets
        await update_presence_state(after.id, presence_data)
    except Exception as e:
        logger.error(
            f"Error processing presence update for {after.id}: {e}", exc_info=True
        )


# --- FastAPI Endpoints ---

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root_html():
    logger.info("Serving index.html")
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

@app.get("/api/v1/users/{user_id_str}")
async def get_user_presence(user_id_str: str):
    """REST endpoint to get the latest presence data for a user."""
    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="User ID must be an integer.")

    async with state_lock:
        presence_data_cached = user_presences.get(user_id)

    if presence_data_cached:
        return JSONResponse(content={"success": True, "data": presence_data_cached})
    else:
        # User presence not cached, try to find user/member and return offline state
        member_obj: Optional[discord.Member] = None
        user_obj: Optional[discord.User] = client.get_user(user_id)

        # Try finding Member object across guilds
        for guild in client.guilds:
            member_candidate = guild.get_member(user_id)
            if member_candidate:
                member_obj = member_candidate  # Found a member object
                break  # Found one, no need to check other guilds

        # Prioritize member_obj if found, otherwise use user_obj if found
        user_for_offline = member_obj if member_obj else user_obj

        if user_for_offline:  # If we found any representation of the user
            logger.debug(
                f"User {user_id} not in presence cache, returning offline state using {type(user_for_offline).__name__} object."
            )
            # Call format_presence with the member object (if found, else None)
            # and the user object as the fallback (if member wasn't found but user was)
            offline_data = format_presence(member_obj, user_obj)
            return JSONResponse(content={"success": True, "data": offline_data})
        else:
            logger.warning(f"User {user_id} not found by bot for REST request.")
            raise HTTPException(
                status_code=404, detail="User not found or bot cannot access user."
            )


# Define OP Codes for WebSocket communication
OP_EVENT = 0  # Server->Client: Presence Update, Initial State
OP_HELLO = 1  # Server->Client: On connect, includes heartbeat interval
OP_INITIALIZE = 2  # Client->Server: Subscribe to user IDs
OP_HEARTBEAT = 3  # Client->Server: Heartbeat acknowledgement/keepalive

HEARTBEAT_INTERVAL_S = 30
CLIENT_TIMEOUT_S = HEARTBEAT_INTERVAL_S + 15


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time presence updates with subscriptions."""
    ws_client_host = (
        f"{websocket.client.host}:{websocket.client.port}"
        if websocket.client
        else "Unknown"
    )
    connection_active = False
    try:
        await websocket.accept()
        connection_active = True
        logger.info(f"WebSocket client connected: {ws_client_host}")

        # Send HELLO message with heartbeat interval
        try:
            await websocket.send_json(
                {
                    "op": OP_HELLO,
                    "d": {"heartbeat_interval": HEARTBEAT_INTERVAL_S * 1000},
                }
            )
        except (WebSocketDisconnect, websockets.exceptions.ConnectionClosed):
            logger.info(
                f"Client {ws_client_host} disconnected immediately after connect during HELLO."
            )
            return  # Exit early

        # Add to subscriptions with an empty set
        async with state_lock:
            websocket_subscriptions[websocket] = set()

        while True:
            try:
                # Wait for a message from the client with a timeout
                raw_data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=CLIENT_TIMEOUT_S
                )
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received invalid JSON from {ws_client_host}. Ignoring."
                    )
                    continue  # Wait for next message

                logger.debug(f"Received message from {ws_client_host}: {data}")

                op = data.get("op")
                payload = data.get("d")

                if op == OP_INITIALIZE:
                    if not isinstance(payload, dict):
                        logger.warning(
                            f"Invalid payload 'd' for OP {op} from {ws_client_host}"
                        )
                        continue

                    subscribe_ids_str = payload.get("subscribe_to_ids")
                    if not isinstance(subscribe_ids_str, list):
                        logger.warning(
                            f"Invalid 'subscribe_to_ids' format from {ws_client_host}: {subscribe_ids_str}"
                        )
                        continue

                    newly_subscribed_ids = set()
                    current_subs = websocket_subscriptions.get(websocket, set())
                    valid_ids_to_subscribe = set()

                    # Process Subscriptions
                    for user_id_str in subscribe_ids_str:
                        try:
                            user_id_int = int(user_id_str)
                            valid_ids_to_subscribe.add(user_id_int)
                            if user_id_int not in current_subs:
                                newly_subscribed_ids.add(user_id_int)
                        except ValueError:
                            logger.warning(
                                f"Invalid user ID format received from {ws_client_host}: {user_id_str}"
                            )

                    # Update the subscription set for this websocket
                    async with state_lock:
                        websocket_subscriptions[websocket] = valid_ids_to_subscribe
                    logger.info(
                        f"Client {ws_client_host} updated subscriptions to IDs: {valid_ids_to_subscribe}"
                    )

                    # Send initial state for newly subscribed IDs
                    if newly_subscribed_ids:
                        logger.info(
                            f"Sending initial presence for {newly_subscribed_ids} to {ws_client_host}"
                        )
                        initial_states_to_send = []
                        async with (
                            state_lock
                        ):  # Need lock to safely read user_presences
                            for sub_id in newly_subscribed_ids:
                                cached_presence_dict = user_presences.get(sub_id)
                                state_to_send = None

                                if cached_presence_dict:
                                    # Use the cached presence dictionary directly
                                    state_to_send = cached_presence_dict
                                    logger.debug(
                                        f"Using cached presence for {sub_id} for INIT_STATE"
                                    )
                                else:
                                    # Not cached, generate offline state by finding user/member
                                    logger.debug(
                                        f"Generating offline state for {sub_id} for INIT_STATE"
                                    )
                                    member_obj: Optional[discord.Member] = None
                                    user_obj: Optional[discord.User] = client.get_user(
                                        sub_id
                                    )

                                    # Try finding Member object across guilds if necessary
                                    if not user_obj or not isinstance(
                                        user_obj, discord.Member
                                    ):
                                        for guild in client.guilds:
                                            member_candidate = guild.get_member(sub_id)
                                            if member_candidate:
                                                member_obj = (
                                                    member_candidate  # Found member
                                                )
                                                user_obj = member_obj  # Use member as the primary user obj for fallback
                                                break
                                    elif isinstance(user_obj, discord.Member):
                                        # User found via get_user was already a Member object
                                        member_obj = user_obj

                                    # Call format_presence ONLY to generate offline state
                                    # Pass member_obj (which might be None) and user_obj (best available user info)
                                    state_to_send = format_presence(
                                        member_obj, user_obj
                                    )
                                initial_states_to_send.append(
                                    {
                                        "op": OP_EVENT,
                                        "t": "INIT_STATE",
                                        "d": state_to_send,  # Use the dictionary determined above
                                    }
                                )

                        # Send all initial states found
                        for state_msg in initial_states_to_send:
                            try:
                                await websocket.send_json(state_msg)
                            except Exception as e:
                                logger.error(
                                    f"Failed to send initial state to {ws_client_host} for user {state_msg['d']['discord_user']['id']}: {e}"
                                )
                                # If sending fails, the connection might be dead, break loop?
                                raise websockets.exceptions.ConnectionClosed(
                                    1011, "Failed to send initial state"
                                )  # Trigger cleanup

                elif op == OP_HEARTBEAT:
                    # Client acknowledged heartbeat or is sending keepalive
                    # Receiving any message within the timeout resets it implicitly
                    logger.debug(f"Received heartbeat from {ws_client_host}")

                    try:
                        await websocket.send_json({"op": 11})
                    except Exception:
                        logger.warning(f"Failed to send Heartbeat ACK to {ws_client_host}")

                else:
                    logger.warning(
                        f"Received unknown OP code {op} from {ws_client_host}"
                    )
                    try:
                        await websocket.send_json({"op": -1, "d": f"Unknown OP Code: {op}"})
                    except Exception: 
                        pass

            except asyncio.TimeoutError:
                logger.info(
                    f"Client {ws_client_host} timed out (no message received in {CLIENT_TIMEOUT_S}s). Closing connection."
                )
                break
            except (
                WebSocketDisconnect,
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError,
            ) as e:
                code = e.code if hasattr(e, "code") else "N/A"
                reason = e.reason if hasattr(e, "reason") else "N/A"
                logger.info(
                    f"WebSocket client {ws_client_host} disconnected. Code: {code}, Reason: {reason}"
                )
                break  # Exit the loop
            except Exception as e:
                logger.error(
                    f"Unexpected WebSocket error for {ws_client_host}: {e}",
                    exc_info=True,
                )
                # Break loop on unexpected errors to ensure cleanup
                break

    except Exception as e:
        # Catch errors during the initial accept or HELLO phase
        logger.error(
            f"Error during WebSocket setup or outer loop for {ws_client_host}: {e}",
            exc_info=True,
        )
    finally:
        # Ensure removal from subscriptions on disconnect/error/timeout
        async with state_lock:
            if websocket in websocket_subscriptions:
                del websocket_subscriptions[websocket]
        # Ensure websocket is closed if the loop was exited due to error rather than clean disconnect
        if (
            connection_active
            and websocket.client_state != websockets.protocol.State.CLOSED
        ):
            try:
                await websocket.close(
                    code=1011
                )  # Internal Server Error / appropriate code
            except Exception:
                pass  # Ignore errors during close, already handling exit
        logger.info(
            f"WebSocket connection closed for {ws_client_host}. Active connections: {len(websocket_subscriptions)}"
        )


# --- Main Execution Logic ---


async def run_bot():
    """Starts the Discord bot."""
    try:
        await client.start(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Error starting Discord bot: {e}", exc_info=True)
    finally:
        if client and not client.is_closed():
            await client.close()
            logger.info("Discord client closed.")


async def run_server():
    """Starts the FastAPI server."""
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Web server task cancelled.")
    except Exception as e:
        logger.error(f"Error running web server: {e}", exc_info=True)
    finally:
        logger.info("Web server stopped.")  # Uvicorn handles its shutdown


async def main():
    """Runs the bot and server concurrently."""
    logger.info("Starting services...")
    # Ensure client object exists before creating task
    if not isinstance(client, discord.Client):
        logger.critical("Discord client not initialized correctly.")
        return

    bot_task = asyncio.create_task(run_bot(), name="DiscordBotTask")
    server_task = asyncio.create_task(run_server(), name="WebServerTask")

    done, pending = await asyncio.wait(
        [bot_task, server_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        logger.info(
            f"Service task completed or failed, cancelling pending task: {task.get_name()}"
        )
        task.cancel()
        try:
            await task  # Wait for cancellation to complete
        except asyncio.CancelledError:
            logger.info(f"Task {task.get_name()} cancelled successfully.")
        except Exception as e:
            logger.error(
                f"Error during cancellation of task {task.get_name()}: {e}",
                exc_info=True,
            )

    # Check results of completed tasks
    for task in done:
        try:
            task.result()  # Raise exception if task failed
            logger.info(f"Task {task.get_name()} completed successfully.")
        except Exception as e:
            logger.error(f"Task {task.get_name()} failed: {e}", exc_info=True)

    logger.info("All services are shutting down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        logger.info("Application shutdown complete.")
