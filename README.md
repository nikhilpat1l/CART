# CART
You are looking at CART (Continuous Automated Red Teaming) – an autonomous, self‑healing framework that turns a plain‑text goal into a sequence of Kali Linux commands, executes them, and automatically recovers from failures without human intervention

**Core Capabilities**


**Goal → Action**
You provide any natural language goal (e.g., “Find all open ports on my network and check for CCTV cameras”). The tool internally uses an LLM (via OpenRouter) to translate that into a structured array of bash commands. If the LLM fails or is rate‑limited, a hardcoded fallback system detects keywords (smb, null session, web, cctv, default credentials, etc.) and injects a proven command sequence.

**Autonomous Execution**

Runs commands in a sandboxed process (non‑shell for simple commands, shell for pipelines/loops).

Automatically installs missing Kali tools via apt-get or pip3.

Supports complex constructs: pipes, redirections, while loops, for loops, conditionals.

**Self‑Healing**

If a command fails, the tool captures stderr and sends it to a fallback LLM (or another model) to rewrite the command.

Up to 3 healing attempts per command.

If all LLMs are unavailable, the tool falls back to a correct hardcoded version of the command (e.g., changing cut to awk).

**No Limits**

No whitelist of allowed binaries.

No target restrictions (you can scan any IP or domain – only use on your own infrastructure).

Can run any tool or install any package.

Full root privileges required for low‑level network operations.

Network Discovery

Auto‑detects your local subnet from your default network interface.

Performs host discovery (nmap -sn, arp-scan).

Fast port scanning (nmap -F for top 100 ports, or -p- for all ports).

Service version detection and script scanning.

Red Teaming Modules (Hardcoded)

SMB null session enumeration – checks for anonymous shares using smbclient and enum4linux.

Default credentials – tests common admin passwords on SSH, HTTP, FTP.

Web directory brute‑forcing – uses gobuster with common wordlists.

SNMP enumeration – queries public community strings.

CCTV / IP camera detection – looks for RTSP (554), HTTP camera endpoints, ONVIF (3702).

Full network penetration test simulation – discovery → port scan → vulnerability scripts → optional Metasploit.

Beautiful Terminal UI

Color‑coded output (green for success, red for errors, yellow for warnings).

Progress indicators, session IDs, and live log tailing.

Clean banners and section headers.

API‑First Design

FastAPI endpoint POST /scan accepts a JSON {"goal": "..."}.

Returns a session ID.

GET /status/{session_id} returns progress.

Logs every command, attempt, stdout, stderr to ./cart_logs/<session_id>.log.

Example Goals It Can Handle
Goal	What It Does
“Enumerate SMB shares on my network”	Discovers live hosts, then runs smbclient -L //ip -N and enum4linux to list accessible shares and null session status.
“Find all open ports and identify CCTV cameras”	Full port scan (fast mode) then service detection on CCTV‑relevant ports.
“Test for default credentials on SSH and HTTP”	Uses hydra to try root:root and admin:admin on live hosts.
“Brute‑force hidden web directories”	Runs gobuster on each live web server.
“Simulate an internal penetration test”	Multi‑step: discovery → full port scan → vulnerability scripts → Metasploit autopwn.
Why It’s Impressive for an AI Audience
Resilient to LLM failure – hardcoded keyword‑based fallback guarantees that even if all API calls fail, the right commands still run.

No hardcoded IPs – auto‑detects the local subnet.

Self‑healing at the command level – not just retrying, but actually rewriting broken syntax.

No human in the loop – from a one‑sentence goal to a completed red team exercise.

Beautiful and debuggable – colorful logs, session persistence, and full transparency.

In short: Give it a sentence, and it will own the network (the one you own).



<img width="1366" height="768" alt="tool4" src="https://github.com/user-attachments/assets/8d4507f8-9e0e-4864-82fe-0763c9e747c3" />
<img width="1364" height="768" alt="tool3" src="https://github.com/user-attachments/assets/78e674c2-b623-4ff4-bea7-6e91642f3a58" />
<img width="1366" height="768" alt="tool2" src="https://github.com/user-attachments/assets/065b91c7-9def-4b38-a749-b9657a297ece" />
<img width="1361" height="658" alt="tool1" src="https://github.com/user-attachments/assets/0174f90f-9fb3-463f-9350-490c6c43082d" />
