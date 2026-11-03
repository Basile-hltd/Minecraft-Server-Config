# Minecraft-Server-Config

Déploiement d'un serveur Minecraft en une commande depuis Linux.

**Ansible** prépare la machine (Debian/Ubuntu) : paquets, pare-feu, SSH durci, Docker.
Il lance ensuite le serveur décrit dans `server/docker-compose.yml`
(image [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server), Paper par défaut),
avec des sauvegardes automatiques.

## Structure

```
ansible/
  ansible.cfg
  requirements.yml         Collections Ansible
  site.yml                 Playbook principal
  inventory/hosts.yml      La machine cible (IP + utilisateur SSH)
  inventory/local.yml      Pour lancer Ansible depuis la machine cible elle-même
  group_vars/all.yml       Utilisateur admin, clé GitHub, ports
  roles/base               Paquets, pare-feu (ufw), fail2ban, SSH durci, mises à jour auto, veille capot
  roles/docker             Installation de Docker + compose
  roles/minecraft          Copie de server/ sur la machine + docker compose up
server/
  docker-compose.yml       Config du serveur : version, RAM, gameplay, joueurs, plugins, sauvegardes
  config/                  Copié à la racine de /data à chaque démarrage :
    bukkit.yml               active le générateur Isohypse sur le monde principal
    plugins/Isohypse/config.yml                     réglages d'Isohypse
    plugins/LodServerSupport/lss-server-config.yaml réglages de LOD Server Support
  whitelist/               Page web d'ajout à la whitelist (copiée dans /opt/minecraft/whitelist) :
    app.py                   script Python (RCON), index.html la page, Caddyfile le HTTPS
requirements.txt           Dépendances Python (ansible-core)
```

## Prérequis

- **Machine cible** : Debian/Ubuntu, avec OpenSSH, un utilisateur `basile` (ou celui défini dans `admin_user`)
  disposant de `sudo`, et ta clé publique SSH déjà installée (par exemple importée depuis GitHub à l'installation).
- **Poste de contrôle** : Linux (ou macOS) avec `python3`, `python3-venv`, `rsync` et un accès SSH à la machine cible.
  Ansible ne tourne pas sous Windows natif.

```bash
sudo apt install -y python3-venv rsync
```

## 1. Installer Ansible

```bash
git clone git@github.com:Basile-hltd/Minecraft-Server-Config.git
cd Minecraft-Server-Config

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ansible
python -m ansible.cli.galaxy collection install -r requirements.yml
```

Les commandes suivantes se lancent depuis le dossier `ansible/`, avec le venv activé
(`source .venv/bin/activate` à chaque nouveau terminal).

## 2. Configurer

| Fichier | À régler |
|---|---|
| `ansible/inventory/hosts.yml` | `ansible_host` : IP ou nom de la machine ; `ansible_user` |
| `ansible/group_vars/all.yml` | `admin_user`, `admin_github_user` (ou `admin_ssh_public_keys`) ; **`mc_version`, `isohypse_version`, `lss_version` et `orebfuscator_version`** (versions du serveur et des plugins, seul endroit à modifier) |
| `server/docker-compose.yml` | `MEMORY`, `MOTD`, `OPS`, `WHITELIST`, `DIFFICULTY`, `LEVEL_TYPE`... |
| `server/config/` | Réglages des plugins (voir [Réglages des plugins](#réglages-des-plugins)) |

## Versions de Minecraft et des plugins

Les versions se changent à **un seul endroit** : `ansible/group_vars/all.yml`.

```yaml
mc_version: "26.3"          # version de Minecraft/Paper du serveur
isohypse_version: "0.2.2"   # plugin Isohypse (tag v... sur Basile-hltd/Minecraft-isohypse)
lss_version: "0.20.0"       # plugin LOD Server Support (Modrinth)
orebfuscator_version: "5.6.2"   # plugin Orebfuscator, anti-xray (Modrinth)
```

Au déploiement, Ansible les écrit dans `/opt/minecraft/.env`, et `server/docker-compose.yml` s'en sert pour :

- la version de Paper ;
- **Isohypse** : le jar `isohypse-<isohypse_version>-minecraft-<majeure.mineure>.jar` des releases GitHub du plugin
  (26.3 -> `minecraft-26.3`, 26.1.2 -> `minecraft-26.1`) ;
- **LOD Server Support** : la version Modrinth `v<lss_version>+paper+mc<mc_version>` (version exacte de Minecraft) ;
- **Orebfuscator** (anti-xray) : la version Modrinth `<orebfuscator_version>`, avec ses réglages par défaut (mode 2 : les minerais cachés
  sont mêlés à de faux minerais). Son dossier `plugins/Orebfuscator/` est créé au premier lancement ; pour le régler, ajouter
  ses fichiers dans `server/config/plugins/Orebfuscator/`.

Pour mettre à jour : modifier ces valeurs, puis `python -m ansible.cli.playbook site.yml --tags minecraft`.
Chaque plugin doit déjà avoir publié un jar pour la version de Minecraft voulue
([releases Isohypse](https://github.com/Basile-hltd/Minecraft-isohypse/releases),
[versions LSS](https://modrinth.com/plugin/lod-server-support/versions),
[versions Orebfuscator](https://modrinth.com/plugin/orebfuscator/versions)).

`REMOVE_OLD_MODS` est activé : les jars de `plugins/` absents de `PLUGINS` et `MODRINTH_PROJECTS` sont supprimés au démarrage.

## Réglages des plugins

Les réglages sont dans `server/config/`, dont l'arborescence reproduit celle de `/data`. Au démarrage du conteneur,
tout son contenu est copié à la racine de `/data` et **écrase** les fichiers du serveur
(`COPY_CONFIG_DEST=/data`, `SYNC_SKIP_NEWER_IN_DESTINATION=false`) : c'est le dépôt qui fait foi, une modification
faite à la main sur le serveur est perdue au redémarrage suivant.

| Fichier | Rôle |
|---|---|
| `server/config/bukkit.yml` | `generator: Isohypse` pour le monde principal (Paper complète le reste) |
| `server/config/plugins/Isohypse/config.yml` | Lieu réel (latitude, longitude, taille), hauteur du monde, zones, structures. Doc : [README d'Isohypse](https://github.com/Basile-hltd/Minecraft-isohypse#configuration) |
| `server/config/plugins/LodServerSupport/lss-server-config.yaml` | Distance des LOD, génération, bande passante, disque, confidentialité. Fichier complet, commenté par le plugin |
| `LEVEL_TYPE` dans `server/docker-compose.yml` | Style de génération d'Isohypse : `Vanilla+`, `Realistic` ou `Fairy` |

Les valeurs de départ viennent de `tools/server/` du dépôt Isohypse (v0.2.2) : `config.yml` tel quel,
`lss.yml` appliqué au fichier par défaut de LSS 0.20.0 (`reader_threads` et `max_concurrent_reads` à 8),
et `level-type=Realistic` de son `server.properties` (ses autres clés sont propres au serveur de test).

Pour appliquer un changement : modifier le fichier, puis `python -m ansible.cli.playbook site.yml --tags minecraft`
et redémarrer le serveur (`sudo docker compose restart mc` dans `/opt/minecraft` ; Ansible ne redémarre le conteneur
que si `docker-compose.yml` ou `.env` changent).

**Monde neuf obligatoire pour Isohypse.** Le générateur, `LEVEL_TYPE` et `world.max_height` ne s'appliquent qu'à un
monde qui n'existe pas encore. Sur un monde déjà généré, seuls les nouveaux chunks utilisent Isohypse, avec des
raccords visibles. Pour repartir de zéro, arrêter le serveur et supprimer `world`, `world_nether` et `world_the_end`
dans `/opt/minecraft/data` (les sauvegardes restent dans `/opt/minecraft/backups`).

Avec `Realistic`, le premier démarrage télécharge les altitudes réelles de la zone (plusieurs Go pour 50 km de côté,
supprimés ensuite) : le serveur attend la fin avant d'ouvrir. Changer la zone, `world.max_height` ou
`realistic.scale.*` relance ce téléchargement.

**LOD Server Support** envoie le terrain lointain aux joueurs qui ont un mod client compatible
([Voxy](https://modrinth.com/mod/voxy) ou [Distant Horizons](https://modrinth.com/mod/distanthorizons)) ;
les autres jouent normalement. Après une modification de son fichier, `/lsslod reload` dans la console applique
les réglages qui ne sont pas marqués `[restart]`.

## 3. Déployer

Vérifier que la machine répond (SSH + Python, sans `sudo`) :

```bash
python -m ansible.cli.adhoc minecraft -m ping -e ansible_become=false
```

Simuler (ne modifie rien ; les tâches dépendant de Docker peuvent échouer en simulation, c'est normal) :

```bash
python -m ansible.cli.playbook site.yml --ask-become-pass --check --diff
```

Déployer :

```bash
python -m ansible.cli.playbook site.yml --ask-become-pass
```

`--ask-become-pass` demande le mot de passe `sudo` de **la machine cible (le serveur Minecraft)**, pour l'utilisateur
`admin_user` : c'est le mot de passe que tu tapes sur le serveur quand tu fais `sudo`, pas celui de ton poste de contrôle. Après le premier déploiement,
`sudo` est sans mot de passe pour `admin_user` et ce flag n'est plus nécessaire.

Le déploiement est idempotent : relance la même commande après chaque modification de config.
Pour ne redéployer que la config du serveur :

```bash
python -m ansible.cli.playbook site.yml --tags minecraft
```

### Dépannage : `sudo-rs` (Ubuntu 25.10 et 26.04)

Depuis Ubuntu 25.10, `sudo` est remplacé par `sudo-rs`. Son prompt n'est pas reconnu par Ansible, ce qui donne
`Timeout (12s) waiting for privilege escalation prompt` (ou `sudo: interactive authentication is required`
si aucun mot de passe n'est fourni). Le playbook détecte automatiquement `sudo.ws` (le `sudo` classique, fourni
en parallèle) et l'utilise. Aucune action n'est nécessaire pour `site.yml`.

Pour une commande ad-hoc (hors playbook) sur une telle machine, ajouter `-e ansible_become_exe=sudo.ws` :

```bash
python -m ansible.cli.adhoc minecraft -m ping --ask-become-pass -e ansible_become_exe=sudo.ws
```

### Depuis la machine cible elle-même

Copier le repo sur la machine, y refaire l'étape 1, puis utiliser l'inventaire local :

```bash
python -m ansible.cli.playbook -i inventory/local.yml site.yml --ask-become-pass
```

## 4. Utiliser le serveur

Sur la machine (`ssh basile@IP`) :

```bash
cd /opt/minecraft
sudo docker compose ps                  # état des conteneurs
sudo docker compose logs -f mc          # logs (attendre la ligne "Done" au premier démarrage)
sudo docker compose exec mc rcon-cli    # console Minecraft
sudo docker compose restart mc          # redémarrer le serveur
```

Dans Minecraft Java : Multijoueur → Ajouter un serveur → IP de la machine.
Pour jouer depuis Internet, rediriger le port TCP **25565** de la box vers la machine.

### Whitelist web

Les amis ajoutent eux-mêmes leur pseudo sur `https://<web_hostname>` (`web_hostname` dans `group_vars/all.yml`).

- Rediriger les ports TCP **80 et 443** de la box vers la machine : Caddy en a besoin pour obtenir son certificat Let's Encrypt
  (il le renouvelle seul, et le garde dans le volume `caddy_data`).
- Le mot de passe, unique et aléatoire (12 caractères), est écrit dans `/opt/minecraft/.env` au premier déploiement.
  Pour le lire et le donner aux amis :

```bash
sudo grep WHITELIST_PASSWORD /opt/minecraft/.env
```

La page est publique, mais sans le mot de passe elle ne fait rien. Il n'y a ni session ni cookie : le mot de passe est
renvoyé et vérifié à chaque envoi, et recharger la page l'efface. Le script ne sait faire qu'une chose, `whitelist add <pseudo>`
(en RCON, sur le réseau interne), après avoir vérifié que le pseudo fait 3 à 16 caractères parmi `A-Za-z0-9_`.
Après 5 mots de passe faux en 10 minutes, l'IP est bloquée le temps de la fenêtre. Les ajouts sont gardés au redémarrage
(`EXISTING_WHITELIST_FILE: MERGE`). Le service refuse de démarrer sans mot de passe d'au moins 12 caractères (pas de valeur par défaut) : en local, ajouter
`WHITELIST_PASSWORD=...` dans `server/.env`. Pour changer le mot de passe : modifier la ligne dans `.env`, puis
`sudo docker compose up -d whitelist`. Les ajouts sont visibles avec `sudo docker compose logs whitelist`.

Les données (monde, plugins) sont dans `/opt/minecraft/data`.
Les sauvegardes sont dans `/opt/minecraft/backups` (toutes les 6 h, 7 jours conservés).

## Tester le serveur en local (Linux avec Docker)

```bash
cd server
printf 'MC_VERSION=26.3\nMC_LINE=26.3\nISOHYPSE_VERSION=0.2.2\nLSS_VERSION=0.20.0\nOREBFUSCATOR_VERSION=5.6.2
' > .env   # mêmes valeurs que group_vars/all.yml
docker compose up -d mc       # seulement le serveur, sans le service de sauvegarde
docker compose logs -f mc     # attendre "Done", puis se connecter sur localhost
docker compose down
```

Mets ton pseudo dans `OPS` et `WHITELIST` avant, sinon la whitelist te refuse.

## Sécurité

Appliqué par le rôle `base` :

- **SSH** : seul `admin_user` peut se connecter, par clé uniquement (pas de mot de passe, pas de root).
  Les clés viennent de `https://github.com/<admin_github_user>.keys` et/ou de `admin_ssh_public_keys`.
  Le playbook refuse de s'exécuter si aucune clé n'est configurée, pour ne pas te verrouiller dehors.
- **Pare-feu (ufw)** : tout est fermé en entrée sauf SSH (limité en débit), le port Minecraft et les ports 80/443 de la page de whitelist.
- **fail2ban** et **mises à jour de sécurité automatiques** activés.
- **sudo sans mot de passe** pour `admin_user` : protège ta clé privée avec une passphrase.
- **Veille du capot désactivée** (utile si la machine est un portable).

### Mot de passe RCON

RCON permet d'envoyer des commandes au serveur ; le service `backup` l'utilise pour figer
le monde pendant une sauvegarde. `mc` et `backup` partagent donc le même mot de passe (`RCON_PASSWORD`) :

| Contexte | Mot de passe |
|---|---|
| Déployé par Ansible | Aléatoire (32 caractères), écrit dans `/opt/minecraft/.env` au premier déploiement, jamais dans git |
| Test en local | `dev` (valeur par défaut du compose, aucun fichier à créer) |

Une valeur en clair comme `dev` n'est acceptable **que parce que le port RCON (25575) n'est pas publié** :
il n'est joignable que par les conteneurs du même compose.
**Ne jamais ajouter `25575` dans `ports:`** sans avoir d'abord défini un vrai mot de passe.
Docker contourne `ufw` pour les ports publiés : seuls ceux listés dans `ports:` sont exposés.

Aucun secret n'est stocké dans le dépôt. Si un vrai secret devient nécessaire
(par exemple une clé CurseForge), le chiffrer avec `ansible-vault` avant de le commiter.

## Notes

- `mc_uid` (`group_vars/all.yml`) doit correspondre à `UID`/`GID` dans `server/docker-compose.yml`,
  sinon le conteneur ne peut pas écrire dans `data/`.
- `mc_port` doit correspondre au port publié dans le compose.
- Le dépôt apt de Docker doit exister pour ta version d'Ubuntu ; si l'étape `docker` échoue sur ce point,
  utiliser une version LTS plus ancienne.
