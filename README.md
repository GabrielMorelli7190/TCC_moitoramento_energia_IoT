# 💡 Solução IoT para Monitoramento de Eficiência Energética

Este projeto apresenta o desenvolvimento de um **sistema de monitoramento e controle de energia elétrica residencial** baseado em **Internet das Coisas (IoT)**. O objetivo é tornar o consumo de energia mais transparente e inteligente, permitindo acompanhar tensão, corrente e potência em tempo real, além de atuar automaticamente em casos de falhas elétricas.

## ⚙️ Componentes Utilizados
- **ESP32 WROOM-32** – Microcontrolador principal responsável pela coleta de dados e controle das cargas.  
- **Sensor ACS712 (5A / 20A)** – Medição de corrente elétrica.  
- **Sensor ZMPT101B** – Medição de tensão alternada da rede.  
- **Módulo Relé 5V (ativo em LOW)** – Controle de cargas conectadas.  
- **LED e Buzzer** – Indicação de falhas e alertas.  
- **Aplicação Python (cod_monitor.py)** – Processamento dos dados, exibição em interface gráfica e comunicação com o ESP32.

## 🧠 Funcionalidades Principais
- Monitoramento em tempo real de **tensão, corrente e potência**.  
- **Desligamento automático** de cargas em casos de subtensão ou sobrecorrente.  
- Exibição gráfica de dados através da aplicação Python.  
- **Comunicação MQTT** entre ESP32 e Python para troca de informações.  
- Registro de logs e alertas automáticos.  

## 🖥️ Estrutura do Projeto

├── cod_arduino_esp_monitor # Código do ESP32 (Arduino)

├── cod_monitor.py # Interface e processamento em Python

└── README.md # Descrição do projeto

## 🚀 Como Executar
1. **Carregue o código do ESP32** no Arduino IDE.  
2. **Configure a rede Wi-Fi e o servidor MQTT** no código.  
3. **Execute o script Python (`cod_monitor.py`)** no computador conectado à mesma rede.  
4. Visualize as medições e controle as cargas pela interface gráfica.  

## 📈 Resultados
Durante os testes, o sistema apresentou:
- Leituras precisas de corrente e tensão.  
- Comunicação estável via MQTT.  
- Resposta rápida no desligamento de cargas em condições críticas.  

## 🔮 Trabalhos Futuros
- Implementação de **armazenamento em nuvem** para histórico de consumo.  
- Cálculo de **potência ativa e reativa**, além da potência aparente.  
- Versão móvel da interface para **monitoramento via celular**.  

## 👨‍🔧 Autor
**Gabriel Henrique Morelli**  
Curso: Engenharia de Controle e Automação  
Instituição: FENTESC – Faculdade de Engenharia e Tecnologia  

---

🧾 *Este repositório faz parte do Trabalho de Conclusão de Curso intitulado “Solução IoT para Monitoramento de Eficiência Energética”.*
