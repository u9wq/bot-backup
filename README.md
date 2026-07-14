# 🎛️ Discord Server Backup & Transfer Bot

Bot Discord permettant de **sauvegarder**, **restaurer** et **transférer** la structure complète d'un serveur (rôles, salons, catégories, permissions, emojis, webhooks) via un panel interactif à menus déroulants — sans taper la moindre commande complexe.

## ✨ Fonctionnalités

- 💾 **Sauvegarde** d'un serveur en fichier JSON, envoyé directement en message privé
- 🔄 **Restauration** d'une sauvegarde sur le même serveur (choix via menu déroulant)
- 🚀 **Transfert** complet de la structure d'un serveur vers un autre serveur où le bot est présent (choix du serveur cible via menu déroulant)
- ☑️ Sélection fine des éléments à traiter : rôles, salons & catégories, permissions, emojis, webhooks
- ⚠️ Confirmation Oui/Non obligatoire avant toute action destructive
- 📦 Gestion des sauvegardes : liste, suppression, import d'un fichier JSON externe
- 🔒 Toutes les actions sensibles nécessitent la permission **Administrateur**

## 📋 Prérequis

- Python 3.9 ou supérieur
- Un bot Discord créé sur le [Portail développeur Discord](https://discord.com/developers/applications)

## 🚀 Installation

1. **Cloner le dépôt**
   ```bash
   git clone https://github.com/<ton-utilisateur>/<ton-repo>.git
   cd <ton-repo>
   ```

2. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurer le token**

   Copie `.env.example` en `.env` et colle ton token :
   ```bash
   cp .env.example .env
   ```
   ```
   DISCORD_TOKEN=ton_token_ici
   ```

   ⚠️ Le fichier `.env` est ignoré par Git (`.gitignore`) — ne le commit jamais et ne partage jamais ton token.

## 🔧 Configuration du bot sur le portail Discord

### 1. Activer les Privileged Gateway Intents

Sur la page de ton application → onglet **Bot** → section **Privileged Gateway Intents**, active :
- ✅ **Server Members Intent**
- ✅ **Message Content Intent**

Sans ça, le bot plantera au démarrage avec une erreur `PrivilegedIntentsRequired`.

### 2. Générer le lien d'invitation

Onglet **OAuth2 → URL Generator** :
- **Scopes** : `bot`
- **Bot Permissions** : `Administrator` (recommandé — le bot doit pouvoir créer/supprimer rôles, salons, webhooks et emojis)

Copie l'URL générée et ouvre-la dans un navigateur pour inviter le bot sur ton/tes serveur(s).

> Pour un **transfert**, le bot doit être invité avec les droits Administrateur **sur les deux serveurs** (source et destination).

## ▶️ Lancer le bot

```bash
python main.py
```

## 🎮 Utilisation

### Le panel principal

Dans un salon texte, tape :
```
!panel
```

1. **Menu 1** — coche/décoche les éléments à inclure (tout est sélectionné par défaut)
2. **Menu 2** — choisis l'action : Sauvegarder / Restaurer / Transférer
3. Clique sur **Exécuter l'action**

➡️ La suite se déroule **en messages privés** avec le bot. Assure-toi d'autoriser les MP venant des membres du serveur (Paramètres du serveur → Confidentialité).

| Action | Ce qu'il se passe |
|---|---|
| 💾 **Sauvegarder** | Le bot génère un fichier JSON et te l'envoie en MP |
| 🔄 **Restaurer** | Un menu déroulant liste tes sauvegardes → tu choisis → confirmation → le serveur actuel est nettoyé puis reconstruit |
| 🚀 **Transférer** | Un menu déroulant liste les serveurs où le bot est présent → tu choisis la destination → confirmation → le serveur cible est nettoyé puis reconstruit à l'identique |

### Commandes complémentaires

| Commande | Description |
|---|---|
| `!panel` | Affiche le panel interactif |
| `!backups` | Liste toutes les sauvegardes stockées (nom du serveur, date, contenu) |
| `!deletebackup <id>` | Supprime une sauvegarde du disque |
| `!import` *(+ fichier `.json` joint)* | Importe une sauvegarde JSON externe pour pouvoir la restaurer ensuite |

Toutes les commandes nécessitent d'être **Administrateur** sur le serveur.

## 📁 Structure du projet

```
.
├── main.py             # Bot Discord, commandes, panel interactif (UI)
├── backup_handler.py   # Logique de sauvegarde/restauration/transfert
├── models.py           # Structures de données (dataclasses) + sérialisation JSON
├── config.py           # Configuration (token, dossier de sauvegardes)
├── requirements.txt
├── .env.example
└── .gitignore
```

## ⚠️ Notes importantes

- Les actions de **restauration** et de **transfert** sont **destructives** : elles suppriment tous les salons et rôles existants du serveur cible avant de recréer ceux de la sauvegarde. Utilise toujours la confirmation proposée pour vérifier avant de valider.
- Les permissions de salon/catégorie sont sauvegardées **par nom de rôle** (pas par ID), car les IDs n'ont plus de sens une fois transférés sur un autre serveur.
- Les permissions accordées individuellement à des membres (et non à des rôles) ne sont **pas** sauvegardées, car elles n'ont pas de sens hors du contexte du serveur d'origine.
- Le dossier `backups/` contient les sauvegardes en clair (JSON) — il n'est **volontairement pas versionné** (voir `.gitignore`) car il peut contenir des données de serveur.

## 🔒 Sécurité

- Ne commit **jamais** ton fichier `.env` ni ton token Discord.
- Si un token a été exposé (commit, capture d'écran, message public...), régénère-le immédiatement depuis le portail développeur (**Bot → Reset Token**).
- Il est recommandé de restreindre l'accès aux commandes `!panel`, `!backups`, `!deletebackup` et `!import` aux administrateurs du serveur — ce qui est déjà fait par défaut dans ce bot.

## 🤝 Contribuer

Les pull requests sont les bienvenues. Pour des changements majeurs, ouvre d'abord une issue pour en discuter.

## 📄 Licence

Ce projet est sous licence [MIT](LICENSE).
