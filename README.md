# ⚡ Guide d'Installation Complet : Dashboard d'Administration

Ce guide officiel est destiné aux administrateurs et développeurs du système de supervision des bornes de recharge. Il détaille pas à pas la configuration de l'environnement, la gestion des dépendances et le déploiement du tableau de bord d'administration cross-platform écrit en **Python 3** avec **PySide6**.

> 💡 Ce programme a été conçu pour fonctionner sur les systèmes basé sur unix comme linux et mac os

## 📋 1. Prérequis Système & Dépendances Globales

L'application requiert **Python 3.10** (ou une version supérieure) ainsi que l'accès au gestionnaire de paquets de votre système d'exploitation pour charger les composants graphiques natifs et les liaisons Qt6 (X11 / Wayland).

#### Debian / Ubuntu / Linux Mint

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
```

#### Fedora / RHEL / CentOS

```bash
sudo dnf upgrade --refresh -y
sudo dnf install python3 python3-pip -y
```

#### Arch Linux / EndeavourOS

```bash
sudo pacman -Syu python python-pip --noconfirm
```

## 🔐 2. Configuration du Fichier d'Environnement (`.env`)

Le programme ne stocke jamais d’identifiants sensibles directement dans le code source.

### Étapes

1. À la racine du projet (même dossier que `DashboardAdmin.py`), créez le fichier :
```bash
cp example.env .env
```

2. Éditez le fichier `.env` avec vos identifiants :
```env
email="votremail@gmail.com"
password="votre_mot_de_passe"
```
> 🛑 **Sécurité :** Ne poussez jamais le fichier `.env` sur GitHub/GitLab. Assurez-vous qu'il est présent dans votre fichier `.gitignore`.

## 🛠 3. Configuration de l'Environnement & Automatisation

### Aller dans le dossier du projet
```bash
cd /chemin/vers/DashboardAdmin/
```

### À la racine de votre projet, créez les trois fichiers suivants :
#### 📄 `requirements.txt`

```text
requests
python-socketio
pyqtgraph
PySide6
python-dotenv
```

#### 📜 `install.sh`

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 📜 `start.sh`

```bash
source venv/bin/activate
python DashboardAdmin.py
```

> 💡 **Note pour Linux :** N'oubliez pas de rendre vos scripts exécutables avec la commande :
> `chmod +x install.sh start.sh`


## 📦 4. Dépendances & Librairies

Pour installer les dépendances dans l'environnement virtuel, lancez simplement :

```bash
./install.sh
```

### Rôle des librairies installées

* **PySide6** : Interface graphique officielle Qt6 pour Python.
* **requests** : Communication HTTP avec l’API REST.
* **python-socketio** : Flux temps réel bidirectionnel.
* **pyqtgraph** : Graphiques temps réel haute performance.
* **python-dotenv** : Chargement automatique du fichier `.env`.


## 🚀 5. Lancement de la Tour de Contrôle

Pour démarrer l'application, exécutez le script de lancement :

```bash
./start.sh
```

### Fonctionnalités disponibles

* **Prises** : Suivi temps réel, provisionnement, arrêt d’urgence (*Force Stop*).
* **Consommation** : Graphique dynamique via Socket.IO.
* **Clients** : Gestion CRUD utilisateurs et rechargement des portefeuilles.
* **Maintenance** : Suivi de l'état de connexion des bornes (mise à jour toutes les 10 secondes).
