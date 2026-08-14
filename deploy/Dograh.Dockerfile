FROM ghcr.io/dograh-hq/dograh-api:latest

USER root

# Sarvam sometimes streams an identical second empty JSON object for a
# no-argument tool call ("{}{}"). Accept only that exact duplication.
COPY deploy/dograh/base_llm.py /opt/venv/lib/python3.13/site-packages/pipecat/services/openai/base_llm.py
COPY deploy/dograh/gemini_live.py /app/api/services/pipecat/realtime/gemini_live.py
COPY deploy/dograh/telnyx_provider.py /app/api/services/telephony/providers/telnyx/provider.py
COPY deploy/dograh/telnyx_transport.py /app/api/services/telephony/providers/telnyx/transport.py
RUN /opt/venv/bin/python3 -m py_compile /opt/venv/lib/python3.13/site-packages/pipecat/services/openai/base_llm.py
RUN /opt/venv/bin/python3 -m py_compile /app/api/services/pipecat/realtime/gemini_live.py
RUN /opt/venv/bin/python3 -m py_compile /app/api/services/telephony/providers/telnyx/provider.py /app/api/services/telephony/providers/telnyx/transport.py

USER dograh
