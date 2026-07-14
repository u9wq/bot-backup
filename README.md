# Discord Server Backup & Transfer Bot

Bot Discord permettant de sauvegarder, restaurer et transferer la structure complete d'un serveur (roles, salons, categories, permissions, emojis, webhooks) via un panel interactif a menus deroulants.

## Fonctionnalites

- Sauvegarde d'un serveur en fichier JSON, envoye directement en message prive
- Restauration d'une sauvegarde sur le meme serveur (choix via menu deroulant)
- Transfert complet de la structure d'un serveur vers un autre serveur ou le bot est present (choix du serveur cible via menu deroulant)
- Selection fine des elements a traiter : roles, salons et categories, permissions, emojis, webhooks
- Confirmation obligatoire avant toute action destructive
- Gestion des sauvegardes : liste, suppression, import d'un fichier JSON externe
- Toutes les actions sensibles necessitent la permission Administrateur

## Prerequis

- Python 3.9 ou superieur
- Un bot Discord cree sur le [Portail developpeur Discord](https://discord.com/developers/applications)

## Installation

1. Cloner le depot

   ```bash
   git clone https://github.com/<ton-utilisateur>/<ton-repo>.git
   cd <ton-repo>
   ```

2. Installer les dependances

   ```bash
   pip install -r requirements.txt
   ```

3. Configurer le token

   Copie `.env.example` en `.env` et colle ton token :

   ```bash
   cp .env.example .env
   ```

   ```
   DISCORD_TOKEN=ton_token_ici
   ```

   Le fichier `.env` est ignore par Git (`.gitignore`) : ne le commit jamais et ne partage jamais ton token.

## Configuration du bot sur le portail Discord

### 1. Activer les Privileged Gateway Intents

Sur la page de ton application, onglet Bot, section Privileged Gateway Intents, active :

- Server Members Intent
- Message Content Intent

Sans cela, le bot plantera au demarrage avec une erreur `PrivilegedIntentsRequired`.

### 2. Generer le lien d'invitation

Onglet OAuth2 puis URL Generator :

- Scopes : `bot`
- Bot Permissions : `Administrator` (recommande, le bot doit pouvoir creer/supprimer roles, salons, webhooks et emojis)

Copie l'URL generee et ouvre-la dans un navigateur pour inviter le bot sur ton ou tes serveurs.

Pour un transfert, le bot doit etre invite avec les droits Administrateur sur les deux serveurs (source et destination).

## Lancer le bot

```bash
python main.py
```

## Utilisation

### Le panel principal

Dans un salon texte, tape :

```
!panel
```

1. Menu 1 : coche ou decoche les elements a inclure (tout est selectionne par defaut)
2. Menu 2 : choisis l'action, Sauvegarder, Restaurer ou Transferer
3. Clique sur "Executer l'action"

La suite se deroule en messages prives avec le bot. Assure-toi d'autoriser les MP venant des membres du serveur (Parametres du serveur, Confidentialite).

| Action | Ce qu'il se passe |
|---|---|
| Sauvegarder | Le bot genere un fichier JSON et te l'envoie en MP |
| Restaurer | Un menu deroulant liste tes sauvegardes, tu choisis, confirmation, puis le serveur actuel est nettoye et reconstruit |
| Transferer | Un menu deroulant liste les serveurs ou le bot est present, tu choisis la destination, confirmation, puis le serveur cible est nettoye et reconstruit a l'identique |

### Commandes complementaires

| Commande | Description |
|---|---|
| `!panel` | Affiche le panel interactif |
| `!backups` | Liste toutes les sauvegardes stockees (nom du serveur, date, contenu) |
| `!deletebackup <id>` | Supprime une sauvegarde du disque |
| `!import` (avec un fichier `.json` joint) | Importe une sauvegarde JSON externe pour pouvoir la restaurer ensuite |

Toutes les commandes necessitent d'etre Administrateur sur le serveur.

## Structure du projet

```
.
├── main.py             # Bot Discord, commandes, panel interactif (UI)
├── backup_handler.py   # Logique de sauvegarde, restauration, transfert
├── models.py           # Structures de donnees (dataclasses) et serialisation JSON
├── config.py           # Configuration (token, dossier de sauvegardes)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Notes importantes

- Les actions de restauration et de transfert sont destructives : elles suppriment tous les salons et roles existants du serveur cible avant de recreer ceux de la sauvegarde. Utilise toujours la confirmation proposee pour verifier avant de valider.
- Les permissions de salon ou categorie sont sauvegardees par nom de role et non par ID, car les IDs n'ont plus de sens une fois transferes sur un autre serveur.
- Les permissions accordees individuellement a des membres, et non a des roles, ne sont pas sauvegardees, car elles n'ont pas de sens hors du contexte du serveur d'origine.
- Le dossier `backups/` contient les sauvegardes en clair (JSON) et n'est volontairement pas versionne (voir `.gitignore`) car il peut contenir des donnees de serveur.

## Securite

- Ne commit jamais ton fichier `.env` ni ton token Discord.
- Si un token a ete expose (commit, capture d'ecran, message public), regenere-le immediatement depuis le portail developpeur (Bot, Reset Token).
- Il est recommande de restreindre l'acces aux commandes `!panel`, `!backups`, `!deletebackup` et `!import` aux administrateurs du serveur, ce qui est deja fait par defaut dans ce bot.

## Contribuer

Les pull requests sont les bienvenues. Pour des changements majeurs, ouvre d'abord une issue pour en discuter.

## Licence

Ce projet est sous licence [MIT](LICENSE).
