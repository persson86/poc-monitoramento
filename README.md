🧠 Intelligent Event Monitoring Platform (PoC)

From video streams to structured events, human-readable narratives, and reliable decisions.

Este projeto é uma prova de conceito (PoC) de uma plataforma de monitoramento inteligente baseada em vídeo, construída com foco em engenharia de eventos, rastreabilidade, narrativas legíveis e decisão determinística, utilizando LLMs apenas como observadores críticos, nunca como autoridade final.

O primeiro caso de uso é a detecção de quedas de idosos em ambientes residenciais, mas a arquitetura foi desenhada desde o início para expandir para qualquer evento comportamental, como invasões, movimentos suspeitos, permanência indevida ou comportamentos anômalos.

⸻

✨ Princípios Fundamentais

Arquitetura event-driven desde a base.
Determinismo antes de IA.
LLM como observadora, não decisora.
Rastreabilidade total de eventos.
Replay como capacidade de primeira classe.
Fail-safe por padrão.
Escalável para múltiplos tipos de eventos e sensores.

⸻

🧩 Visão Geral da Arquitetura

Video Stream (RTSP / Webcam)
→ Frame Ingestion
→ Motion / Pose Analysis
→ Event Engine (Atomic + Composite Events)
→ Event Persistence (JSON)
→ Analysis Snapshot (Narrativa Estruturada)
→ Decision Engine (Autoridade)
→ LLM Arbiter (Observação Crítica – Opcional)

⸻

🚀 O Que o Sistema Faz Hoje

• Lê vídeo de webcam ou stream RTSP
• Detecta movimentos e padrões físicos básicos
• Gera eventos atômicos e compostos
• Persiste eventos com IDs e rastreabilidade
• Permite replay temporal de eventos
• Constrói Analysis Snapshots (janelas narrativas)
• Gera resumo legível por humanos
• Executa decisões determinísticas (Decision Engine v0.2)
• Integra LLM real (GPT-5 mini) em modo observe
• Exibe a análise da LLM no terminal
• Possui fallback seguro sem IA

⸻

🗂️ Estrutura do Projeto

src/
camera/ – leitura RTSP / webcam
analyzer/ – motion / pose analysis
events/ – event engine + persistência
analysis/ – analysis snapshot builder
decision/ – decision engine + LLM arbiter
test_*.py – testes por fase
main.py – loop principal

⸻

🧠 Conceitos-Chave

Events

Eventos são unidades objetivas e persistentes que representam algo detectado no mundo físico (ex.: RAPID_VERTICAL_MOVEMENT, POTENTIAL_FALL). Cada evento é salvo em JSON, com timestamp, ID único e metadados.

Analysis Snapshot

Um Analysis Snapshot é uma janela temporal de eventos transformada em uma história estruturada. Inclui intervalo de tempo, resumo quantitativo, padrões temporais, estado observado (ex.: postura baixa), hipóteses com confiança e human_readable_summary. É o input oficial para decisões e LLMs.

Decision Engine (Autoridade)

Sistema determinístico responsável pela decisão final. Decisões possíveis: IGNORE, MONITOR, REQUEST_CONFIRMATION, NOTIFY_CAREGIVER.
Versão atual: v0.2, considerando tempo em postura baixa, recuperação após queda, redução de falsos positivos e priorização de segurança.

LLM Arbiter (Opcional)

A LLM não vê vídeo, não executa ações, não substitui regras e não bloqueia o sistema. Apenas lê o Analysis Snapshot, fornece leitura crítica contextual, aponta ambiguidades e riscos e sugere cautela ou escalonamento.
Modo atual: observe. Modelo testado: gpt-5-mini.

⸻

🔐 Configuração de Ambiente

Variáveis esperadas via .env (não versionado):
LLM_ENABLED, LLM_MODE, LLM_MODEL, OPENAI_API_KEY.
O arquivo .env não deve ser commitado e já está no .gitignore.

⸻

▶️ Execução de Testes

Detector + Webcam: python3 src/test_fall_detector.py
Analysis Snapshot: python3 src/test_analysis_snapshot.py
Decision Engine: python3 src/test_decision_engine_scenarios.py
LLM em modo observe: python3 src/test_llm_observe_mode.py

⸻

🧪 Estado Atual do Projeto

Pipeline end-to-end funcional.
Arquitetura validada por fases.
Eventos rastreáveis e replayáveis.
Snapshots legíveis para humanos e IA.
Decision Engine maduro (v0.2).
LLM real integrada com sucesso.

⸻

🛣️ Próximos Passos Possíveis

Refinar ainda mais o human_readable_summary.
Comparar decisão determinística vs leitura da LLM.
Integração com Telegram (read-only).
Testes com câmera IP real (RTSP).
Expansão para novos tipos de eventos comportamentais.

⸻

🧠 Filosofia do Projeto

Vídeo não é entendimento.
Eventos são.
Histórias são.
Decisões precisam ser explicáveis.

Este projeto demonstra que boa engenharia vem antes da IA, e que LLMs funcionam melhor quando são convidadas a observar, não a mandar.

⸻

📜 Licença

Projeto em fase de PoC / exploração técnica. Licença a definir conforme evolução.
