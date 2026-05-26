import sys, os, requests, socketio, pyqtgraph as pg
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, 
    QDialog, QMessageBox, QLabel, QInputDialog, QComboBox, 
    QFrame, QDoubleSpinBox, QLineEdit
)
from PySide6.QtCore import Qt, QTimer, Slot, QObject, Signal
from PySide6.QtGui import QColor

API_URL = "https://recharge.cielnewton.fr/api"
ADMIN_CREDENTIALS = {"email": "", "password": ""}
api = requests.Session()

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line:
                k, v = line.split("=", 1)
                ADMIN_CREDENTIALS[k.strip()] = v.strip().strip('"')

def format_api_date(date_str):
    if not date_str: return ""
    try: return datetime.fromisoformat(date_str.replace('Z', '+00:00')).strftime('%m-%d - %H:%M')
    except: return date_str

class SocketSignals(QObject):
    update_ui = Signal(str, dict)

class UserDetailsDialog(QDialog):
    def __init__(self, user_id, username, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Profil : {username}"); self.resize(550, 600)
        layout = QVBoxLayout(self)
        
        self.info_card = QFrame()
        self.info_card.setStyleSheet("background-color: #2a2a30; padding: 2px;")
        card_lay = QVBoxLayout(self.info_card)
        
        self.lbl_email, self.lbl_solde, self.lbl_inscrit = QLabel("📧 Email: ..."), QLabel("💰 Solde: ..."), QLabel("📅 Inscrit: ...")
        for w in [QLabel(f"<h2>{username}</h2>"), self.lbl_email, self.lbl_solde, self.lbl_inscrit, QLabel("🔑 <b>Mot de passe:</b> Haché en BDD")]:
            card_lay.addWidget(w)
        layout.addWidget(self.info_card)
        
        layout.addWidget(QLabel("<b>Historique des transactions</b>"))
        self.trans_table = QTableWidget(0, 3)
        self.trans_table.setHorizontalHeaderLabels(["Date", "Description", "Montant"])
        self.trans_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.trans_table.verticalHeader().setVisible(False); layout.addWidget(self.trans_table)
        
        btn_close = QPushButton("Fermer"); btn_close.clicked.connect(self.accept); layout.addWidget(btn_close)
        
        try:
            res = api.get(f"{API_URL}/auth/users/{user_id}/history").json()
            user = res.get('user', {})
            history = res.get('transactions') or res.get('history') or []

            self.lbl_email.setText(f"📧 <b>Email:</b> {user.get('email', 'N/A')}")
            self.lbl_solde.setText(f"💰 {float(user.get('balance', 0)):.2f} €")
            if user.get('created_at'): self.lbl_inscrit.setText(f"📅 <b>Inscrit le:</b> {format_api_date(user.get('created_at'))}")

            self.trans_table.setRowCount(len(history))
            for i, t in enumerate(history):
                d = t.get('created_at') or t.get('start_time') or ""
                desc = t.get('description') or f"Charge Prise {t.get('plug_id')} ({t.get('energy_kwh', 0):.3f} kWh)"
                cost = float(t.get('amount') or t.get('cost') or 0.0)
                
                self.trans_table.setItem(i, 0, QTableWidgetItem(format_api_date(d)))
                self.trans_table.setItem(i, 1, QTableWidgetItem(desc))
                item_cost = QTableWidgetItem(f"{cost:+.2f}€")
                item_cost.setForeground(QColor("#2ecc71" if cost >= 0 else "#e74c3c"))
                self.trans_table.setItem(i, 2, item_cost)
        except: pass

class TabPrises(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = SocketSignals(); self.signals.update_ui.connect(self.update_row_ui)
        
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Prise", "Statut & Session", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False); layout.addWidget(self.table)

        btns = QHBoxLayout()
        btn_add, btn_prov = QPushButton("➕ Ajouter une prise"), QPushButton("🚀 Config. Initiale (Local)")
        btn_prov.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        btn_add.clicked.connect(self.add_prise); btn_prov.clicked.connect(self.provision_local_plug)
        btns.addWidget(btn_add); btns.addWidget(btn_prov); layout.addLayout(btns)

        self.sio = socketio.Client()
        self.sio.on('power_update', lambda d: self.signals.update_ui.emit(str(d['plugId']), {'power': d['power']}))
        self.sio.on('live_consumption', lambda d: self.signals.update_ui.emit(str(d['plugId']), {'energyWh': d['energyWh']}))
        self.sio.on('status_update', lambda d: self.signals.update_ui.emit(str(d['plugId']), d))
        try: self.sio.connect(API_URL.replace('/api', ''), socketio_path='/api/socket.io', transports=['websocket'])
        except: pass

        self.timer = QTimer(self); self.timer.timeout.connect(self.load_data); self.timer.start(5000); self.load_data()

    def provision_local_plug(self):
        dlg = QDialog(self); lay = QVBoxLayout(dlg); fields = {}
        config_list = [
            ("ssid", "Nom du Wi-Fi (SSID)", False), ("wifi_pass", "Mot de passe Wi-Fi", True),
            ("mqtt", "Serveur MQTT", False), ("mqtt_user", "Utilisateur MQTT", False), ("mqtt_pass", "Mot de passe MQTT", True)
        ]
        for key, placeholder, is_pwd in config_list:
            edit = QLineEdit(); edit.setPlaceholderText(placeholder)
            if is_pwd: edit.setEchoMode(QLineEdit.Password)
            lay.addWidget(edit); fields[key] = edit
            
        btn = QPushButton("🚀 Envoyer"); btn.clicked.connect(dlg.accept); lay.addWidget(btn)

        if dlg.exec() == QDialog.Accepted:
            try:
                mqtt_cfg = {"server": fields["mqtt"].text(), "enable": True}
                if fields["mqtt_user"].text(): mqtt_cfg["user"] = fields["mqtt_user"].text()
                if fields["mqtt_pass"].text(): mqtt_cfg["pass"] = fields["mqtt_pass"].text()
                requests.post("http://192.168.33.1/rpc/Mqtt.SetConfig", json={"config": mqtt_cfg}, timeout=2)
                requests.post("http://192.168.33.1/rpc/Wifi.SetConfig", json={"config": {"sta1": {"ssid": fields["ssid"].text(), "pass": fields["wifi_pass"].text(), "enable": True}}}, timeout=2)
                QMessageBox.information(self, "Succès", "Configuration envoyée !")
            except: QMessageBox.critical(self, "Erreur", "Connexion à la prise échouée.")

    def load_data(self):
        try:
            res = api.get(f"{API_URL}/plugs").json()
            existing_ids = {str(p['id']) for p in res}
            
            for p in res:
                pid = str(p['id'])
                if self.find_row(pid) is None:
                    row = self.table.rowCount(); self.table.insertRow(row)
                    item = QTableWidgetItem(pid); item.setData(Qt.UserRole, p)
                    self.table.setItem(row, 0, item); self.table.setItem(row, 1, QTableWidgetItem("..."))
                    
                    act = QWidget(); lay = QHBoxLayout(act); lay.setContentsMargins(4, 2, 4, 2); lay.setSpacing(6)
                    b1, b2, b3, b4 = QPushButton("QR"), QPushButton("🔧"), QPushButton("⚙️"), QPushButton("🛑")
                    b4.setStyleSheet("background:#c0392b; color: white;"); b4.hide()
                    
                    b1.clicked.connect(lambda _, x=pid: self.show_qr(x))
                    b2.clicked.connect(lambda _, x=pid: api.post(f"{API_URL}/plugs/{x}/maintenance"))
                    b3.clicked.connect(lambda _, x=pid: self.set_limit(x))
                    b4.clicked.connect(lambda _, x=pid: api.post(f"{API_URL}/plugs/{x}/force-stop"))
                    
                    for b in [b1, b2, b3, b4]: lay.addWidget(b)
                    self.table.setCellWidget(row, 2, act)
                self.update_row_ui(pid, p)

            for r in reversed(range(self.table.rowCount())):
                if self.table.item(r, 0).text() not in existing_ids: self.table.removeRow(r)
        except: pass

    def find_row(self, pid):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == pid: return r
        return None

    @Slot(str, dict)
    def update_row_ui(self, pid, data):
        row = self.find_row(pid)
        if row is None: return
        item = self.table.item(row, 0); curr = item.data(Qt.UserRole) or {}; curr.update(data); item.setData(Qt.UserRole, curr)
        status, state = curr.get('status', 'libre'), curr.get('state', False)
        elec = "⚡ ON" if state else "OFF"

        if status == "occupied":
            txt, color = f"👤 {curr.get('username', 'Inconnu')} ({elec}) | ⚡ {float(curr.get('power', curr.get('powerW', 0))):.0f}W", "#f39c12"
        elif status == "hs": txt, color = "🔧 Maintenance (Hors Service)", "#e74c3c"
        else: txt, color = f"Libre ({elec})", "#2ecc71"

        self.table.item(row, 1).setText(txt); self.table.item(row, 1).setForeground(QColor(color))
        self.table.cellWidget(row, 2).layout().itemAt(3).widget().setVisible(status == "occupied")

    def set_limit(self, pid):
        val, ok = QInputDialog.getInt(self, "Limite", "Watts max :", 2500, 0, 5000)
        if ok: api.post(f"{API_URL}/plugs/{pid}/configure", json={"powerLimit": val})

    def show_qr(self, pid):
        dlg = QDialog(self); lay = QVBoxLayout(dlg); lab = QLabel()
        from PySide6.QtGui import QPixmap
        px = QPixmap(); px.loadFromData(api.get(f"{API_URL}/plugs/{pid}/qrcode").content)
        lab.setPixmap(px.scaled(250, 250)); lay.addWidget(lab); dlg.exec()

    def add_prise(self):
        nom, ok = QInputDialog.getText(self, "Ajouter", "ID prise :")
        if ok and nom: api.post(f"{API_URL}/plugs", json={"plugId": nom})

class TabConso(QWidget):
    def __init__(self):
        super().__init__()
        self.history_vals, self.history_dates = [], []
        layout = QVBoxLayout(self)
        self.sel = QComboBox(); self.sel.currentIndexChanged.connect(self.load_history)
        layout.addWidget(QLabel("Consommation par utilisateur :")); layout.addWidget(self.sel)
        
        self.graph = pg.PlotWidget(); self.graph.setBackground('#2a2a30')
        self.graph.showGrid(x=True, y=True, alpha=0.3); self.graph.setLabel('left', "Consommation", units="Wh")
        layout.addWidget(self.graph)
        
        self.t_live = QTimer(self); self.t_live.timeout.connect(self.update_live); self.t_live.start(2000)
        self.t_users = QTimer(self); self.t_users.timeout.connect(self.load_users); self.t_users.start(10000)
        self.load_users()
    
    def load_users(self):
        try:
            res = api.get(f"{API_URL}/auth/users").json(); cur = self.sel.currentData()
            self.sel.blockSignals(True); self.sel.clear()
            for u in [x for x in res if x['username'] != 'Admin']: self.sel.addItem(u['username'], u['id'])
            if cur:
                idx = self.sel.findData(cur); self.sel.setCurrentIndex(idx if idx >= 0 else 0)
            self.sel.blockSignals(False)
        except: pass

    def load_history(self):
        uid = self.sel.currentData()
        if not uid: return
        try:
            res = api.get(f"{API_URL}/auth/users/{uid}/history").json()
            data = sorted(res.get('history', []), key=lambda x: x.get('start_time', ''))
            self.history_vals = [float(h.get("energy_kwh") or 0) * 1000 for h in data]
            self.history_dates = [format_api_date(h.get('start_time') or h.get('created_at')) for h in data]
            self.update_live()
        except: pass

    def update_live(self):
        uid = self.sel.currentData()
        if not uid: return
        try:
            res = api.get(f"{API_URL}/plugs").json(); live_val, active = 0, False
            for p in res:
                if str(p.get('current_session', {}).get('user_id')) == str(uid):
                    live_val, active = float(p.get('energyWh') or 0), True; break
            vals, dates = list(self.history_vals), list(self.history_dates)
            if active: vals.append(live_val); dates.append(datetime.now().strftime('%m-%d - %H:%M'))
            self.graph.clear()
            if vals:
                self.graph.getAxis('bottom').setTicks([[(i, dates[i]) for i in range(0, len(dates), max(1, len(dates)//5))]])
                self.graph.plot(list(range(len(vals))), vals, pen=pg.mkPen('#2ecc71', width=2))
        except: pass

class TabUsers(QWidget):
    def __init__(self):
        super().__init__()
        self.users_data = {}
        layout = QVBoxLayout(self)
        self.tableau = QTableWidget(0, 3)
        self.tableau.setHorizontalHeaderLabels(["Utilisateurs", "Solde (€)", "Détails"])
        self.tableau.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents); layout.addWidget(self.tableau)
        
        btns = QHBoxLayout()
        for name, color, cb in zip(["➕ Nouveau", "✏️ Modifier", "🗑️ Supprimer"], ["#27ae60", "#e67e22", "#c0392b"], [self.add, self.edit, self.delete]):
            btn = QPushButton(name); btn.setStyleSheet(f"background-color: {color}; color: white;"); btn.clicked.connect(cb); btns.addWidget(btn)
        layout.addLayout(btns)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(2000); self.refresh()

    def refresh(self):
        try:
            res = api.get(f"{API_URL}/auth/users").json(); users = [u for u in res if u['username'] != 'Admin']
            if len(users) != self.tableau.rowCount():
                self.tableau.setRowCount(len(users))
                for i, u in enumerate(users):
                    self.tableau.setItem(i, 0, QTableWidgetItem(u['username']))
                    self.tableau.setItem(i, 1, QTableWidgetItem(f"{float(u['balance']):.2f} €"))
                    btn = QPushButton("Détails"); btn.setStyleSheet("padding: 2px 10px; font-weight: normal;")
                    btn.clicked.connect(lambda _, uid=u['id'], name=u['username']: UserDetailsDialog(uid, name, self).exec())
                    self.tableau.setCellWidget(i, 2, btn)
            else:
                for i, u in enumerate(users): self.tableau.item(i, 1).setText(f"{float(u['balance']):.2f} €")
            self.users_data = {i: u for i, u in enumerate(users)}
        except: pass

    def add(self):
        dlg = QDialog(self); lay = QVBoxLayout(dlg); fields = [QLineEdit() for _ in range(5)]
        for f, p in zip(fields, ["Prénom", "Nom", "Email", "Mot de passe", "Argent (€)"]):
            f.setPlaceholderText(p); f.setEchoMode(QLineEdit.Password) if p == "Mot de passe" else None; lay.addWidget(f)
        btn = QPushButton("Créer"); btn.clicked.connect(dlg.accept); lay.addWidget(btn)
        if dlg.exec() == QDialog.Accepted:
            payload = {"username": f"{fields[0].text()} {fields[1].text()}", "email": fields[2].text(), "password": fields[3].text(), "balance": float(fields[4].text() or 0)}
            api.post(f"{API_URL}/auth/register", json=payload); self.refresh()

    def edit(self):
        row = self.tableau.currentRow()
        if row < 0 or row not in self.users_data: return
        u = self.users_data[row]; dlg = QDialog(self); dlg.setWindowTitle("Modifier"); lay = QVBoxLayout(dlg)
        
        # Découpage automatique du username ("Prénom Nom")
        parts = u['username'].split(" ", 1)
        prenom_val = parts[0] if len(parts) > 0 else ""
        nom_val = parts[1] if len(parts) > 1 else ""
        email_val = u.get('email', '')

        # Si l'email est manquant dans l'index global, on va chercher l'info complète sur l'API
        if not email_val:
            try:
                user_res = api.get(f"{API_URL}/auth/users/{u['id']}/history").json()
                email_val = user_res.get('user', {}).get('email', '')
            except: pass

        prenom, nom, mail = QLineEdit(prenom_val), QLineEdit(nom_val), QLineEdit(email_val)
        arg, pwd = QDoubleSpinBox(), QLineEdit()
        
        mail.setPlaceholderText("exemple@gmail.com")
        arg.setRange(-1000, 10000); arg.setValue(float(u.get('balance', 0)))
        pwd.setPlaceholderText("Laisser vide pour ne pas changer"); pwd.setEchoMode(QLineEdit.Password)
        
        # Ajout des composants de manière ordonnée et explicite
        components = [("Prénom :", prenom), ("Nom :", nom), ("Email / Gmail :", mail), ("Solde (€) :", arg), ("Mot de passe :", pwd)]
        for txt, w in components:
            lay.addWidget(QLabel(f"<b>{txt}</b>")); lay.addWidget(w)
            
        btn = QPushButton("Enregistrer"); btn.clicked.connect(dlg.accept); lay.addWidget(btn)
        if dlg.exec() == QDialog.Accepted:
            payload = {"username": f"{prenom.text().strip()} {nom.text().strip()}".strip(), "email": mail.text().strip(), "balance": float(arg.value())}
            if pwd.text().strip(): payload["password"] = pwd.text().strip()
            api.put(f"{API_URL}/auth/users/{u['id']}", json=payload); self.refresh()

    def delete(self):
        row = self.tableau.currentRow()
        if row >= 0 and row in self.users_data:
            if QMessageBox.question(self, "Supprimer", "Supprimer ce compte ?") == QMessageBox.Yes:
                api.delete(f"{API_URL}/auth/users/{self.users_data[row]['id']}"); self.refresh()

class TabMaintenance(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.tableau = QTableWidget(0, 2)
        self.tableau.setHorizontalHeaderLabels(["Prise", "Alerte"])
        self.tableau.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableau.verticalHeader().setVisible(False); layout.addWidget(self.tableau)
        self.timer = QTimer(self); self.timer.timeout.connect(self.fetch_alerts); self.timer.start(10000); self.fetch_alerts()

    def fetch_alerts(self):
        try:
            res = api.get(f"{API_URL}/plugs/alerts").json().get('devices', [])
            self.tableau.setRowCount(0)
            for alert in res:
                row = self.tableau.rowCount(); self.tableau.insertRow(row)
                self.tableau.setItem(row, 0, QTableWidgetItem(str(alert.get('id', 'N/A'))))
                self.tableau.setItem(row, 1, QTableWidgetItem(f"{alert.get('alert_reason', 'Erreur')}"))
        except: pass

class Dashboard(QTabWidget):    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard Admin"); self.resize(848, 480)
        self.setDocumentMode(True); self.tabBar().setExpanding(True)
        self.addTab(TabPrises(), "🔌 Prises"); self.addTab(TabConso(), "📈 Consommation")
        self.addTab(TabUsers(), "👤 Utilisateurs"); self.addTab(TabMaintenance(), "🛠️ Maintenance")

if __name__ == '__main__':
    app = QApplication(sys.argv)    
    app.setStyleSheet("""
        QWidget { background: #1c1c21; color: white; }
        QTableWidget { background: #2a2a30; border: none; }
        QPushButton { background: #287aad; padding: 6px; font-weight: bold; border-radius: 4px; }
        QTabBar::tab { background: #2b2b33; padding: 8px; }
        QTabBar::tab:selected { background: #1c1c21; border-bottom: 3px solid #287aad; }    
    """)
    try:
        res = api.post(f"{API_URL}/auth/login", json=ADMIN_CREDENTIALS, timeout=5)
        if res.status_code == 200:
            api.headers.update({"Authorization": f"Bearer {res.json().get('token')}"})
            win = Dashboard(); win.show(); sys.exit(app.exec())
    except: pass