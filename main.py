import discord
from discord.ext import commands
import asyncio
import io

from config import TOKEN
from backup_handler import BackupHandler, ALL_COMPONENTS

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.messages = True

MAX_SELECT_OPTIONS = 25


# ------------------------------------------------------------------ #
# Petits composants réutilisables : confirmation, choix de backup,
# choix de serveur de destination.
# ------------------------------------------------------------------ #

class ConfirmView(discord.ui.View):
    """Boutons Oui/Non. self.value vaut True/False/None (timeout) une fois
    la vue terminée (attendre avec `await view.wait()`)."""

    def __init__(self, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.value = None

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="✅ **Confirmé.** Traitement en cours...", view=self)
        self.stop()

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ **Action annulée.**", view=self)
        self.stop()

    async def on_timeout(self):
        self.value = None
        for child in self.children:
            child.disabled = True


class BackupSelectView(discord.ui.View):
    """Menu déroulant listant les sauvegardes disponibles."""

    def __init__(self, handler: BackupHandler, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.chosen: str | None = None

        backup_ids = sorted(handler.list_backups(), reverse=True)[:MAX_SELECT_OPTIONS]
        options = []
        for bid in backup_ids:
            info = handler.get_backup_summary(bid)
            if info:
                label = f"{info['server_name']}"[:100]
                description = (
                    f"{info['backup_date'][:19].replace('T', ' ')} • "
                    f"{info['roles']} rôles, {info['channels']} salons"
                )[:100]
            else:
                label, description = bid[:100], "Sauvegarde"
            options.append(discord.SelectOption(label=label, description=description, value=bid))

        if not options:
            options.append(discord.SelectOption(label="Aucune sauvegarde disponible", value="__none__"))

        select = discord.ui.Select(placeholder="Choisissez une sauvegarde à restaurer", options=options)

        async def callback(interaction: discord.Interaction):
            value = select.values[0]
            if value == "__none__":
                await interaction.response.edit_message(content="❌ Aucune sauvegarde disponible.", view=None)
                self.chosen = None
            else:
                self.chosen = value
                await interaction.response.edit_message(
                    content=f"✅ Sauvegarde sélectionnée : `{value}`", view=None
                )
            self.stop()

        select.callback = callback
        self.add_item(select)


class GuildSelectView(discord.ui.View):
    """Menu déroulant listant les serveurs où le bot est présent (hors serveur source)."""

    def __init__(self, bot: commands.Bot, source_guild_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.chosen_id: int | None = None

        candidates = [g for g in bot.guilds if g.id != source_guild_id][:MAX_SELECT_OPTIONS]
        options = []
        for g in candidates:
            is_admin = g.me.guild_permissions.administrator if g.me else False
            description = "✅ Droits administrateur" if is_admin else "⚠️ Pas administrateur ici"
            options.append(discord.SelectOption(label=g.name[:100], description=description, value=str(g.id)))

        if not options:
            options.append(discord.SelectOption(label="Aucun autre serveur trouvé", value="__none__"))

        select = discord.ui.Select(placeholder="Choisissez le serveur de destination", options=options)

        async def callback(interaction: discord.Interaction):
            value = select.values[0]
            if value == "__none__":
                await interaction.response.edit_message(
                    content="❌ Le bot n'est présent sur aucun autre serveur. Invitez-le d'abord avec les droits Administrateur.",
                    view=None,
                )
                self.chosen_id = None
            else:
                guild = bot.get_guild(int(value))
                self.chosen_id = int(value)
                await interaction.response.edit_message(
                    content=f"✅ Serveur de destination : **{guild.name if guild else value}**", view=None
                )
            self.stop()

        select.callback = callback
        self.add_item(select)


# ------------------------------------------------------------------ #
# Panel principal
# ------------------------------------------------------------------ #

class BackupPanel(discord.ui.View):
    def __init__(self, bot: "BackupBot"):
        super().__init__(timeout=None)
        self.bot = bot
        # Par défaut, tout est sélectionné
        self.selected_components = set(ALL_COMPONENTS)
        self.action = "backup"

    @discord.ui.select(
        placeholder="1️⃣ Éléments à inclure (Tout par défaut)",
        min_values=1,
        max_values=5,
        options=[
            discord.SelectOption(label="Rôles", value="roles", default=True),
            discord.SelectOption(label="Salons & Catégories", value="channels", default=True),
            discord.SelectOption(label="Permissions", value="permissions", default=True),
            discord.SelectOption(label="Emojis", value="emojis", default=True),
            discord.SelectOption(label="Webhooks", value="webhooks", default=True),
        ]
    )
    async def component_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_components = set(select.values)
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="2️⃣ Action à effectuer",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="💾 Sauvegarder & Télécharger JSON", value="backup"),
            discord.SelectOption(label="🔄 Restaurer (sur ce serveur)", value="restore"),
            discord.SelectOption(label="🚀 Transférer vers un autre serveur", value="transfer"),
        ]
    )
    async def action_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.action = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Exécuter l'action", style=discord.ButtonStyle.green, row=2)
    async def execute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission administrateur requise.", ephemeral=True)
            return

        await interaction.response.send_message(
            "✅ Action lancée ! Regardez vos messages privés pour la suite.", ephemeral=True
        )
        try:
            user_dm = await interaction.user.create_dm()
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Impossible de vous envoyer un MP. Activez les messages privés depuis ce serveur.", ephemeral=True
            )
            return

        async def log_to_dm(msg: str):
            await user_dm.send(msg[:2000])

        handler = self.bot.backup_handler

        # ---------------------------------------------------------
        # ACTION 1 : SAUVEGARDE ET EXPORT JSON
        # ---------------------------------------------------------
        if self.action == "backup":
            await log_to_dm(
                f"🔄 **Création de la sauvegarde en cours...**\n"
                f"Éléments : `{', '.join(sorted(self.selected_components))}`"
            )
            try:
                backup, backup_id, filepath = await handler.backup_server(
                    interaction.guild, self.selected_components
                )
                await log_to_dm(f"✅ Sauvegarde réussie (ID: `{backup_id}`).\nVoici le fichier JSON de votre serveur :")
                await user_dm.send(file=discord.File(filepath))
            except Exception as e:
                await log_to_dm(f"❌ Erreur : {str(e)}")

        # ---------------------------------------------------------
        # ACTION 2 : RESTAURATION
        # ---------------------------------------------------------
        elif self.action == "restore":
            select_view = BackupSelectView(handler)
            await user_dm.send("Choisissez la sauvegarde à restaurer :", view=select_view)
            await select_view.wait()

            if not select_view.chosen:
                await log_to_dm("❌ Action annulée (aucune sauvegarde sélectionnée ou délai expiré).")
                return

            backup_id = select_view.chosen
            confirm_view = ConfirmView()
            await user_dm.send(
                f"⚠️ **Attention** : restaurer `{backup_id}` va **supprimer tous les salons et rôles actuels** "
                f"de **{interaction.guild.name}** avant de recréer ceux de la sauvegarde.\n"
                f"Éléments concernés : `{', '.join(sorted(self.selected_components))}`\n"
                f"Confirmez-vous ?",
                view=confirm_view,
            )
            await confirm_view.wait()

            if not confirm_view.value:
                if confirm_view.value is None:
                    await log_to_dm("❌ Action annulée (délai expiré).")
                return

            await log_to_dm("🗑️ Nettoyage du serveur actuel...")
            await handler.clear_server(interaction.guild, log_callback=log_to_dm)

            await log_to_dm(f"🔄 Restauration des éléments : `{', '.join(sorted(self.selected_components))}`")
            await handler.restore_server(
                interaction.guild, backup_id, components=self.selected_components, log_callback=log_to_dm
            )
            await log_to_dm("✅ Restauration terminée !")

        # ---------------------------------------------------------
        # ACTION 3 : TRANSFERT INTER-SERVEUR
        # ---------------------------------------------------------
        elif self.action == "transfer":
            guild_view = GuildSelectView(self.bot, interaction.guild.id)
            await user_dm.send("Choisissez le serveur de destination :", view=guild_view)
            await guild_view.wait()

            if not guild_view.chosen_id:
                await log_to_dm("❌ Action annulée (aucun serveur sélectionné ou délai expiré).")
                return

            target_guild = self.bot.get_guild(guild_view.chosen_id)
            if not target_guild:
                await log_to_dm("❌ Serveur introuvable (le bot a peut-être quitté ce serveur entre-temps).")
                return

            if not target_guild.me.guild_permissions.administrator:
                await log_to_dm(
                    f"❌ Le bot n'a pas les droits Administrateur sur **{target_guild.name}**. "
                    f"Corrigez ses permissions puis réessayez."
                )
                return

            confirm_view = ConfirmView()
            await user_dm.send(
                f"⚠️ **Attention** : ceci va **supprimer tous les salons et rôles actuels** de "
                f"**{target_guild.name}**, puis y recréer ceux de **{interaction.guild.name}**.\n"
                f"Éléments transférés : `{', '.join(sorted(self.selected_components))}`\n"
                f"Confirmez-vous ce transfert ?",
                view=confirm_view,
            )
            await confirm_view.wait()

            if not confirm_view.value:
                if confirm_view.value is None:
                    await log_to_dm("❌ Action annulée (délai expiré).")
                return

            await log_to_dm(f"🚀 Début du transfert vers **{target_guild.name}**...")
            try:
                await handler.transfer_server(
                    source_guild=interaction.guild,
                    target_guild=target_guild,
                    components=self.selected_components,
                    clean_target=True,
                    log_callback=log_to_dm,
                )
                await log_to_dm("✅ Transfert terminé avec succès !")
            except Exception as e:
                await log_to_dm(f"❌ Erreur inattendue : {str(e)}")


class BackupBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents, help_command=None)
        self.backup_handler = BackupHandler(self)

    async def setup_hook(self):
        print(f"✅ Bot {self.user} connecté !")


bot = BackupBot()


@bot.command(name='panel')
async def panel_command(ctx: commands.Context):
    """Affiche le panel interactif de gestion des backups et transferts"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Permission administrateur requise.")
        return

    embed = discord.Embed(
        title="🎛️ Panel de Gestion Serveur",
        description=(
            "1️⃣ Choisissez les éléments à inclure\n"
            "2️⃣ Choisissez l'action (sauvegarde / restauration / transfert)\n"
            "3️⃣ Cliquez sur **Exécuter l'action** — la suite se passe en messages privés."
        ),
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed, view=BackupPanel(bot))


@bot.command(name='backups')
async def backups_command(ctx: commands.Context):
    """Liste les sauvegardes disponibles sur ce bot"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Permission administrateur requise.")
        return

    backup_ids = sorted(bot.backup_handler.list_backups(), reverse=True)
    if not backup_ids:
        await ctx.send("📭 Aucune sauvegarde disponible pour le moment.")
        return

    embed = discord.Embed(title="📦 Sauvegardes disponibles", color=discord.Color.blurple())
    for bid in backup_ids[:MAX_SELECT_OPTIONS]:
        info = bot.backup_handler.get_backup_summary(bid)
        if info:
            embed.add_field(
                name=f"`{bid}`",
                value=(
                    f"**Serveur :** {info['server_name']}\n"
                    f"**Date :** {info['backup_date'][:19].replace('T', ' ')}\n"
                    f"**Rôles :** {info['roles']} • **Salons :** {info['channels']} • "
                    f"**Emojis :** {info['emojis']} • **Webhooks :** {info['webhooks']}"
                ),
                inline=False,
            )
    if len(backup_ids) > MAX_SELECT_OPTIONS:
        embed.set_footer(text=f"... et {len(backup_ids) - MAX_SELECT_OPTIONS} autre(s) sauvegarde(s).")
    await ctx.send(embed=embed)


@bot.command(name='deletebackup')
async def delete_backup_command(ctx: commands.Context, backup_id: str = None):
    """Supprime une sauvegarde du disque : !deletebackup <id>"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Permission administrateur requise.")
        return
    if not backup_id:
        await ctx.send("Utilisation : `!deletebackup <id>` (voir `!backups` pour la liste des IDs).")
        return

    path = bot.backup_handler.get_backup_path(backup_id)
    import os
    if not os.path.exists(path):
        await ctx.send(f"❌ Sauvegarde `{backup_id}` introuvable.")
        return
    os.remove(path)
    await ctx.send(f"🗑️ Sauvegarde `{backup_id}` supprimée.")


@bot.command(name='import')
async def import_command(ctx: commands.Context):
    """Importe un fichier JSON de sauvegarde envoyé en pièce jointe : !import (+ fichier .json)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Permission administrateur requise.")
        return
    if not ctx.message.attachments:
        await ctx.send("📎 Joignez un fichier `.json` de sauvegarde à votre message `!import`.")
        return

    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith('.json'):
        await ctx.send("❌ Le fichier doit être un `.json`.")
        return

    try:
        content = await attachment.read()
        backup_id = bot.backup_handler.save_uploaded_backup(attachment.filename, content)
        await ctx.send(f"✅ Sauvegarde importée avec succès. ID : `{backup_id}`\nUtilisez `!panel` pour la restaurer.")
    except Exception as e:
        await ctx.send(f"❌ Fichier invalide ou corrompu : {str(e)}")


if __name__ == "__main__":
    if not TOKEN:
        print("❌ Token non trouvé dans .env")
    else:
        bot.run(TOKEN)
