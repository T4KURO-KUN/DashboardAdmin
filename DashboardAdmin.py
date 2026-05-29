import sys, os, requests, socketio, pyqtgraph as pg
from datetime import datetime
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QDialog, QMessageBox, QLabel, QInputDialog, QComboBox, QFrame, QDoubleSpinBox, QLineEdit, QAbstractItemView
from PySide6.QtCore import Qt, QTimer, Slot, QObject, Signal
from PySide6.QtGui import QColor

API_URL = "https://recharge.cielnewton.fr/api"
SOCKET_URL = "https://recharge.cielnewton.fr"
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
    if not date_str: 
        return "N/A"
    try: 
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('[%d-%m - %H:%M]')
    except (ValueError, AttributeError):
        return str(date_str)

class SocketSignals(QObject):
    update_ui = Signal(str, dict)

class UserDetailsDialog(QDialog):
    def __init__(self, user_id, username, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Profil : {username}")
        self.resize(550, 600)
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
        self.trans_table.verticalHeader().setVisible(False)
        layout.addWidget(self.trans_table)
        
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
        
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
        self.signals = SocketSignals()
        self.signals.update_ui.connect(self.update_row_ui)
        
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Prise", "Statut & Session", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        layout_boutons = QHBoxLayout()
        btn_add = QPushButton("➕ Ajouter une prise")
        btn_prov = QPushButton("🚀 Config. Initiale (Local)")
        btn_prov.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        btn_add.clicked.connect(self.add_prise)
        btn_prov.clicked.connect(self.provision_local_plug)
        layout_boutons.addWidget(btn_add)
        layout_boutons.addWidget(btn_prov)
        layout.addLayout(layout_boutons)

        self.sio = socketio.Client()
        self.sio.on('state_update', lambda data: self.signals.update_ui.emit(str(data.get('plugId')), {'state': data.get('state')}))
        self.sio.on('power_update', lambda data: self.signals.update_ui.emit(str(data.get('plugId')), {'power': data.get('power', 0)}))
        self.sio.on('status_update', lambda data: self.signals.update_ui.emit(str(data.get('plugId')), {'status': data.get('status')}))
        self.sio.on('live_consumption', lambda data: self.signals.update_ui.emit(str(data.get('plugId')), {'energyWh': data.get('energyWh', 0), 'cost': data.get('cost', 0)}))

        try: self.sio.connect(SOCKET_URL, socketio_path='/socket.io', transports=['websocket', 'polling'])
        except: pass

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load_data)
        self.timer.start(5000)
        self.load_data()

    def provision_local_plug(self):
        dialogue = QDialog(self)
        layout_dialogue = QVBoxLayout(dialogue)
        champs = {}
        config_list = [
            ("ssid", "Nom du Wi-Fi (SSID)", False), ("wifi_pass", "Mot de passe Wi-Fi", True),
            ("mqtt", "Serveur MQTT", False), ("mqtt_user", "Utilisateur MQTT", False), ("mqtt_pass", "Mot de passe MQTT", True)
        ]
        for cle, placeholder, est_password in config_list:
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            if est_password: edit.setEchoMode(QLineEdit.Password)
            layout_dialogue.addWidget(edit)
            champs[cle] = edit
            
        btn_envoyer = QPushButton("🚀 Envoyer")
        btn_envoyer.clicked.connect(dialogue.accept)
        layout_dialogue.addWidget(btn_envoyer)

        if dialogue.exec() == QDialog.Accepted:
            try:
                mqtt_cfg = {"server": champs["mqtt"].text(), "enable": True}
                if champs["mqtt_user"].text(): mqtt_cfg["user"] = champs["mqtt_user"].text()
                if champs["mqtt_pass"].text(): mqtt_cfg["pass"] = champs["mqtt_pass"].text()
                requests.post("http://192.168.33.1/rpc/Mqtt.SetConfig", json={"config": mqtt_cfg}, timeout=2)
                requests.post("http://192.168.33.1/rpc/Wifi.SetConfig", json={"config": {"sta1": {"ssid": champs["ssid"].text(), "pass": champs["wifi_pass"].text(), "enable": True}}}, timeout=2)
                QMessageBox.information(self, "Succès", "Configuration envoyée !")
            except: QMessageBox.critical(self, "Erreur", "Connexion à la prise échouée.")

    def load_data(self):
        try:
            reponse = api.get(f"{API_URL}/plugs").json()
            ids_existants = {str(prise.get('id')) for prise in reponse if prise.get('id') is not None}
            
            for prise in reponse:
                id_prise = str(prise.get('id'))
                if id_prise == 'None': continue
                    
                if self.find_row(id_prise) is None:
                    ligne = self.table.rowCount()
                    self.table.insertRow(ligne)
                    
                    item_id = QTableWidgetItem(id_prise)
                    item_id.setData(Qt.UserRole, prise)
                    self.table.setItem(ligne, 0, item_id)
                    
                    item_statut = QTableWidgetItem("...")
                    item_statut.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                    self.table.setItem(ligne, 1, item_statut)
                    
                    widget_actions = QWidget()
                    layout_actions = QHBoxLayout(widget_actions)
                    layout_actions.setContentsMargins(4, 2, 4, 2)
                    layout_actions.setSpacing(6)
                    
                    btn_qr, btn_maint, btn_lim, btn_stop = QPushButton("QR"), QPushButton("🔧"), QPushButton("⚙️"), QPushButton("🛑")
                    btn_stop.setStyleSheet("background:#c0392b; color: white;")
                    btn_stop.hide()
                    
                    btn_qr.clicked.connect(lambda _, x=id_prise: self.show_qr(x))
                    btn_maint.clicked.connect(lambda _, x=id_prise: api.post(f"{API_URL}/plugs/{x}/maintenance"))
                    btn_lim.clicked.connect(lambda _, x=id_prise: self.set_limit(x))
                    btn_stop.clicked.connect(lambda _, x=id_prise: api.post(f"{API_URL}/plugs/{x}/force-stop"))
                    
                    for b in [btn_qr, btn_maint, btn_lim, btn_stop]: layout_actions.addWidget(b)
                    self.table.setCellWidget(ligne, 2, widget_actions)
                    
                self.update_row_ui(id_prise, prise)

            for ligne in reversed(range(self.table.rowCount())):
                if self.table.item(ligne, 0).text() not in ids_existants: self.table.removeRow(ligne)
        except: pass

    def find_row(self, id_prise):
        for ligne in range(self.table.rowCount()):
            if self.table.item(ligne, 0).text() == id_prise: return ligne
        return None

    @Slot(str, dict)
    def update_row_ui(self, id_prise, data):
        ligne = self.find_row(id_prise)
        if ligne is None: return
        
        item_id = self.table.item(ligne, 0)
        configuration_courante = item_id.data(Qt.UserRole) or {}
        configuration_courante.update(data)
        item_id.setData(Qt.UserRole, configuration_courante)
        
        statut = configuration_courante.get('status', 'libre')

        if statut == "occupied":
            puissance = float(configuration_courante.get('power', 0))
            energie_wh = float(configuration_courante.get('energyWh', 0))
            cout = float(configuration_courante.get('cost', 0))
            # Texte épuré :
            texte_affichage = f"👤 {configuration_courante.get('username', 'Inconnu')} [⚡ {puissance:.0f} W | 📈 {energie_wh:.1f} Wh | 💰 {cout:.2f} € ]"
            couleur_texte = "#f39c12"
        elif statut == "hs":
            texte_affichage = "🔧 Maintenance [hors service]"
            couleur_texte = "#e74c3c"
        else:
            texte_affichage = "🟢 Libre"
            couleur_texte = "#2ecc71"

        self.table.item(ligne, 1).setText(texte_affichage)
        self.table.item(ligne, 1).setForeground(QColor(couleur_texte))
        
        widget_cellule = self.table.cellWidget(ligne, 2)
        if widget_cellule and widget_cellule.layout():
            bouton_stop = widget_cellule.layout().itemAt(3).widget()
            if bouton_stop: bouton_stop.setVisible(statut == "occupied")

    def set_limit(self, id_prise):
        valeur, ok = QInputDialog.getInt(self, "Limite", "Watts max :", 2500, 0, 5000)
        if ok: api.post(f"{API_URL}/plugs/{id_prise}/configure", json={"powerLimit": valeur})

    def show_qr(self, id_prise):
        dialogue = QDialog(self)
        layout_dialogue = QVBoxLayout(dialogue)
        label_image = QLabel()
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap()
        try:
            pixmap.loadFromData(api.get(f"{API_URL}/plugs/{id_prise}/qrcode").content)
            label_image.setPixmap(pixmap.scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except: label_image.setText("Erreur QR Code")
        layout_dialogue.addWidget(label_image)
        dialogue.exec()

    def add_prise(self):
        identifiant, ok = QInputDialog.getText(self, "Ajouter", "ID prise :")
        if ok and identifiant: api.post(f"{API_URL}/plugs", json={"plugId": identifiant})

class TabUsers(QWidget):
    def __init__(self):
        super().__init__()
        self.users_data = {}
        layout = QVBoxLayout(self)
        self.tableau = QTableWidget(0, 3)
        self.tableau.setHorizontalHeaderLabels(["Utilisateurs", "Solde (€)", "Détails"])
        self.tableau.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tableau.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tableau)
        
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
                    btn = QPushButton("ℹ️")
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
        parts = u['username'].split(" ", 1)
        prenom, nom, mail = QLineEdit(parts[0] if len(parts) > 0 else ""), QLineEdit(parts[1] if len(parts) > 1 else ""), QLineEdit()
        try: mail.setText(api.get(f"{API_URL}/auth/users/{u['id']}/history").json().get('user', {}).get('email', ''))
        except: pass
        arg, pwd = QDoubleSpinBox(), QLineEdit()
        arg.setRange(-1000, 10000); arg.setValue(float(u.get('balance', 0)))
        pwd.setPlaceholderText("Laisser vide pour ne pas changer"); pwd.setEchoMode(QLineEdit.Password)
        for txt, w in [("Prénom :", prenom), ("Nom :", nom), ("Email :", mail), ("Solde (€) :", arg), ("Mot de passe :", pwd)]:
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
        self.tableau.setEditTriggers(QAbstractItemView.NoEditTriggers)
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

class TabConso(QWidget):
    def __init__(self):
        super().__init__()
        self.history_vals, self.history_dates = [], []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Consommation par utilisateur :"))

        self.sel = QComboBox()
        self.sel.currentIndexChanged.connect(self.load_history)
        layout.addWidget(self.sel)

        self.graph = pg.PlotWidget(background='#2a2a30')
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        self.graph.setLabel('left', "Consommation", units="Wh")
        layout.addWidget(self.graph)

        QTimer(self).timeout.connect(self.load_users) or None
        t_users = QTimer(self); t_users.timeout.connect(self.load_users); t_users.start(10000)
        t_live  = QTimer(self); t_live.timeout.connect(self.update_live);  t_live.start(2000)
        self.load_users()

    def load_users(self):
        try:
            res = api.get(f"{API_URL}/auth/users").json()
            cur = self.sel.currentData()
            self.sel.blockSignals(True)
            self.sel.clear()
            for u in res:
                if u.get('username') != 'Admin':
                    self.sel.addItem(u['username'], u['id'])
            idx = self.sel.findData(cur)
            self.sel.setCurrentIndex(idx if idx >= 0 else 0)
            self.sel.blockSignals(False)
        except: pass

    def load_history(self):
        uid = self.sel.currentData()
        if not uid: return
        try:
            data = sorted(
                api.get(f"{API_URL}/auth/users/{uid}/history").json().get('history', []),
                key=lambda x: x.get('start_time', '')
            )
            self.history_vals  = [float(h.get("energy_kwh") or 0) * 1000 for h in data]
            self.history_dates = [format_api_date(h.get('start_time') or h.get('created_at')) for h in data]
            self.update_live()
        except: pass

    def update_live(self):
        uid = self.sel.currentData()
        if not uid: return
        try:
            vals, dates = list(self.history_vals), list(self.history_dates)

            # Ajoute le point live si une session est active pour cet user
            for p in api.get(f"{API_URL}/plugs").json():
                if str(p.get('current_session', {}).get('user_id')) == str(uid):
                    vals.append(float(p.get('energyWh') or 0))
                    dates.append(datetime.now().strftime('%m-%d %H:%M'))
                    break

            self.graph.clear()
            if not vals: return

            n = len(dates)
            nb = min(9, n)
            step = max(1, len(dates) // 6)
            ticks = [(i, dates[i]) for i in range(0, len(dates), step)]
            if len(dates) > 0 and ticks[-1][0] != len(dates) - 1:
                ticks.append((len(dates) - 1, dates[-1]))
            self.graph.getAxis('bottom').setTicks([ticks])

            self.graph.getAxis('bottom').setTicks([ticks])
            self.graph.setXRange(-0.5, n - 0.5, padding=0)
            self.graph.plot(range(n), vals,
                            pen=pg.mkPen('#2ecc71', width=2),
                            symbol='o', symbolSize=5, symbolBrush='#2ecc71')
        except: pass

class Dashboard(QTabWidget):    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard Admin"); self.resize(848, 480)
        self.setDocumentMode(True); self.tabBar().setExpanding(True)
        self.addTab(TabPrises(), "🔌 Prises")
        self.addTab(TabConso(), "📈 Consommation")
        self.addTab(TabUsers(), "👤 Utilisateurs")
        self.addTab(TabMaintenance(), "🛠️ Maintenance")

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
            win = Dashboard()
            win.show()
            sys.exit(app.exec())
        else:
            QMessageBox.warning(None, "Connexion", "Identifiants incorrects ou accès refusé.")
            
    except requests.exceptions.RequestException:
        QMessageBox.critical(None, "Erreur Réseau", "Impossible de contacter le serveur. Vérifiez votre connexion.")