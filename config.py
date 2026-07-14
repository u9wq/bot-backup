import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
BACKUP_FOLDER = 'backups'

# Permissions requises pour les opérations
REQUIRED_PERMISSIONS = {
    'administrator': True,
    'manage_channels': True,
    'manage_roles': True,
    'manage_webhooks': True
}