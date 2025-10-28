import json
import time
import threading
from collections import deque
from datetime import datetime
import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import paho.mqtt.client as mqtt


class SimplifiedEnergyMonitor:
    # --------- LIMITES / POLÍTICAS DE ALERTA ----------
    V_LOW = 90.0
    V_HIGH = 260.0
    I_WARN = 10.0
    I_CUTOFF = 15.0
    SPIKE_MIN_W = 200.0
    SPIKE_FACTOR = 1.6
    # ---------------------------------------------------

    def __init__(self):
        # Configurações MQTT
        self.mqtt_broker = "seu ip da rede"
        self.mqtt_port = 1883
        self.mqtt_user = ""            # deixe vazio se não usa auth
        self.mqtt_password = ""

        # Cliente MQTT
        self.client = mqtt.Client(clean_session=True)
        self.client.enable_logger()  # log básico no console
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)

        # Dados (últimos 100 pontos)
        self.rooms_data = {
            'sala': deque(maxlen=100),
            'quarto': deque(maxlen=100),
            'cozinha': deque(maxlen=100),
            'banheiro': deque(maxlen=100),
            'area_servico': deque(maxlen=100)
        }

        # Estado dos relés (UI)
        self.relay_status = {
            'sala': True,
            'quarto': True,
            'cozinha': True,
            'banheiro': True,
            'area_servico': True
        }

        # Fator de potência por cômodo
        self.power_factors = {
            'sala': 0.85,
            'quarto': 0.90,
            'cozinha': 0.80,
            'banheiro': 0.95,
            'area_servico': 0.75
        }

        # Limites por cômodo
        self.room_limits = {
            "default": {"V_LOW": 90.0, "V_HIGH": 260.0, "I_WARN": 10.0, "I_CUTOFF": 15.0},
            "cozinha": {"I_WARN": 13.0, "I_CUTOFF": 18.0},
            "banheiro": {"I_WARN": 14.0, "I_CUTOFF": 20.0},
            "area_servico": {"I_WARN": 12.0, "I_CUTOFF": 17.0},
            "sala": {"I_WARN": 8.0, "I_CUTOFF": 12.0},
            "quarto": {"I_WARN": 7.0, "I_CUTOFF": 10.0},
        }

        # Tarifa elétrica (R$/kWh)
        self.tariff = 0.65

        # Interface
        self.setup_gui()

        # Conectar MQTT
        self.connect_mqtt()

        # Thread de atualização de custos
        self.update_thread = threading.Thread(target=self.continuous_update, daemon=True)
        self.update_thread.start()

    # --------------------------- GUI -------------------------------------
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Monitoramento de Energia")
        self.root.geometry("1200x800")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Aba: Gráficos
        self.tab_graphs = ttk.Frame(notebook)
        notebook.add(self.tab_graphs, text='Gráficos')
        self.setup_graphs_tab()

        # Aba: Controle / Avisos
        self.tab_control = ttk.Frame(notebook)
        notebook.add(self.tab_control, text='Controle de Carga')
        self.setup_control_tab()

        # Aba: Custos
        self.tab_costs = ttk.Frame(notebook)
        notebook.add(self.tab_costs, text='Custos de Energia')
        self.setup_costs_tab()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_graphs_tab(self):
        # Controles
        control_frame = ttk.Frame(self.tab_graphs)
        control_frame.pack(fill='x', padx=10, pady=5)

        ttk.Label(control_frame, text="Circuito:").pack(side='left')
        self.selected_room = tk.StringVar(value='sala')
        room_combo = ttk.Combobox(
            control_frame,
            textvariable=self.selected_room,
            values=list(self.rooms_data.keys()),
            state='readonly'
        )
        room_combo.pack(side='left', padx=5)

        ttk.Button(control_frame, text="Iniciar Gráfico",
                   command=self.start_realtime_graph).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Parar Gráfico",
                   command=self.stop_realtime_graph).pack(side='left', padx=5)

        # Indicador numérico de potência
        indicator_frame = ttk.Frame(self.tab_graphs)
        indicator_frame.pack(fill='x', padx=10, pady=(10, 0))

        ttk.Label(indicator_frame, text="Potência :", font=('Arial', 12)).pack(side='left')
        self.current_power_var = tk.StringVar(value="-- W")
        self.current_power_label = ttk.Label(
            indicator_frame,
            textvariable=self.current_power_var,
            font=('Arial', 24, 'bold')
        )
        self.current_power_label.pack(side='left', padx=12)

        # Gráfico (potência)
        self.graph_frame = ttk.Frame(self.tab_graphs)
        self.graph_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.fig, self.ax = plt.subplots(1, 1, figsize=(10, 5))
        self.fig.tight_layout(pad=2.0)
        self.canvas = FigureCanvasTkAgg(self.fig, self.graph_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.animation = None

    def setup_control_tab(self):
        # Status dos relés
        status_frame = ttk.LabelFrame(self.tab_control, text="Status das Cargas")
        status_frame.pack(fill='x', padx=10, pady=10)

        self.relay_labels = {}
        for room in self.rooms_data.keys():
            frame = ttk.Frame(status_frame)
            frame.pack(fill='x', padx=5, pady=5)

            ttk.Label(frame, text=f"{room.title()}:", width=15).pack(side='left')

            ttk.Button(frame, text="Ligar",
                       command=lambda r=room: self.control_relay(r, True)).pack(side='left', padx=2)
            ttk.Button(frame, text="Desligar",
                       command=lambda r=room: self.control_relay(r, False)).pack(side='left', padx=2)

            status_label = ttk.Label(frame, text="● ON", foreground="green")
            status_label.pack(side='left', padx=10)
            self.relay_labels[room] = status_label

        # Controles gerais
        general_frame = ttk.LabelFrame(self.tab_control, text="Controle Geral")
        general_frame.pack(fill='x', padx=10, pady=10)

        ttk.Button(general_frame, text="Ligar Todos",
                   command=lambda: self.control_all_relays(True)).pack(side='left', padx=5, pady=10)
        ttk.Button(general_frame, text="Desligar Todos",
                   command=lambda: self.control_all_relays(False)).pack(side='left', padx=5, pady=10)
        ttk.Button(general_frame, text="EMERGÊNCIA",
                   command=self.emergency_shutdown).pack(side='left', padx=20, pady=10)

        # Avisos
        alerts_frame = ttk.LabelFrame(self.tab_control, text="Avisos do Sistema")
        alerts_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.alert_text = tk.Text(alerts_frame, height=12, state='disabled')
        scrollbar = ttk.Scrollbar(alerts_frame, orient='vertical', command=self.alert_text.yview)
        self.alert_text.configure(yscrollcommand=scrollbar.set)
        self.alert_text.tag_configure("INFO", foreground="#1f6feb")
        self.alert_text.tag_configure("AVISO", foreground="#b08900")
        self.alert_text.tag_configure("ALERTA", foreground="#d97706")
        self.alert_text.tag_configure("CRITICO", foreground="#d00000", font=('Arial', 10, 'bold'))

        self.alert_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def setup_costs_tab(self):
        config_frame = ttk.LabelFrame(self.tab_costs, text="Configuração")
        config_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(config_frame, text="Tarifa Elétrica (R$/kWh):").pack(side='left')
        self.tariff_var = tk.DoubleVar(value=self.tariff)
        ttk.Entry(config_frame, textvariable=self.tariff_var, width=10).pack(side='left', padx=5)
        ttk.Button(config_frame, text="Atualizar",
                   command=self.update_tariff).pack(side='left', padx=5)

        costs_frame = ttk.LabelFrame(self.tab_costs, text="Custos por Cômodo")
        costs_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = ('Cômodo', 'Potência (W)', 'Custo/Hora (R$)', 'Custo/Dia (R$)', 'Custo/Mês (R$)')
        self.costs_tree = ttk.Treeview(costs_frame, columns=columns, show='headings', height=8)
        for col in columns:
            self.costs_tree.heading(col, text=col)
            self.costs_tree.column(col, width=120)

        costs_scrollbar = ttk.Scrollbar(costs_frame, orient='vertical', command=self.costs_tree.yview)
        self.costs_tree.configure(yscrollcommand=costs_scrollbar.set)
        self.costs_tree.pack(side='left', fill='both', expand=True)
        costs_scrollbar.pack(side='right', fill='y')

        totals_frame = ttk.LabelFrame(self.tab_costs, text="Totais do Sistema")
        totals_frame.pack(fill='x', padx=10, pady=10)

        self.total_power_label = ttk.Label(totals_frame, text="Potência Total: -- W",
                                           font=('Arial', 12, 'bold'))
        self.total_power_label.pack(pady=2)
        self.total_cost_hour = ttk.Label(totals_frame, text="Custo por Hora: R$ --")
        self.total_cost_hour.pack(pady=2)
        self.total_cost_day = ttk.Label(totals_frame, text="Custo por Dia: R$ --")
        self.total_cost_day.pack(pady=2)
        self.total_cost_month = ttk.Label(totals_frame, text="Custo por Mês: R$ --")
        self.total_cost_month.pack(pady=2)

    # ------------------------ MQTT / PROCESSAMENTO ------------------------
    def calculate_power(self, voltage, current, room):
        if voltage <= 0 or current <= 0:
            return 0.0
        apparent_power = voltage * current
        pf = self.power_factors.get(room, 0.85)
        return round(apparent_power * pf, 2)

    def connect_mqtt(self):
        try:
            if self.mqtt_user:
                self.client.username_pw_set(self.mqtt_user, self.mqtt_password)
            self.client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
            self.client.loop_start()
            self.add_alert("INFO", "Conectado ao MQTT")
        except Exception as e:
            self.add_alert("ALERTA", f"Erro MQTT: {e}",
                           "Verifique IP/porta do broker, usuário/senha e se o serviço está ativo.")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.add_alert("INFO", "MQTT conectado com sucesso")
            client.subscribe("energy/room/+")
            client.subscribe("energy/relay/status/+")
        else:
            self.add_alert("ALERTA", f"Falha na conexão MQTT: {rc}",
                           "Cheque as credenciais e tente novamente.")

    def on_publish(self, client, userdata, mid):
        # feedback quando algo foi realmente enviado
        print(f"[MQTT] Publicado (mid={mid})")

    def mqtt_publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        """Helper com log e try/except."""
        try:
            print(f"[PUB] {topic} => {payload}")
            self.client.publish(topic, payload=payload, qos=qos, retain=retain)
        except Exception as e:
            self.add_alert("ALERTA", f"Falha ao publicar em {topic}: {e}")

    def on_message(self, client, userdata, msg):
        try:
            topic_parts = msg.topic.split('/')
            payload_text = msg.payload.decode()

            if topic_parts[1] == 'room':
                room = topic_parts[2]
                data = json.loads(payload_text)
                if room in self.rooms_data:
                    voltage = float(data.get('tensao', 0))
                    current = float(data.get('corrente', 0))
                    power = self.calculate_power(voltage, current, room)
                    data['power'] = power
                    data['timestamp_py'] = time.time()
                    self.rooms_data[room].append(data)
                    self.check_alerts(room, voltage, current, power)

            elif topic_parts[1] == 'relay' and topic_parts[2] == 'status':
                # Espera JSON com {"relay_estado": true/false}
                room = topic_parts[3]
                try:
                    data = json.loads(payload_text)
                    if room in self.relay_status:
                        self.relay_status[room] = bool(data.get('relay_estado', False))
                        self.update_relay_display()
                except Exception:
                    # se vier string simples, ignora
                    pass

        except Exception as e:
            self.add_alert("ALERTA", f"Erro ao processar mensagem: {e}",
                           "Formato do payload pode estar incorreto (JSON).")

    # ------------------------ ALERTAS E AÇÕES -----------------------------
    def get_limit(self, room: str, key: str) -> float:
        base = self.room_limits.get("default", {})
        per_room = self.room_limits.get(room, {})
        return float(per_room.get(key, base.get(key)))

    def check_alerts(self, room, v, i, p):
        V_LOW = self.get_limit(room, "V_LOW")
        V_HIGH = self.get_limit(room, "V_HIGH")
        I_WARN = self.get_limit(room, "I_WARN")
        I_CUTOFF = self.get_limit(room, "I_CUTOFF")

        if v < V_LOW:
            self.add_alert("AVISO", f"{room.title()}: Subtensão detectada ({v:.1f} V).",
                           "Evite ligar aparelhos sensíveis. Se persistir, contate a concessionária.")
        elif v > V_HIGH:
            self.add_alert("AVISO", f"{room.title()}: Sobretensão detectada ({v:.1f} V).",
                           "Desconecte equipamentos sensíveis. Se continuar, acione a concessionária.")

        if i > I_CUTOFF:
            self.control_relay(room, False)
            self.add_alert("CRITICO",
                           f"{room.title()}: Corrente crítica {i:.1f} A. Relé DESLIGADO por segurança.",
                           "Verifique curto-circuito/aquecimento. Religando só após inspeção.")
        elif i > I_WARN:
            self.add_alert("ALERTA",
                           f"{room.title()}: Corrente elevada {i:.1f} A.",
                           "Evite ligar mais aparelhos nesse circuito.")

        history = [d.get('power', 0.0) for d in self.rooms_data[room]]
        if len(history) >= 10:
            avg_recent = sum(history[-10:]) / 10.0
            if p > max(self.SPIKE_MIN_W, avg_recent * self.SPIKE_FACTOR):
                self.add_alert("AVISO",
                               f"{room.title()}: Consumo elevado agora ({p:.0f} W).",
                               "Se foi você que ligou algo de alto consumo, ok. Caso contrário, investigue.")

    # ====== AQUI ESTAVA O PROBLEMA: comandos individuais em texto simples ======
    def control_relay(self, room, turn_on: bool):
        payload = "ON" if turn_on else "OFF"
        topic = f"energy/control/{room}"
        self.mqtt_publish(topic, payload)
        action = "ligado" if turn_on else "desligado"
        self.add_alert("INFO", f"Comando enviado: {room} {action}")

    def control_all_relays(self, turn_on: bool):
        payload = "ON" if turn_on else "OFF"
        self.mqtt_publish("energy/control/relay", payload)
        action = "ligados" if turn_on else "desligados"
        self.add_alert("INFO", f"Comando enviado: Todos os relés {action}")

    def emergency_shutdown(self):
        self.mqtt_publish("energy/control/emergency", "SHUTDOWN")
        self.control_all_relays(False)
        self.add_alert("CRITICO", "DESLIGAMENTO DE EMERGÊNCIA ATIVADO! (cargas OFF)")

    def update_relay_display(self):
        for room, status in self.relay_status.items():
            if room in self.relay_labels:
                label = self.relay_labels[room]
                label.config(text="● ON" if status else "● OFF",
                             foreground="green" if status else "red")

    # ----------------------- GRÁFICOS / CUSTOS ----------------------------
    def start_realtime_graph(self):
        if self.animation:
            self.animation.event_source.stop()
        self.animation = FuncAnimation(self.fig, self.update_graph, interval=1000, blit=False)
        self.canvas.draw()
        self.add_alert("INFO", "Gráfico em tempo real iniciado")

    def stop_realtime_graph(self):
        if self.animation:
            self.animation.event_source.stop()
        self.add_alert("INFO", "Gráfico em tempo real parado")

    def update_graph(self, frame):
        room = self.selected_room.get()
        data = list(self.rooms_data[room])
        if not data:
            return
        data = data[-50:]
        times = [d.get('timestamp_py', time.time()) for d in data]
        powers = [float(d.get('power', 0)) for d in data]
        if len(times) < 2:
            return

        base_time = times[0]
        rel_times = [(t - base_time) for t in times]
        last_power = powers[-1]
        self.current_power_var.set(f"{last_power:.1f} W")
        try:
            if last_power >= 1000:
                self.current_power_label.configure(foreground="red")
            elif last_power >= 200:
                self.current_power_label.configure(foreground="orange")
            else:
                self.current_power_label.configure(foreground="green")
        except Exception:
            pass

        self.ax.clear()
        self.ax.plot(rel_times, powers, linewidth=2, label='Potência (W)')
        self.ax.set_ylabel('Potência (W)')
        self.ax.set_xlabel('Tempo (s)')
        self.ax.set_title(f'{room.title()} - Potência em Tempo Real')
        self.ax.grid(True, alpha=0.3)
        self.ax.legend()
        self.fig.tight_layout()
        self.canvas.draw()

    def update_tariff(self):
        self.tariff = self.tariff_var.get()
        self.add_alert("INFO", f"Tarifa atualizada: R$ {self.tariff:.3f}/kWh")
        self.update_costs_display()

    def update_costs_display(self):
        for item in self.costs_tree.get_children():
            self.costs_tree.delete(item)

        total_power = 0.0
        for room, data_queue in self.rooms_data.items():
            if data_queue:
                latest = data_queue[-1]
                power = latest.get('power', 0.0)
                cost_hour = (power / 1000.0) * self.tariff
                cost_day = cost_hour * 24
                cost_month = cost_day * 30
                total_power += power
                self.costs_tree.insert('', 'end', values=(
                    room.title(), f"{power:.1f}", f"{cost_hour:.4f}",
                    f"{cost_day:.2f}", f"{cost_month:.2f}"
                ))

        total_cost_hour = (total_power / 1000.0) * self.tariff
        total_cost_day = total_cost_hour * 24
        total_cost_month = total_cost_day * 30

        self.total_power_label.config(text=f"Potência Total: {total_power:.1f} W")
        self.total_cost_hour.config(text=f"Custo por Hora: R$ {total_cost_hour:.4f}")
        self.total_cost_day.config(text=f"Custo por Dia: R$ {total_cost_day:.2f}")
        self.total_cost_month.config(text=f"Custo por Mês: R$ {total_cost_month:.2f}")

    def continuous_update(self):
        while True:
            try:
                self.update_costs_display()
                time.sleep(5)
            except Exception as e:
                print(f"Erro na atualização contínua: {e}")
                time.sleep(5)

    # ---------------------- PAINEL DE “AVISOS” ----------------------------
    def add_alert(self, level: str, message: str, guidance: str | None = None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {level}: {message}\n"
        if guidance:
            line += f"   ➜ Orientação: {guidance}\n"

        if hasattr(self, 'alert_text'):
            self.alert_text.config(state='normal')
            tag = level.upper()
            if tag not in ("INFO", "AVISO", "ALERTA", "CRITICO"):
                tag = "INFO"
            self.alert_text.insert('end', line, tag)
            self.alert_text.config(state='disabled')
            self.alert_text.see('end')

        print(line.strip())

    # ---------------------------- SISTEMA ---------------------------------
    def on_close(self):
        try:
            if self.animation:
                self.animation.event_source.stop()
            self.client.loop_stop()
            self.client.disconnect()
        except:
            pass
        self.root.destroy()

    def run(self):
        print("Sistema de Monitoramento Simplificado iniciado!")
        self.add_alert("INFO", "Sistema iniciado")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.add_alert("AVISO", "Sistema encerrado pelo usuário")
        finally:
            self.on_close()


if __name__ == "__main__":
    app = SimplifiedEnergyMonitor()
    app.run()
