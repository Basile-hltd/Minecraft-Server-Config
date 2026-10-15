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
  config/                  Fichiers copiés dans /data (configs de plugins...)
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
| `ansible/group_vars/all.yml` | `admin_user`, `admin_github_user` (ou `admin_ssh_public_keys`) |
| `server/docker-compose.yml` | `VERSION`, `MEMORY`, `MOTD`, `OPS`, `WHITELIST`, `DIFFICULTY`... |

## 3. Déployer

Vérifier que la machine répond :

```bash
python -m ansible.cli.adhoc minecraft -m ping
```

Simuler (ne modifie rien ; les tâches dépendant de Docker peuvent échouer en simulation, c'est normal) :

```bash
python -m ansible.cli.playbook site.yml --ask-become-pass --check --diff
```

Déployer :

```bash
python -m ansible.cli.playbook site.yml --ask-become-pass
```

`--ask-become-pass` demande le mot de passe `sudo` de la machine. Après le premier déploiement,
`sudo` est sans mot de passe pour `admin_user` et ce flag n'est plus nécessaire.

Le déploiement est idempotent : relance la même commande après chaque modification de config.
Pour ne redéployer que la config du serveur :

```bash
python -m ansible.cli.playbook site.yml --tags minecraft
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
docker compose ps                  # état des conteneurs
docker compose logs -f mc          # logs (attendre la ligne "Done" au premier démarrage)
docker compose exec mc rcon-cli    # console Minecraft
docker compose restart mc          # redémarrer le serveur
```

Dans Minecraft Java : Multijoueur → Ajouter un serveur → IP de la machine.
Pour jouer depuis Internet, rediriger le port TCP **25565** de la box vers la machine.

Les données (monde, plugins) sont dans `/opt/minecraft/data`.
Les sauvegardes sont dans `/opt/minecraft/backups` (toutes les 6 h, 7 jours conservés).

## Tester le serveur en local (Linux avec Docker)

```bash
cd server
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
- **Pare-feu (ufw)** : tout est fermé en entrée sauf SSH (limité en débit) et le port Minecraft.
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
