import discord
from discord.ext import commands
import json
import os
import asyncio
import base64
import aiohttp
from datetime import datetime
from typing import List, Optional, Set, Dict, Callable, Awaitable

from models import (
    RoleData, ChannelData, CategoryData, ServerBackup, EmojiData, WebhookData,
    PermissionOverwriteData,
)
from config import BACKUP_FOLDER

LogFn = Optional[Callable[[str], Awaitable[None]]]

ALL_COMPONENTS = {"roles", "channels", "permissions", "emojis", "webhooks"}


class BackupHandler:

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.backup_folder = BACKUP_FOLDER
        self._ensure_backup_folder()

    def _ensure_backup_folder(self):
        if not os.path.exists(self.backup_folder):
            os.makedirs(self.backup_folder)

    @staticmethod
    def get_backup_path(backup_id: str) -> str:
        return os.path.join(BACKUP_FOLDER, f"{backup_id}.json")

    def list_backups(self) -> List[str]:
        backups = []
        if not os.path.exists(BACKUP_FOLDER):
            return backups
        for file in os.listdir(BACKUP_FOLDER):
            if file.endswith('.json'):
                backups.append(file[:-5])
        return sorted(backups)

    def get_backup_summary(self, backup_id: str) -> Optional[dict]:
        """Lecture rapide des infos d'un backup pour l'affichage (sans tout reconstruire)."""
        path = self.get_backup_path(backup_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {
                "server_name": data.get("server_name", "?"),
                "backup_date": data.get("backup_date", "?"),
                "roles": len(data.get("roles", [])),
                "channels": len(data.get("channels", [])),
                "emojis": len(data.get("emojis", [])),
                "webhooks": len(data.get("webhooks", [])),
            }
        except Exception:
            return None

    def load_backup(self, backup_id: str) -> Optional[ServerBackup]:
        path = self.get_backup_path(backup_id)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return ServerBackup.from_json(f.read())

    def save_uploaded_backup(self, filename: str, content: bytes) -> str:
        """Enregistre un fichier JSON uploadé par l'utilisateur comme backup utilisable.
        Valide qu'il s'agit bien d'un ServerBackup avant de l'écrire sur disque."""
        text = content.decode('utf-8')
        backup = ServerBackup.from_json(text)  # lève une exception si invalide

        safe_name = "".join(c for c in filename if c.isalnum() or c in ('_', '-')) or "import"
        backup_id = f"import_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        filepath = self.get_backup_path(backup_id)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(backup.to_json(backup_id))
        return backup_id

    async def check_admin_permission(self, ctx: commands.Context) -> bool:
        permissions = ctx.guild.me.guild_permissions
        if not permissions.administrator:
            missing_perms = []
            if not permissions.manage_channels:
                missing_perms.append("Gérer les salons")
            if not permissions.manage_roles:
                missing_perms.append("Gérer les rôles")

            if missing_perms:
                await ctx.send(
                    f"❌ Le bot n'a pas les permissions nécessaires !\n"
                    f"Permissions manquantes : {', '.join(missing_perms)}"
                )
                return False
        return True

    # ------------------------------------------------------------------ #
    # NETTOYAGE
    # ------------------------------------------------------------------ #

    async def clear_server(self, guild: discord.Guild, log_callback: LogFn = None):
        """Supprime TOUS les salons, catégories et rôles"""

        async def log(msg):
            if log_callback:
                try:
                    await log_callback(msg)
                except Exception:
                    pass

        await log("🧹 **Début du nettoyage du serveur...**")

        deleted_count = 0
        failed_count = 0

        channels = list(guild.channels)
        await log(f"📊 {len(channels)} salons/catégories à supprimer...")

        for channel in channels:
            try:
                await channel.delete()
                deleted_count += 1
                await asyncio.sleep(0.3)
            except discord.Forbidden:
                await log(f"⚠️ Permission manquante pour supprimer {channel.name}")
                failed_count += 1
            except Exception as e:
                await log(f"⚠️ Impossible de supprimer {channel.name}: {str(e)[:50]}")
                failed_count += 1

        await asyncio.sleep(2)

        roles = list(guild.roles)
        await log(f"📊 {len(roles)} rôles à supprimer...")

        for role in roles:
            if role.name != "@everyone" and not role.managed:
                try:
                    await role.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.3)
                except discord.Forbidden:
                    await log(f"⚠️ Permission manquante pour supprimer {role.name}")
                    failed_count += 1
                except Exception as e:
                    await log(f"⚠️ Impossible de supprimer {role.name}: {str(e)[:50]}")
                    failed_count += 1

        await log(f"✅ **Nettoyage terminé !** {deleted_count} supprimés, {failed_count} échecs")
        return deleted_count

    # ------------------------------------------------------------------ #
    # CAPTURE (backup en mémoire, à partir d'un serveur live)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _capture_overwrites(overwrites: dict) -> List[PermissionOverwriteData]:
        """Capture les overwrites par NOM de rôle uniquement (les overwrites de
        membre sont ignorées : elles n'ont pas de sens hors du serveur source)."""
        result = []
        for target, overwrite in overwrites.items():
            if isinstance(target, discord.Role):
                allow, deny = overwrite.pair()
                target_type = "everyone" if target.is_default() else "role"
                result.append(PermissionOverwriteData(
                    target_type=target_type,
                    target_name=target.name,
                    allow=allow.value,
                    deny=deny.value,
                ))
        return result

    async def build_backup(self, guild: discord.Guild, components: Set[str]) -> ServerBackup:
        """Construit un ServerBackup en mémoire depuis un serveur Discord vivant,
        en ne capturant que les composants demandés."""
        include_permissions = "permissions" in components

        roles_data = []
        if "roles" in components:
            for role in guild.roles:
                if role.name != "@everyone" and not role.managed:
                    roles_data.append(RoleData(
                        name=role.name,
                        color=role.color.value,
                        permissions=role.permissions.value,
                        position=role.position,
                        hoist=role.hoist,
                        mentionable=role.mentionable,
                    ))

        categories_data = []
        channels_data = []
        if "channels" in components:
            for category in guild.categories:
                categories_data.append(CategoryData(
                    name=category.name,
                    position=category.position,
                    permission_overwrites=self._capture_overwrites(category.overwrites) if include_permissions else [],
                ))

            for channel in guild.channels:
                if isinstance(channel, discord.CategoryChannel):
                    continue
                overwrites = self._capture_overwrites(channel.overwrites) if include_permissions else []
                category_name = channel.category.name if channel.category else None

                if isinstance(channel, discord.TextChannel):
                    channels_data.append(ChannelData(
                        name=channel.name, type='text', position=channel.position,
                        category_name=category_name, topic=channel.topic,
                        slowmode_delay=channel.slowmode_delay, nsfw=channel.nsfw,
                        permission_overwrites=overwrites,
                    ))
                elif isinstance(channel, discord.VoiceChannel):
                    channels_data.append(ChannelData(
                        name=channel.name, type='voice', position=channel.position,
                        category_name=category_name, bitrate=channel.bitrate,
                        user_limit=channel.user_limit, permission_overwrites=overwrites,
                    ))
                elif isinstance(channel, discord.StageChannel):
                    channels_data.append(ChannelData(
                        name=channel.name, type='stage', position=channel.position,
                        category_name=category_name, topic=getattr(channel, 'topic', None),
                        permission_overwrites=overwrites,
                    ))
                elif isinstance(channel, discord.ForumChannel):
                    channels_data.append(ChannelData(
                        name=channel.name, type='forum', position=channel.position,
                        category_name=category_name, topic=channel.topic,
                        permission_overwrites=overwrites,
                    ))

        emojis_data = []
        if "emojis" in components:
            async with aiohttp.ClientSession() as session:
                for emoji in guild.emojis:
                    try:
                        async with session.get(str(emoji.url)) as resp:
                            if resp.status == 200:
                                image_data = await resp.read()
                                emojis_data.append(EmojiData(
                                    name=emoji.name,
                                    image_data=base64.b64encode(image_data).decode('utf-8'),
                                    is_animated=emoji.animated,
                                ))
                    except Exception:
                        pass

        webhooks_data = []
        if "webhooks" in components:
            for channel in guild.text_channels:
                try:
                    webhooks = await channel.webhooks()
                    for webhook in webhooks:
                        webhooks_data.append(WebhookData(
                            name=webhook.name, channel_name=channel.name, avatar_data=None,
                        ))
                except Exception:
                    pass

        return ServerBackup(
            server_name=guild.name,
            server_id=guild.id,
            backup_date=datetime.now().isoformat(),
            roles=roles_data,
            categories=categories_data,
            channels=channels_data,
            emojis=emojis_data,
            webhooks=webhooks_data,
        )

    async def backup_server(self, guild: discord.Guild, components: Optional[Set[str]] = None) -> tuple:
        """Sauvegarde le serveur sur disque. Retourne (backup, backup_id, filepath)."""
        components = components or ALL_COMPONENTS
        backup = await self.build_backup(guild, components)
        backup_id = f"backup_{guild.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        filepath = self.get_backup_path(backup_id)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(backup.to_json(backup_id))
        return backup, backup_id, filepath

    # ------------------------------------------------------------------ #
    # APPLICATION (restore sur le même serveur OU transfert vers un autre)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_overwrites_dict(guild: discord.Guild, role_map: Dict[str, discord.Role],
                                overwrite_list: List[PermissionOverwriteData]) -> dict:
        result = {}
        for ow in overwrite_list:
            if ow.target_type == "everyone":
                target = guild.default_role
            else:
                target = role_map.get(ow.target_name)
            if target is None:
                continue
            result[target] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(ow.allow), discord.Permissions(ow.deny)
            )
        return result

    async def apply_backup(self, target_guild: discord.Guild, backup: ServerBackup,
                            components: Set[str], log_callback: LogFn = None) -> dict:
        """Applique un ServerBackup à un serveur cible (restore = même serveur,
        transfert = serveur différent). Ne touche que les composants demandés."""

        async def log(msg):
            if log_callback:
                try:
                    await log_callback(msg)
                except Exception:
                    pass

        include_permissions = "permissions" in components
        stats = {"roles": 0, "categories": 0, "channels": 0, "emojis": 0, "webhooks": 0}

        # Rôle map de départ = rôles déjà présents sur le serveur cible
        role_map: Dict[str, discord.Role] = {r.name: r for r in target_guild.roles}

        # --- Étape 1 : Emojis ---
        if "emojis" in components and backup.emojis:
            await log(f"😀 **Emojis** ({len(backup.emojis)})...")
            for emoji_data in backup.emojis:
                try:
                    image_bytes = base64.b64decode(emoji_data.image_data)
                    await target_guild.create_custom_emoji(name=emoji_data.name, image=image_bytes)
                    stats["emojis"] += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    await log(f"⚠️ Erreur emoji {emoji_data.name}: {str(e)[:50]}")

        # --- Étape 2 : Rôles (ordre décroissant de position, puis repositionnement) ---
        created_roles = []
        if "roles" in components and backup.roles:
            await log(f"🎭 **Rôles** ({len(backup.roles)})...")
            sorted_roles = sorted(backup.roles, key=lambda r: r.position, reverse=True)

            for role_data in sorted_roles:
                try:
                    existing = role_map.get(role_data.name)
                    if not existing:
                        new_role = await target_guild.create_role(
                            name=role_data.name,
                            color=discord.Color(role_data.color),
                            permissions=discord.Permissions(role_data.permissions),
                            hoist=role_data.hoist,
                            mentionable=role_data.mentionable,
                        )
                        role_map[role_data.name] = new_role
                        created_roles.append((role_data.position, new_role))
                        stats["roles"] += 1
                        await log(f"  ✅ Rôle créé : {role_data.name}")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    await log(f"⚠️ Erreur rôle {role_data.name}: {str(e)[:50]}")

            if created_roles:
                await log("🔄 **Réorganisation de l'ordre des rôles...**")
                created_roles.sort(key=lambda x: x[0])
                for new_position, (_, role) in enumerate(created_roles, start=1):
                    try:
                        await role.edit(position=new_position)
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        await log(f"⚠️ Impossible de repositionner {role.name}: {str(e)[:50]}")

        # --- Étape 3 : Catégories ---
        category_map: Dict[str, discord.CategoryChannel] = {c.name: c for c in target_guild.categories}
        if "channels" in components and backup.categories:
            await log(f"📂 **Catégories** ({len(backup.categories)})...")
            for cat_data in backup.categories:
                if cat_data.name in category_map:
                    continue
                try:
                    overwrites = (
                        self._build_overwrites_dict(target_guild, role_map, cat_data.permission_overwrites)
                        if include_permissions else {}
                    )
                    new_category = await target_guild.create_category(
                        name=cat_data.name, position=cat_data.position, overwrites=overwrites,
                    )
                    category_map[cat_data.name] = new_category
                    stats["categories"] += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    await log(f"❌ Erreur catégorie {cat_data.name}: {str(e)[:100]}")

        # --- Étape 4 : Salons ---
        if "channels" in components and backup.channels:
            await log(f"💬 **Salons** ({len(backup.channels)})...")
            for ch in backup.channels:
                try:
                    category = category_map.get(ch.category_name) if ch.category_name else None
                    overwrites = (
                        self._build_overwrites_dict(target_guild, role_map, ch.permission_overwrites)
                        if include_permissions else {}
                    )

                    if ch.type == 'text':
                        await target_guild.create_text_channel(
                            name=ch.name, category=category, position=ch.position,
                            topic=ch.topic, slowmode_delay=ch.slowmode_delay or 0,
                            nsfw=ch.nsfw, overwrites=overwrites,
                        )
                    elif ch.type == 'voice':
                        await target_guild.create_voice_channel(
                            name=ch.name, category=category, position=ch.position,
                            bitrate=ch.bitrate or 64000, user_limit=ch.user_limit or 0,
                            overwrites=overwrites,
                        )
                    elif ch.type == 'stage':
                        create_stage = getattr(target_guild, 'create_stage_channel', None)
                        if create_stage:
                            await create_stage(name=ch.name, category=category,
                                                position=ch.position, overwrites=overwrites)
                        else:
                            await log(f"⚠️ Salon stage {ch.name} ignoré (non supporté par cette version)")
                            continue
                    elif ch.type == 'forum':
                        create_forum = getattr(target_guild, 'create_forum', None)
                        if create_forum:
                            await create_forum(name=ch.name, category=category, position=ch.position,
                                                topic=ch.topic, overwrites=overwrites)
                        else:
                            await log(f"⚠️ Forum {ch.name} ignoré (non supporté par cette version)")
                            continue
                    else:
                        continue

                    stats["channels"] += 1
                    await asyncio.sleep(0.35)
                except Exception as e:
                    await log(f"⚠️ Erreur salon {ch.name}: {str(e)[:50]}")

        # --- Étape 5 : Webhooks ---
        if "webhooks" in components and backup.webhooks:
            await log(f"🔌 **Webhooks** ({len(backup.webhooks)})...")
            for webhook_data in backup.webhooks:
                try:
                    target_channel = discord.utils.get(target_guild.text_channels, name=webhook_data.channel_name)
                    if target_channel:
                        await target_channel.create_webhook(name=webhook_data.name)
                        stats["webhooks"] += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    await log(f"⚠️ Erreur webhook {webhook_data.name}: {str(e)[:50]}")

        await log(
            f"✅ **Terminé !**\n"
            f"• Rôles créés : {stats['roles']}\n"
            f"• Catégories créées : {stats['categories']}\n"
            f"• Salons créés : {stats['channels']}\n"
            f"• Emojis créés : {stats['emojis']}\n"
            f"• Webhooks créés : {stats['webhooks']}"
        )
        return stats

    # ------------------------------------------------------------------ #
    # RESTORE : depuis un backup JSON, sur le même serveur
    # ------------------------------------------------------------------ #

    async def restore_server(self, guild: discord.Guild, backup_id: str,
                              components: Optional[Set[str]] = None, log_callback: LogFn = None):
        components = components or ALL_COMPONENTS
        backup = self.load_backup(backup_id)
        if backup is None:
            if log_callback:
                await log_callback(f"❌ Backup `{backup_id}` introuvable.")
            return None

        if not guild.me.guild_permissions.manage_channels:
            if log_callback:
                await log_callback("❌ Le bot n'a pas la permission 'Gérer les salons'")
            return None

        return await self.apply_backup(guild, backup, components, log_callback)

    # ------------------------------------------------------------------ #
    # TRANSFERT : depuis un serveur live vers un autre serveur
    # ------------------------------------------------------------------ #

    async def transfer_server(self, source_guild: discord.Guild, target_guild: discord.Guild,
                               components: Set[str], clean_target: bool = False,
                               log_callback: LogFn = None):
        async def log(msg):
            if log_callback:
                try:
                    await log_callback(msg)
                except Exception:
                    pass

        if not target_guild.me.guild_permissions.manage_channels or not target_guild.me.guild_permissions.manage_roles:
            await log("❌ Le bot n'a pas les permissions nécessaires sur le serveur de destination.")
            return None

        await log(f"📥 **Capture des données depuis « {source_guild.name} »...**")
        backup = await self.build_backup(source_guild, components)

        if clean_target:
            await self.clear_server(target_guild, log_callback=log_callback)

        await log(f"📤 **Application sur « {target_guild.name} »...**")
        return await self.apply_backup(target_guild, backup, components, log_callback)