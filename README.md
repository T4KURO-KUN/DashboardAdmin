# ⚡ Guide d'Installation Complet : Dashboard d'Administration

Ce guide officiel est destiné aux administrateurs et développeurs du système de supervision des bornes de recharge. Il détaille pas à pas la configuration de l'environnement, la gestion des dépendances et le déploiement du tableau de bord d'administration cross-platform écrit en **Python 3** avec **PySide6**.

---

## 📋 1. Prérequis Système & Dépendances Globales

L'application requiert **Python 3.10** (ou une version supérieure) ainsi que l'accès au gestionnaire de paquets de votre système d'exploitation pour charger les composants graphiques natifs et les liaisons Qt6 (X11 / Wayland / Windows).

---

### 🪟 Microsoft Windows

1. Téléchargez l’installateur stable depuis : https://www.python.org/downloads/
2. Durant l’installation, cochez impérativement :

```text
[X] Add Python.exe to PATH
````

Sinon les commandes `python` et `pip` seront introuvables.

---

### 🐧 Distributions Linux

#### Debian / Ubuntu / Linux Mint / Pop!_OS

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-pyside6 libegl1 -y
```

#### Fedora / RHEL / CentOS

```bash
sudo dnf upgrade --refresh
sudo dnf install python3 python3-pip python3-virtualenv -y
```

#### Arch Linux / Manjaro / EndeavourOS

```bash
sudo pacman -Syu python python-pip python-virtualenv --noconfirm
```

---

## 🔐 2. Configuration du Fichier d'Environnement (.env)

Le programme ne stocke jamais d’identifiants sensibles directement dans le code source.

### Étapes

1. À la racine du projet (même dossier que `DashboardAdmin.py`) :

```bash
touch .env
```

2. Éditez le fichier :

```env
# Identifiants administrateur
email="votremail@gmail.com"
password="votre_mot_de_passe"
```

> 🛑 Ne poussez jamais `.env` sur GitHub/GitLab.
> Ajoutez-le dans `.gitignore`.

---

## 🛠 3. Isolation de l'Environnement (Sandbox)

### Aller dans le dossier du projet

```bash
cd /chemin/vers/votre/dossier_projet
```

### Créer l'environnement virtuel

```bash
python3 -m venv venv
```

### Activer l’environnement

#### Windows (CMD)

```bash
venv\Scripts\activate
```

#### Windows (PowerShell)

```powershell
.\venv\Scripts\Activate.ps1
```

#### Linux

```bash
source venv/bin/activate
```

Une fois activé, `(venv)` doit apparaître dans le terminal.

---

## 📦 4. Dépendances & Librairies

```bash
pip install --upgrade pip
pip install requests python-socketio pyqtgraph PySide6 python-dotenv
```

### Rôle des librairies

* **PySide6** : Interface graphique Qt.
* **requests** : Communication HTTP avec l’API REST.
* **python-socketio** : Flux temps réel bidirectionnel.
* **pyqtgraph** : Graphiques temps réel haute performance.
* **python-dotenv** : Chargement automatique du fichier `.env`.

---

## 🚀 5. Lancement de la Tour de Contrôle

```bash
python DashboardAdmin.py
```

### Fonctionnalités disponibles

* **Prises** : suivi temps réel, provisionnement, arrêt d’urgence (*Force Stop*).
* **Consommation** : graphique dynamique via Socket.IO.
* **Clients** : gestion CRUD utilisateurs et rechargement des portefeuilles.
* **Maintenance** : surveillance réseau avec *Heartbeat* toutes les 10 secondes.
