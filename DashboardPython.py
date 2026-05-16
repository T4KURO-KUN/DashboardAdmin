import sys
import os
import requests
import socketio
from PySide6.QtWidgets import (QApplication, QMainWindow, QTableWidget, QTableWidgetItem, 
                             QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QHeaderView, 
                             QInputDialog, QMessageBox, QTabWidget, QLabel, QComboBox)
from PySide6.QtCore import Qt, Signal, QObject, Slot, QTimer
from PySide6.QtGui import QColor, QFont, QIcon

# --- CONFIGURATION ---
API_URL = "https://recharge.cielnewton.fr/api"

# Chargement des identifiants depuis le .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
ADMIN_CREDENTIALS = {"email": "", "password": ""}

try:
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    parts = line.split("=", 1)
                    key = parts[0].strip()
                    val = parts[1].strip().strip("\"")
                    if key in ADMIN_CREDENTIALS:
                        ADMIN_CREDENTIALS[key] = val
except Exception as e:
    print(f"Erreur lecture .env : {e}")

# --- COMMUNICATION THREAD-SAFE ---
class SocketSignals(QObject):
    update_ui = Signal(str, dict)

# --- 01. ONGLET PRISES (TabPrises) ---
class TabPrises(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Signaux pour mettre à jour l'UI depuis le thread WebSocket
        self.signals = SocketSignals()
        self.signals.update_ui.connect(self.update_row_ui)

        self.init_ui()
        self.init_socket()
        self.load_prises()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Barre d'outils
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("➕ Ajouter une prise")
        self.btn_add.clicked.connect(self.add_prise_dialog)
        
        self.btn_refresh = QPushButton("🔄 Actualiser")
        self.btn_refresh.clicked.connect(self.load_prises)
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_refresh)
        layout.addLayout(btn_layout)

        # Table des prises
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Identifiant", "État / Status / Conso", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

    def load_prises(self):
        try:
            res = requests.get(f"{API_URL}/plugs", headers=self.headers, timeout=5)
            if res.status_code == 200:
                self.table.setRowCount(0)
                for prise in res.json():
                    self.add_row_to_table(prise)
        except Exception as e:
            print(f"Erreur chargement prises : {e}")

    def add_row_to_table(self, prise):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Stockage de l'objet data complet dans l'item de la 1ère colonne
        item_id = QTableWidgetItem(prise['id'])
        prise['energyWh'] = prise.get('energyWh', 0)
        item_id.setData(Qt.UserRole, prise)
        self.table.setItem(row, 0, item_id)
        
        # Cellule d'état
        self.table.setItem(row, 1, QTableWidgetItem("Initialisation..."))

        # Widget d'actions
        actions_widget = QWidget()
        l = QHBoxLayout(actions_widget)
        l.setContentsMargins(4, 2, 4, 2)
        
        btn_maint = QPushButton("🔧 Maint.")
        btn_maint.clicked.connect(lambda: self.toggle_maintenance(prise['id']))
        
        btn_stop = QPushButton("🛑 Stop")
        btn_stop.setStyleSheet("background-color: #c0392b;")
        btn_stop.clicked.connect(lambda: self.force_stop(prise['id']))
        
        l.addWidget(btn_maint)
        l.addWidget(btn_stop)
        self.table.setCellWidget(row, 2, actions_widget)

        self.update_row_ui(prise['id'], prise)

    @Slot(str, dict)
    def update_row_ui(self, plug_id, data):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == plug_id:
                curr = item.data(Qt.UserRole)
                curr.update(data)
                item.setData(Qt.UserRole, curr)

                # Sécurisation des variables (évite les NoneType)
                status = curr.get('status', 'libre') or 'libre'
                state = curr.get('state', False)
                power = curr.get('power') or 0
                energy = curr.get('energyWh') or 0
                user = curr.get('username', '')

                # Reset de l'énergie si libre
                if status in ['libre', 'hs']:
                    energy = 0
                    curr['energyWh'] = 0

                # Construction de la chaîne d'affichage
                state_txt = "⚡ ALLUMÉE" if state else "ÉTEINTE"
                status_txt = f"Occupée par {user}" if (status == "occupied" and user) else status.upper()
                
                final_txt = f"{status_txt} ({state_txt})"
                if power > 0:
                    final_txt += f" - {power}W"
                
                if status == "occupied" and energy > 0:
                    final_txt += f" | 📈 {float(energy):.1f} Wh"

                # Mise à jour graphique
                cell = self.table.item(row, 1)
                cell.setText(final_txt)
                cell.setForeground(QColor("#2ecc71") if state else QColor("#95a5a6"))
                
                # Visibilité du bouton Stop
                actions_widget = self.table.cellWidget(row, 2)
                if actions_widget:
                    btn_stop = actions_widget.layout().itemAt(1).widget()
                    btn_stop.setVisible(status == "occupied")
                break

    def init_socket(self):
        self.sio = socketio.Client()
        
        @self.sio.on('power_update')
        def on_p(d): self.signals.update_ui.emit(d['plugId'], {'power': d['power']})
        
        @self.sio.on('state_update')
        def on_s(d): self.signals.update_ui.emit(d['plugId'], {'state': d['state']})
        
        @self.sio.on('live_consumption')
        def on_c(d): self.signals.update_ui.emit(d['plugId'], {'energyWh': d['energyWh']})
        
        @self.sio.on('status_update')
        def on_st(d): self.signals.update_ui.emit(d['plugId'], d)

        try:
            self.sio.connect(API_URL.replace('/api', ''), socketio_path='/api/socket.io', transports=['websocket'])
        except:
            print("Connexion WebSocket impossible")

    def toggle_maintenance(self, p_id):
        requests.post(f"{API_URL}/plugs/{p_id}/maintenance", headers=self.headers)

    def force_stop(self, p_id):
        confirm = QMessageBox.question(self, "Action", f"Forcer l'arrêt de {p_id} ?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            requests.post(f"{API_URL}/plugs/{p_id}/force-stop", headers=self.headers)

    def add_prise_dialog(self):
        name, ok = QInputDialog.getText(self, "Nouvelle Prise", "ID de la prise :")
        if ok and name:
            requests.post(f"{API_URL}/plugs", json={"plugId": name}, headers=self.headers)
            self.load_prises()

# --- 02. ONGLET CONSOMMATION & STATISTIQUES (TabConso) ---
class TabConso(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        top_layout = QHBoxLayout()
        self.label_filter = QLabel("🔍 Filtrer l'historique par client :")
        self.combo_users = QComboBox()
        self.combo_users.currentTextChanged.connect(self.filter_changed)
        
        self.btn_refresh = QPushButton("🔄 Recharger")
        self.btn_refresh.clicked.connect(self.load_users_list)
        
        top_layout.addWidget(self.label_filter)
        top_layout.addWidget(self.combo_users)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_refresh)
        layout.addLayout(top_layout)

        self.table_history = QTableWidget(0, 4)
        self.table_history.setHorizontalHeaderLabels(["Prise ID", "Utilisateur", "Consommation (Wh)", "Statut"])
        self.table_history.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_history)
        
        self.load_users_list()

    def load_users_list(self):
        try:
            res = requests.get(f"{API_URL}/users", headers=self.headers, timeout=5)
            if res.status_code == 200:
                self.combo_users.clear()
                self.combo_users.addItem("Tous les utilisateurs")
                for u in res.json():
                    self.combo_users.addItem(u.get('username', ''))
        except Exception as e:
            print(f"Erreur combo utilisateurs : {e}")

    def filter_changed(self, username):
        try:
            url = f"{API_URL}/history" if username == "Tous les utilisateurs" else f"{API_URL}/history?user={username}"
            res = requests.get(url, headers=self.headers, timeout=5)
            if res.status_code == 200:
                self.table_history.setRowCount(0)
                for h in res.json():
                    row = self.table_history.rowCount()
                    self.table_history.insertRow(row)
                    self.table_history.setItem(row, 0, QTableWidgetItem(str(h.get('plugId', ''))))
                    self.table_history.setItem(row, 1, QTableWidgetItem(str(h.get('username', ''))))
                    self.table_history.setItem(row, 2, QTableWidgetItem(f"{float(h.get('energyWh', 0)):.1f} Wh"))
                    self.table_history.setItem(row, 3, QTableWidgetItem(str(h.get('status', 'terminé')).upper()))
        except Exception as e:
            print(f"Erreur historique : {e}")

# --- 03. ONGLET ADMINISTRATION DES UTILISATEURS / CRM (TabUsers) ---
class TabUsers(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.init_ui()
        self.load_users()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        top_layout = QHBoxLayout()
        self.btn_add_user = QPushButton("👤 Créer un Utilisateur")
        self.btn_add_user.clicked.connect(self.create_user)
        self.btn_refresh = QPushButton("🔄 Actualiser")
        self.btn_refresh.clicked.connect(self.load_users)
        
        top_layout.addWidget(self.btn_add_user)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_refresh)
        layout.addLayout(top_layout)

        self.table_users = QTableWidget(0, 4)
        self.table_users.setHorizontalHeaderLabels(["Nom d'utilisateur", "Email", "Portefeuille / Solde (€)", "Actions"])
        self.table_users.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_users)

    def load_users(self):
        try:
            res = requests.get(f"{API_URL}/users", headers=self.headers, timeout=5)
            if res.status_code == 200:
                self.table_users.setRowCount(0)
                for u in res.json():
                    row = self.table_users.rowCount()
                    self.table_users.insertRow(row)
                    self.table_users.setItem(row, 0, QTableWidgetItem(u.get('username', '')))
                    self.table_users.setItem(row, 1, QTableWidgetItem(u.get('email', '')))
                    self.table_users.setItem(row, 2, QTableWidgetItem(f"{float(u.get('balance', 0)):.2f} €"))
                    
                    actions_widget = QWidget()
                    l = QHBoxLayout(actions_widget)
                    l.setContentsMargins(4, 2, 4, 2)
                    btn_del = QPushButton("❌ Suppr.")
                    btn_del.setStyleSheet("background-color: #c0392b;")
                    btn_del.clicked.connect(lambda checked=False, uid=u.get('id'): self.delete_user(uid))
                    l.addWidget(btn_del)
                    self.table_users.setCellWidget(row, 3, actions_widget)
        except Exception as e:
            print(f"Erreur CRM : {e}")

    def create_user(self):
        name, ok1 = QInputDialog.getText(self, "Nouveau Client", "Nom d'utilisateur :")
        if ok1 and name:
            email, ok2 = QInputDialog.getText(self, "Nouveau Client", "Email :")
            if ok2 and email:
                requests.post(f"{API_URL}/users", json={"username": name, "email": email}, headers=self.headers)
                self.load_users()

    def delete_user(self, user_id):
        confirm = QMessageBox.question(self, "Action", "Confirmer la suppression du compte client ?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            requests.delete(f"{API_URL}/users/{user_id}", headers=self.headers)
            self.load_users()

# --- 04. ONGLET MONITORING PRÉVENTIF & DIAGNOSTIC (TabMaintenance) ---
class TabMaintenance(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.init_ui()
        
        # Configuration de la surveillance active (Heartbeat toutes les 10 secondes)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_server_health)
        self.timer.start(10000)
        self.check_server_health()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.lbl_status = QLabel("État de la connexion avec l'API : Diagnostic en cours...")
        self.lbl_status.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(self.lbl_status)

        self.table_logs = QTableWidget(0, 3)
        self.table_logs.setHorizontalHeaderLabels(["Date / Heure", "Sévérité", "Description du Dysfonctionnement"])
        self.table_logs.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table_logs)

    def check_server_health(self):
        try:
            res = requests.get(f"{API_URL}/maintenance/health", headers=self.headers, timeout=3)
            if res.status_code == 200:
                self.lbl_status.setText("🟢 SYSTEM NOMINAL — Serveur en ligne")
                self.lbl_status.setStyleSheet("color: #2ecc71;")
                self.load_diagnostic_logs()
            else:
                self.lbl_status.setText(f"🟡 INFRASTRUCTURE INSTABLE (Code {res.status_code})")
                self.lbl_status.setStyleSheet("color: #f1c40f;")
        except requests.exceptions.RequestException:
            self.lbl_status.setText("🔴 SERVEUR DÉCONNECTÉ — Perte de liaison avec la VM")
            self.lbl_status.setStyleSheet("color: #e74c3c;")

    def load_diagnostic_logs(self):
        try:
            res = requests.get(f"{API_URL}/maintenance/logs", headers=self.headers, timeout=3)
            if res.status_code == 200:
                self.table_logs.setRowCount(0)
                for log in res.json():
                    row = self.table_logs.rowCount()
                    self.table_logs.insertRow(row)
                    self.table_logs.setItem(row, 0, QTableWidgetItem(log.get('timestamp', '')))
                    self.table_logs.setItem(row, 1, QTableWidgetItem(log.get('level', 'INFO').upper()))
                    self.table_logs.setItem(row, 2, QTableWidgetItem(log.get('message', '')))
        except Exception as e:
            print(f"Erreur rafraîchissement logs de diagnostic : {e}")

# --- DASHBOARD PRINCIPAL ---
class Dashboard(QTabWidget):
    def __init__(self, token):
        super().__init__()
        self.setWindowTitle("Dashboard Admin Newton")
        self.resize(1280, 720)
        self.setDocumentMode(True)
        self.tabBar().setExpanding(True)
        
        # Ajout des onglets métiers finalisés
        self.addTab(TabPrises(token), "🔌 Prises")
        self.addTab(TabConso(token), "📈 Consommation")
        self.addTab(TabUsers(token), "👤 Utilisateurs")
        self.addTab(TabMaintenance(token), "🛠️ Maintenance")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Style global CSS
    app.setStyleSheet("""
        QWidget { background: #1c1c21; color: white; font-family: 'Segoe UI'; font-size: 13px; }
        QTableWidget { background: #2a2a30; border: none; gridline-color: #3f3f46; selection-background-color: #3d3d45; }
        QHeaderView::section { background: #33333a; padding: 8px; border: 1px solid #1c1c21; font-weight: bold; }
        QPushButton { background: #287aad; padding: 7px 15px; font-weight: bold; border-radius: 4px; border: none; }
        QPushButton:hover { background: #3591c9; }
        QTabBar::tab { background: #2b2b33; padding: 15px; min-width: 180px; border-right: 1px solid #1c1c21; }
        QTabBar::tab:selected { background: #1c1c21; border-bottom: 3px solid #287aad; color: #287aad; }
    """)

    try:
        # Authentification avec la route /auth/login
        res = requests.post(f"{API_URL}/auth/login", json=ADMIN_CREDENTIALS, timeout=5)
        
        if res.status_code == 200:
            token = res.json().get("token")
            if token:
                win = Dashboard(token)
                win.show()
                sys.exit(app.exec())
            else:
                QMessageBox.critical(None, "Erreur", "Token non reçu.")
        else:
            QMessageBox.critical(None, "Erreur Login", f"Accès refusé ({res.status_code})")
            
    except Exception as e:
        QMessageBox.critical(None, "Erreur Serveur", f"Impossible de joindre l'API :\n{e}")