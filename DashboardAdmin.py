import sys, requests, os, json, socketio
from PySide6.QtWidgets import (
    QApplication, QTabWidget, QWidget, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QHBoxLayout, QPushButton, QDialog,
    QMessageBox, QLabel, QInputDialog, QComboBox, QFrame, QDoubleSpinBox, QLineEdit
)
from PySide6.QtCore import Qt, QTimer, Slot, QObject, Signal

import pyqtgraph as pg
from PySide6.QtGui import QPixmap, QColor, QIcon    
from datetime import datetime

API_URL = "https://recharge.cielnewton.fr/api"
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
                    ADMIN_CREDENTIALS[key] = val
except:
    pass

class SocketSignals(QObject):
    update_ui = Signal(str, dict)

class UserDetailsDialog(QDialog):
    def __init__(self, token, user_id, username):
        super().__init__()
        self.token, self.user_id = token, user_id
        self.setWindowTitle(f"Profil : {username}")
        self.resize(550, 600)
        layout = QVBoxLayout(self)
        
        self.info_card = QFrame()
        self.info_card.setStyleSheet("background-color: #2a2a30; border-radius: 8px; padding: 15px; border: 1px solid #3d3d45;")
        self.info_lay = QVBoxLayout(self.info_card)
        
        self.lbl_title = QLabel(f"<h2>{username}</h2>")
        self.lbl_email = QLabel("📧 <b>Email:</b> Chargement...")
        self.lbl_solde = QLabel("💰 <b>Solde:</b> Chargement...")
        self.lbl_inscrit = QLabel("📅 <b>Inscrit le:</b> Chargement...")
        self.lbl_pwd = QLabel("🔑 <b>Mot de passe:</b> Haché en BDD")
        
        for lbl in [self.lbl_title, self.lbl_email, self.lbl_solde, self.lbl_inscrit, self.lbl_pwd]:
            self.info_lay.addWidget(lbl)
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
        self.load_data()

    def load_data(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            res = requests.get(f"{API_URL}/auth/users/{self.user_id}/history", headers=headers)
            data = res.json()
            user = data.get('user', {})
            history = data.get('transactions') or data.get('history') or []

            self.lbl_email.setText(f"📧 <b>Email:</b> {user.get('email', 'N/A')}")
            self.lbl_solde.setText(f"💰 {float(user.get('balance', 0)):.2f} €")
            
            if user.get('created_at'):
                dt = datetime.fromisoformat(user.get('created_at').replace('Z', '+00:00'))
                self.lbl_inscrit.setText(f"📅 <b>Inscrit le:</b> {dt.strftime('%d/%m/%Y à %H:%M')}")
            
            self.lbl_pwd.setToolTip(f"Hash: {user.get('password')}")

            self.trans_table.setRowCount(len(history))
            for i, t in enumerate(history):
                d_raw = t.get('created_at') or t.get('start_time') or ""
                if len(d_raw) > 16:
                    self.trans_table.setItem(i, 0, QTableWidgetItem(f"{d_raw[8:10]}/{d_raw[5:7]} {d_raw[11:16]}"))
                else:
                    self.trans_table.setItem(i, 0, QTableWidgetItem(d_raw))
                
                kwh = t.get('energy_kwh', 0)
                desc = t.get('description') or f"Charge Prise {t.get('plug_id')} ({kwh:.3f} kWh)"
                self.trans_table.setItem(i, 1, QTableWidgetItem(desc))
                
                cost = float(t.get('amount') or t.get('cost') or 0.0)
                item_cost = QTableWidgetItem(f"{cost:+.2f}€")
                item_cost.setForeground(QColor("#2ecc71" if cost >= 0 else "#e74c3c"))
                self.trans_table.setItem(i, 2, item_cost)
        except:
            pass

class TabPrises(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.signals = SocketSignals()
        self.signals.update_ui.connect(self.update_row_ui)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Prise", "Statut & Session", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btns_lay = QHBoxLayout()
        
        btn_add = QPushButton("➕ Ajouter une prise")
        btn_add.clicked.connect(self.add_prise)
        btns_lay.addWidget(btn_add)

        btn_provision = QPushButton("🚀 Config. Initiale (Local)")
        btn_provision.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        btn_provision.clicked.connect(self.provision_local_plug)
        btns_lay.addWidget(btn_provision)

        layout.addLayout(btns_lay)

        self.init_socket()
        self.timer = QTimer()
        self.timer.timeout.connect(self.load_data)
        self.timer.start(5000)
        self.load_data()

    def provision_local_plug(self):
            dlg = QDialog(self)
            dlg.setWindowTitle("Provisionnement Prise Neuve")
            dlg.setFixedWidth(450)
            layout = QVBoxLayout(dlg)

            info_box = QFrame()
            info_box.setStyleSheet("background-color: #3d2b1f; border-left: 5px solid #e67e22; border-radius: 4px;")
            info_lay = QVBoxLayout(info_box)
            lbl_step1 = QLabel("<b>⚠️ ÉTAPE 1 :</b><br>Connectez le Wi-Fi de cet ordinateur au réseau de la prise<br>(ex: <i>ShellyPlusPlugS-XXXX</i>). Laissez ce tableau de bord ouvert.")
            lbl_step1.setWordWrap(True)
            info_lay.addWidget(lbl_step1)
            layout.addWidget(info_box)

            layout.addWidget(QLabel("<b>1. Réseau Wi-Fi du Lycée</b>"))
            edit_ssid = QLineEdit()
            edit_ssid.setPlaceholderText("Nom du Wi-Fi (SSID)")
            layout.addWidget(edit_ssid)
            
            edit_wifi_pass = QLineEdit()
            edit_wifi_pass.setPlaceholderText("Mot de passe Wi-Fi")
            edit_wifi_pass.setEchoMode(QLineEdit.Password)
            layout.addWidget(edit_wifi_pass)

            layout.addWidget(QLabel("<br><b>2. Serveur MQTT</b>"))
            edit_mqtt = QLineEdit()
            edit_mqtt.setPlaceholderText("Serveur (ex: broker.hivemq.com:1883)")
            layout.addWidget(edit_mqtt)

            edit_mqtt_user = QLineEdit()
            edit_mqtt_user.setPlaceholderText("Utilisateur MQTT (Optionnel)")
            layout.addWidget(edit_mqtt_user)

            edit_mqtt_pass = QLineEdit()
            edit_mqtt_pass.setPlaceholderText("Mot de passe MQTT (Optionnel)")
            edit_mqtt_pass.setEchoMode(QLineEdit.Password)
            layout.addWidget(edit_mqtt_pass)

            btn_lay = QHBoxLayout()
            btn_send = QPushButton("🚀 Envoyer à la prise")
            btn_send.setStyleSheet("background-color: #8e44ad; color: white; padding: 8px; font-weight: bold;")
            btn_cancel = QPushButton("Annuler")
            btn_cancel.setStyleSheet("background-color: #3d3d45; color: white; padding: 8px;")
            
            btn_lay.addWidget(btn_send)
            btn_lay.addWidget(btn_cancel)
            layout.addLayout(btn_lay)

            btn_send.clicked.connect(dlg.accept)
            btn_cancel.clicked.connect(dlg.reject)

            if dlg.exec() == QDialog.Accepted:
                ssid, pwd = edit_ssid.text(), edit_wifi_pass.text()
                mqtt, m_user, m_pass = edit_mqtt.text(), edit_mqtt_user.text(), edit_mqtt_pass.text()
                
                if not ssid or not mqtt:
                    QMessageBox.warning(self, "Erreur", "Le SSID et le serveur MQTT sont obligatoires.")
                    return

                try:
                    # Payload MQTT complet avec auth
                    mqtt_config = {"server": mqtt, "enable": True}
                    if m_user: mqtt_config["user"] = m_user
                    if m_pass: mqtt_config["pass"] = m_pass

                    requests.post("http://192.168.33.1/rpc/Mqtt.SetConfig", 
                                json={"config": mqtt_config}, timeout=3)
                    try:
                        requests.post("http://192.168.33.1/rpc/Wifi.SetConfig", 
                                    json={"config": {"sta1": {"ssid": ssid, "pass": pwd, "enable": True}}}, timeout=2)
                    except:
                        pass
                    QMessageBox.information(self, "Succès", "Configuration envoyée ! La prise redémarre.")
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Connexion échouée (192.168.33.1).\nVérifiez votre Wi-Fi.")

    def load_data(self):
        try:
            res = requests.get(f"{API_URL}/plugs",
                               headers={"Authorization": f"Bearer {self.token}"},
                               timeout=3)
            if res.ok:
                prises = res.json()
                existing_ids = set()
                for p in prises:
                    pid = str(p['id'])
                    existing_ids.add(pid)
                    row = self.find_row(pid)
                    if row is None:
                        row = self.table.rowCount()
                        self.table.insertRow(row)
                        item = QTableWidgetItem(pid)
                        item.setData(Qt.UserRole, p)
                        self.table.setItem(row, 0, item)
                        self.table.setItem(row, 1, QTableWidgetItem("..."))
                        self.add_actions(row, pid)
                    self.update_row_ui(pid, p)

                for r in reversed(range(self.table.rowCount())):
                    item = self.table.item(r, 0)
                    if item and item.text() not in existing_ids:
                        self.table.removeRow(r)
        except:
            pass

    def find_row(self, pid):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.text() == pid:
                return r
        return None

    def add_actions(self, row, pid):
        actions = QWidget()
        lay = QHBoxLayout(actions)
        lay.setContentsMargins(2, 2, 2, 2)
        btn_qr = QPushButton("QR")
        btn_qr.clicked.connect(lambda _, x=pid: self.show_qr(x))
        btn_m = QPushButton("🔧")
        btn_m.clicked.connect(lambda _, x=pid: self.toggle_m(x))
        btn_cfg = QPushButton("⚙️")
        btn_cfg.clicked.connect(lambda _, x=pid: self.set_limit(x))
        btn_stop = QPushButton("🛑")
        btn_stop.setStyleSheet("background:#c0392b;")
        btn_stop.setEnabled(False)
        btn_stop.clicked.connect(lambda _, x=pid: self.force_stop(x))
        lay.addWidget(btn_qr); lay.addWidget(btn_m); lay.addWidget(btn_cfg); lay.addWidget(btn_stop)
        self.table.setCellWidget(row, 2, actions)

    @Slot(str, dict)
    def update_row_ui(self, pid, data):
            # 1. On cherche la ligne correspondant à l'ID de la prise
            row = self.find_row(pid)
            if row is None: 
                return

            # 2. Mise à jour des données stockées dans l'objet (UserRole)
            item = self.table.item(row, 0)
            curr = item.data(Qt.UserRole) or {}
            curr.update(data)
            item.setData(Qt.UserRole, curr)

            # 3. Extraction des variables
            status = curr.get('status', 'libre')
            state = curr.get('state', False)
            user = curr.get('username') or "Inconnu"
            power = float(curr.get('power') or curr.get('powerW') or 0)
            energy = float(curr.get('energyWh') or 0)

            # 4. Formatage du texte de statut
            elec = "⚡ ON" if state else "OFF"

            if status == "occupied":
                txt = f"👤 {user} ({elec}) | ⚡ {power:.0f}W | 📈 {energy:.1f}Wh"
                color = "#f39c12"  # Orange
            elif status == "hs":
                txt = "🔧 Maintenance (Hors Service)"
                color = "#e74c3c"  # Rouge
            else:
                txt = f"Libre ({elec})"
                color = "#2ecc71"  # Vert

            # 5. Application au tableau
            cell = self.table.item(row, 1)
            if cell:
                cell.setText(txt)
                cell.setForeground(QColor(color))

            # 6. GESTION DU BOUTON STOP (Affiché uniquement si occupé)
            actions = self.table.cellWidget(row, 2)
            if actions and actions.layout():
                # Dans add_actions, le bouton STOP est le 4ème (index 3)
                btn_stop = actions.layout().itemAt(3).widget()
                if btn_stop:
                    if status == "occupied":
                        btn_stop.show()
                        btn_stop.setEnabled(True)
                    else:
                        btn_stop.hide()

    def init_socket(self):
        self.sio = socketio.Client()
        @self.sio.on('power_update')
        def on_power(d): self.signals.update_ui.emit(str(d['plugId']), {'power': d['power']})
        @self.sio.on('live_consumption')
        def on_energy(d): self.signals.update_ui.emit(str(d['plugId']), {'energyWh': d['energyWh']})
        @self.sio.on('status_update')
        def on_status(d): self.signals.update_ui.emit(str(d['plugId']), d)
        try:
            self.sio.connect(API_URL.replace('/api', ''), socketio_path='/api/socket.io', transports=['websocket'])
        except: pass

    def toggle_m(self, pid):
        requests.post(f"{API_URL}/plugs/{pid}/maintenance", headers={"Authorization": f"Bearer {self.token}"})

    def force_stop(self, pid):
        requests.post(f"{API_URL}/plugs/{pid}/force-stop", headers={"Authorization": f"Bearer {self.token}"})

    def set_limit(self, pid):
        val, ok = QInputDialog.getInt(self, "Limite", "Watts max :", 2500, 0, 5000)
        if ok: requests.post(f"{API_URL}/plugs/{pid}/configure", json={"powerLimit": val}, headers={"Authorization": f"Bearer {self.token}"})

    def show_qr(self, pid):
        dlg = QDialog(self); lay = QVBoxLayout(dlg); lab = QLabel()
        res = requests.get(f"{API_URL}/plugs/{pid}/qrcode")
        px = QPixmap(); px.loadFromData(res.content)
        lab.setPixmap(px.scaled(250, 250)); lay.addWidget(lab); dlg.exec()

    def add_prise(self):
        nom, ok = QInputDialog.getText(self, "Ajouter", "ID :")
        if ok and nom: requests.post(f"{API_URL}/plugs", json={"plugId": nom}, headers={"Authorization": f"Bearer {self.token}"})

class TabConso(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.history_vals = []
        self.history_dates = []
        layout = QVBoxLayout(self)
        self.sel = QComboBox()
        self.sel.currentIndexChanged.connect(self.load_history)
        layout.addWidget(QLabel("Consommation par utilisateur :"))
        layout.addWidget(self.sel)
        self.graph = pg.PlotWidget()
        self.graph.setBackground('#2a2a30')
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        self.graph.setLabel('left', 'Consommation', units='Wh')
        self.graph.setLabel('bottom', 'Temps')
        layout.addWidget(self.graph)
        self.t_live = QTimer(); self.t_live.timeout.connect(self.update_live); self.t_live.start(2000)
        self.t_users = QTimer(); self.t_users.timeout.connect(self.load_users); self.t_users.start(10000)
        self.load_users()
    
    def load_users(self):
        try:
            res = requests.get(f"{API_URL}/auth/users", headers={"Authorization": f"Bearer {self.token}"})
            if res.ok:
                cur = self.sel.currentData()
                self.sel.blockSignals(True)
                self.sel.clear()
                for u in [x for x in res.json() if x['username'] != 'Admin']:
                    self.sel.addItem(u['username'], u['id'])
                if cur:
                    idx = self.sel.findData(cur); self.sel.setCurrentIndex(idx if idx >= 0 else 0)
                self.sel.blockSignals(False)
        except:
            pass

    def load_history(self):
        uid = self.sel.currentData()
        if not uid:
            return
        try:
            res = requests.get(f"{API_URL}/auth/users/{uid}/history", headers={"Authorization": f"Bearer {self.token}"})
            if res.ok:
                data = res.json().get('history', [])
                data.sort(key=lambda x: x.get('start_time', ''))
                self.history_vals = []
                self.history_dates = []
                for h in data:
                    val = float(h.get("energy_kwh") or 0) * 1000
                    self.history_vals.append(val)
                    d_raw = h.get('start_time') or h.get('created_at') or ""
                    try:
                        dt = datetime.fromisoformat(d_raw.replace('Z', '+00:00'))
                        self.history_dates.append(dt.strftime('%d/%m %H:%M'))
                    except:
                        self.history_dates.append(d_raw[5:16])
                self.update_live()
        except:
            pass

    def update_live(self):
        uid = self.sel.currentData()
        if not uid:
            return
        try:
            res = requests.get(f"{API_URL}/plugs", headers={"Authorization": f"Bearer {self.token}"})
            live_val = 0
            active = False
            for p in res.json():
                sess = p.get('current_session', {})
                if str(sess.get('user_id')) == str(uid):
                    live_val = float(p.get('energyWh') or 0)
                    active = True
                    break
            vals = list(self.history_vals)
            dates = list(self.history_dates)
            if active:
                vals.append(live_val)
                dates.append(datetime.now().strftime('%H:%M:%S'))
            self.graph.clear()
            if vals:
                x_axis = list(range(len(vals)))
                step = max(1, len(dates) // 5)
                ticks = [(i, dates[i]) for i in range(0, len(dates), step)]
                self.graph.getAxis('bottom').setTicks([ticks])
                self.graph.plot(x_axis, vals, pen=pg.mkPen('#2ecc71', width=3), symbol='o', symbolSize=6, symbolBrush='#27ae60')
        except:
            pass

class TabUsers(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        self.users_data = {}
        layout = QVBoxLayout(self)
        
        self.tableau = QTableWidget(0, 3)
        self.tableau.setHorizontalHeaderLabels(["Utilisateurs", "Solde (€)", "Détails"])
        self.tableau.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.tableau)
        
        btns = QHBoxLayout()
        self.btn_add = QPushButton("➕ Nouveau")
        self.btn_edit = QPushButton("✏️ Modifier")
        self.btn_del = QPushButton("🗑️ Supprimer")
        
        self.btn_add.setStyleSheet("background-color: #27ae60;")
        self.btn_edit.setStyleSheet("background-color: #e67e22;")
        self.btn_del.setStyleSheet("background-color: #c0392b;")
        
        for b in [self.btn_add, self.btn_edit, self.btn_del]: btns.addWidget(b)
        layout.addLayout(btns)

        self.btn_add.clicked.connect(self.add)
        self.btn_edit.clicked.connect(self.edit)
        self.btn_del.clicked.connect(self.delete)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def refresh(self):
        try:
            res = requests.get(f"{API_URL}/auth/users", headers={"Authorization": f"Bearer {self.token}"}, timeout=3)
            if res.ok:
                users = [u for u in res.json() if u['username'] != 'Admin']
                if len(users) != self.tableau.rowCount():
                    self.tableau.setRowCount(len(users))
                    for i, u in enumerate(users):
                        self.tableau.setItem(i, 0, QTableWidgetItem(u['username']))
                        self.tableau.setItem(i, 1, QTableWidgetItem(f"{float(u['balance']):.2f} €"))
                        btn = QPushButton("ℹ️")
                        uid, uname = u['id'], u['username']
                        btn.clicked.connect(lambda _, id=uid, n=uname: UserDetailsDialog(self.token, id, n).exec())
                        self.tableau.setCellWidget(i, 2, btn)
                else:
                    for i, u in enumerate(users):
                        item = self.tableau.item(i, 1)
                        if item: item.setText(f"{float(u['balance']):.2f} €")
                self.users_data = {i: u for i, u in enumerate(users)}
        except: pass

    def add(self):
        dlg = QDialog(self); dlg.setWindowTitle("Ajouter un utilisateur"); lay = QVBoxLayout(dlg)
        f = QLineEdit(); f.setPlaceholderText("Prénom"); lay.addWidget(f)
        n = QLineEdit(); n.setPlaceholderText("Nom"); lay.addWidget(n)
        e = QLineEdit(); e.setPlaceholderText("Email"); lay.addWidget(e)
        m = QLineEdit(); m.setPlaceholderText("Mot de passe"); m.setEchoMode(QLineEdit.Password); lay.addWidget(m)
        a = QLineEdit(); a.setPlaceholderText("Argent (€)"); lay.addWidget(a)
        
        btn = QPushButton("Créer l'utilisateur"); btn.setStyleSheet("background-color: #27ae60;"); btn.clicked.connect(dlg.accept); lay.addWidget(btn)
        
        if dlg.exec() == QDialog.Accepted:
            payload = {"username": f"{f.text()} {n.text()}", "email": e.text(), "password": m.text(), "balance": float(a.text() or 0)}
            requests.post(f"{API_URL}/auth/register", json=payload, headers={"Authorization": f"Bearer {self.token}"})
            self.refresh()

    def edit(self):
            row = self.tableau.currentRow()
            if row >= 0 and row in self.users_data:
                u = self.users_data[row]
                
                headers = {"Authorization": f"Bearer {self.token}"}
                try:
                    res_info = requests.get(f"{API_URL}/auth/users/{u['id']}/history", headers=headers, timeout=3)
                    user_details = res_info.json().get('user', {})
                    current_email = user_details.get('email', '')
                except:
                    current_email = ""

                dlg = QDialog(self)
                dlg.setWindowTitle(f"Modifier : {u['username']}")
                lay = QVBoxLayout(dlg)
                
                nom = QLineEdit()
                nom.setText(u['username'])
                lay.addWidget(QLabel("Nom complet :"))
                lay.addWidget(nom)
                
                mail = QLineEdit()
                mail.setText(current_email)
                lay.addWidget(QLabel("Email :"))
                lay.addWidget(mail)
                
                arg = QDoubleSpinBox()
                arg.setRange(-1000, 10000)
                arg.setDecimals(2)
                arg.setSuffix(" €")
                arg.setValue(float(u.get('balance', 0)))
                lay.addWidget(QLabel("Solde :"))
                lay.addWidget(arg)
                
                pwd = QLineEdit()
                pwd.setPlaceholderText("Changer le mot de passe (laisser vide pour garder l'actuel)")
                pwd.setEchoMode(QLineEdit.Password)
                lay.addWidget(QLabel("Mot de passe :"))
                lay.addWidget(pwd)
                
                btn = QPushButton("Valider les modifications")
                btn.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold; padding: 8px;")
                btn.clicked.connect(dlg.accept)
                lay.addWidget(btn)
                
                if dlg.exec() == QDialog.Accepted:
                    payload = {
                        "username": nom.text(),
                        "email": mail.text(),
                        "balance": float(arg.value())
                    }
                    
                    if pwd.text().strip():
                        payload["password"] = pwd.text().strip()
                    
                    try:
                        res = requests.put(
                            f"{API_URL}/auth/users/{u['id']}", 
                            json=payload, 
                            headers=headers,
                            timeout=5
                        )
                        if res.ok:
                            self.refresh()
                        else:
                            QMessageBox.warning(self, "Erreur", f"Serveur : {res.text}")
                    except Exception as e:
                        QMessageBox.critical(self, "Erreur", str(e))


    def delete(self):
        row = self.tableau.currentRow()
        if row >= 0 and row in self.users_data:
            u = self.users_data[row]
            msg = QMessageBox(self)
            msg.setWindowTitle("Supprimer")
            msg.setText(f"<h2>{u['username']}</h2><br>Voulez-vous vraiment supprimer ce compte ?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg.button(QMessageBox.Yes).setText("Oui, supprimer")
            msg.button(QMessageBox.Yes).setStyleSheet("background-color: #c0392b;")
            
            if msg.exec() == QMessageBox.Yes:
                requests.delete(f"{API_URL}/auth/users/{u['id']}", headers={"Authorization": f"Bearer {self.token}"})
                self.refresh()


class TabMaintenance(QWidget):
    def __init__(self, token):
        super().__init__()
        self.token = token
        layout = QVBoxLayout(self)
        
        # Configuration du tableau
        self.tableau = QTableWidget(0, 2)
        # REMPLACÉ : "Appareil" par "Prise"
        self.tableau.setHorizontalHeaderLabels(["Prise", "Alerte"])
        
        self.tableau.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tableau.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableau.verticalHeader().setVisible(False)
        self.tableau.setAlternatingRowColors(True)
        self.tableau.setStyleSheet("QTableWidget { background-color: #2a2a30; gridline-color: #3d3d45; }")
        
        layout.addWidget(self.tableau)
        
        # Timer pour le rafraîchissement (Polling toutes les 10s comme dans Notification.js)
        self.timer = QTimer()
        self.timer.timeout.connect(self.fetch_alerts)
        self.timer.start(10000) 
        
        # Premier appel immédiat au chargement
        self.fetch_alerts()

    def fetch_alerts(self):
        # Si on n'a pas de token, on évite de spammer (équivalent au check userManager en JS)
        if not self.token: return

        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            # Appel à l'API identique au code JS
            res = requests.get(f"{API_URL}/plugs/alerts", headers=headers, timeout=5)
            if res.ok:
                data = res.json()
                # On récupère la liste 'devices' renvoyée par l'API
                alerts = data.get('devices', [])
                self.update_ui(alerts)
        except Exception as e:
            print(f"Erreur Maintenance API: {e}")

    def update_ui(self, alerts):
        self.tableau.setRowCount(0)

        # Gestion du cas "Aucune alerte" (équivalent du innerHTML avec succès en JS)
        if not alerts or len(alerts) == 0:
            self.tableau.setRowCount(1)
            item_ok = QTableWidgetItem("Aucune alerte ✅")
            item_ok.setTextAlignment(Qt.AlignCenter)
            item_ok.setForeground(QColor("#27ae60")) # Vert succès
            self.tableau.setItem(0, 0, QTableWidgetItem(""))
            self.tableau.setItem(0, 1, item_ok)
            return

        for alert in alerts:
            row = self.tableau.rowCount()
            self.tableau.insertRow(row)

            # Colonne 1 : Prise (ID mis en gras)
            plug_id = str(alert.get('id', 'N/A'))
            item_id = QTableWidgetItem(plug_id)
            font = item_id.font()
            font.setBold(True)
            item_id.setFont(font)
            
            # Colonne 2 : Alerte (Raison en rouge + Heure)
            reason = alert.get('alert_reason', 'Erreur')
            last_ping = alert.get('last_ping', '')
            
            # Formatage de l'heure (HH:mm)
            time_str = ""
            try:
                if last_ping:
                    # Conversion ISO vers local
                    dt = datetime.fromisoformat(last_ping.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M')
            except:
                # Fallback si le format date est capricieux
                time_str = "--:--"

            # Construction du texte de l'alerte
            display_text = f"{reason}  ({time_str})"
            item_alert = QTableWidgetItem(display_text)
            item_alert.setForeground(QColor("#c0392b")) # Rouge alerte

            self.tableau.setItem(row, 0, item_id)
            self.tableau.setItem(row, 1, item_alert)

class Dashboard(QTabWidget):    
    def __init__(self, token):
        super().__init__()
        self.setWindowTitle("Dashboard Admin")
        self.setWindowIcon(QIcon("icon.png"))
        self.resize(848, 480)
        self.setDocumentMode(True)
        self.tabBar().setExpanding(True)
        self.addTab(TabPrises(token), "🔌 Prises")
        self.addTab(TabConso(token), "📈 Consommation")
        self.addTab(TabUsers(token), "👤 Utilisateurs")
        self.addTab(TabMaintenance(token), "🛠️ Maintenance")

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
        res = requests.post(f"{API_URL}/auth/login", json=ADMIN_CREDENTIALS, timeout=5)
        if res.status_code == 200:
            token = res.json().get("token")
            win = Dashboard(token)
            win.show()
            sys.exit(app.exec())
        else:
            QMessageBox.critical(None, "Erreur Login", "Identifiants administrateur incorrects.")
    except Exception as e:
        QMessageBox.critical(None, "Serveur", f"Impossible de joindre le serveur : {e}") 