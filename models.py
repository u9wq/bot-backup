from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json


@dataclass
class PermissionOverwriteData:
    """Permission overwrite d'un salon/catégorie, référencée par NOM de rôle
    (les IDs ne veulent rien dire une fois transférés sur un autre serveur)."""
    target_type: str  # 'role' ou 'everyone'
    target_name: str
    allow: int
    deny: int


@dataclass
class RoleData:
    """Structure de données pour un rôle"""
    name: str
    color: int
    permissions: int
    position: int
    hoist: bool
    mentionable: bool


@dataclass
class ChannelData:
    """Structure de données pour un salon (texte, vocal, stage, forum) AVEC permissions.
    Les salons sont stockés à plat dans ServerBackup.channels et rattachés à
    leur catégorie via `category_name`."""
    name: str
    type: str  # 'text', 'voice', 'stage', 'forum'
    position: int
    category_name: Optional[str] = None
    topic: Optional[str] = None
    bitrate: Optional[int] = None
    user_limit: Optional[int] = None
    slowmode_delay: Optional[int] = None
    nsfw: bool = False
    permission_overwrites: List[PermissionOverwriteData] = field(default_factory=list)


@dataclass
class CategoryData:
    """Structure de données pour une catégorie AVEC permissions."""
    name: str
    position: int
    permission_overwrites: List[PermissionOverwriteData] = field(default_factory=list)


@dataclass
class EmojiData:
    """Structure pour les emojis personnalisés"""
    name: str
    image_data: str  # Base64 encoded
    is_animated: bool


@dataclass
class WebhookData:
    """Structure pour les webhooks"""
    name: str
    channel_name: str  # Nom du salon parent (pour recréation)
    avatar_data: Optional[str] = None


@dataclass
class ServerBackup:
    """Structure COMPLÈTE de sauvegarde d'un serveur."""
    server_name: str
    server_id: int
    backup_date: str
    roles: List[RoleData] = field(default_factory=list)
    categories: List[CategoryData] = field(default_factory=list)
    channels: List[ChannelData] = field(default_factory=list)
    emojis: List[EmojiData] = field(default_factory=list)
    webhooks: List[WebhookData] = field(default_factory=list)

    def to_json(self, backup_id: str) -> str:
        """Convertit la sauvegarde en JSON"""
        data = asdict(self)
        data['backup_id'] = backup_id
        return json.dumps(data, indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "ServerBackup":
        """Reconstruit une sauvegarde depuis JSON"""
        data = json.loads(json_str)
        data.pop('backup_id', None)

        def build_overwrites(raw_list):
            return [PermissionOverwriteData(**ow) for ow in raw_list or []]

        roles = [RoleData(**r) for r in data.get('roles', [])]

        categories = []
        for cat in data.get('categories', []):
            categories.append(CategoryData(
                name=cat['name'],
                position=cat['position'],
                permission_overwrites=build_overwrites(cat.get('permission_overwrites')),
            ))

        channels = []
        for ch in data.get('channels', []):
            channels.append(ChannelData(
                name=ch['name'],
                type=ch['type'],
                position=ch['position'],
                category_name=ch.get('category_name'),
                topic=ch.get('topic'),
                bitrate=ch.get('bitrate'),
                user_limit=ch.get('user_limit'),
                slowmode_delay=ch.get('slowmode_delay'),
                nsfw=ch.get('nsfw', False),
                permission_overwrites=build_overwrites(ch.get('permission_overwrites')),
            ))

        emojis = [EmojiData(**e) for e in data.get('emojis', [])]
        webhooks = [WebhookData(**w) for w in data.get('webhooks', [])]

        return cls(
            server_name=data['server_name'],
            server_id=data['server_id'],
            backup_date=data['backup_date'],
            roles=roles,
            categories=categories,
            channels=channels,
            emojis=emojis,
            webhooks=webhooks,
        )
