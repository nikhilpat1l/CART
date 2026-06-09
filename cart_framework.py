#!/usr/bin/env python3
import os
import re
import json
import shlex
import shutil
import subprocess
import asyncio
import uuid
import datetime
import sys
from typing import List, Tuple, Optional, Dict
from pathlib import Path
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# ============================================================
#  Colorful terminal output setup (works on Kali/macOS/Linux)
# ============================================================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

def cprint(text, color=Colors.RESET, bold=False, end='\n'):
    prefix = Colors.BOLD if bold else ''
    sys.stdout.write(f"{prefix}{color}{text}{Colors.RESET}{end}")
    sys.stdout.flush()

def print_banner():
    cprint("╔══════════════════════════════════════════════════════════╗", Colors.CYAN, bold=True)
    cprint("║     🤖  CART – Continuous Automated Red Teaming  🚀      ║", Colors.CYAN, bold=True)
    cprint("║         Autonomous | Self‑Healing | No Limits            ║", Colors.CYAN)
    cprint("╚══════════════════════════════════════════════════════════╝", Colors.CYAN, bold=True)

# ============================================================
#  Configuration
# ============================================================
OPENROUTER_API_KEY = "sk-or-v1----------"
if not OPENROUTER_API_KEY:
    raise ValueError("Please set your OpenRouter API key inside the script at the top")

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

app = FastAPI()
SCAN_SESSIONS = {}
LOG_DIR = Path("./cart_logs")
LOG_DIR.mkdir(exist_ok=True)
MISSING_TOOLS_CACHE: Dict[str, bool] = {}
LLM_FAILURE_LOGGED = False

class ScanGoal(BaseModel):
    goal: str

def get_local_subnet() -> str:
    try:
        result = subprocess.run(["ip", "-4", "route", "list", "default"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "default" in line:
                parts = line.split()
                iface = parts[4] if len(parts) > 4 else None
                if iface:
                    addr_result = subprocess.run(["ip", "-4", "addr", "show", iface], capture_output=True, text=True)
                    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/(\d+)', addr_result.stdout)
                    if match:
                        ip = match.group(1)
                        mask = match.group(2)
                        ip_parts = ip.split('.')
                        subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/{mask}"
                        return subnet
    except:
        pass
    return "192.168.1.0/24"

def ensure_tool_installed(binary_name: str) -> bool:
    if shutil.which(binary_name):
        return True
    if binary_name in MISSING_TOOLS_CACHE:
        return False
    cprint(f"   🔧 Installing missing tool: {binary_name} ...", Colors.YELLOW)
    try:
        subprocess.run(["apt-get", "update"], capture_output=True, check=True, timeout=60)
        result = subprocess.run(["apt-get", "install", "-y", binary_name], capture_output=True, check=False, timeout=300)
        if result.returncode == 0 and shutil.which(binary_name):
            MISSING_TOOLS_CACHE[binary_name] = True
            cprint(f"   ✓ {binary_name} installed successfully.", Colors.GREEN)
            return True
    except:
        pass
    try:
        subprocess.run(["pip3", "install", binary_name], capture_output=True, check=False, timeout=120)
        if shutil.which(binary_name):
            MISSING_TOOLS_CACHE[binary_name] = True
            cprint(f"   ✓ {binary_name} installed via pip.", Colors.GREEN)
            return True
    except:
        pass
    MISSING_TOOLS_CACHE[binary_name] = False
    cprint(f"   ✗ Failed to install {binary_name}", Colors.RED)
    return False

def execute_shell_command(command_str: str, timeout: int = 900) -> Tuple[bool, str, str]:
    try:
        proc = subprocess.run(
            command_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable="/bin/bash"
        )
        return proc.returncode == 0, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout after {timeout}s"
    except Exception as e:
        return False, "", str(e)

def call_llm_with_fallback(messages: List[Dict], max_tokens: int = 800, temperature: float = 0.2):
    global LLM_FAILURE_LOGGED
    models = [
        "meta-llama/llama-3.2-3b-instruct:free",
        "google/gemini-2.0-flash-lite:free",
        "openrouter/free"
    ]
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            content = response.choices[0].message.content
            if content and isinstance(content, str):
                return content
        except Exception as e:
            if not LLM_FAILURE_LOGGED:
                cprint(f"   ⚠ LLM fallback: {model} unavailable, trying next...", Colors.YELLOW)
                LLM_FAILURE_LOGGED = True
    return None

def plan_commands(goal: str) -> List[str]:
    goal_lower = goal.lower()
    subnet = get_local_subnet()
    # ---- Hardcoded command sequences ----
    if "smb" in goal_lower or "null session" in goal_lower or "enum4linux" in goal_lower:
        return [
            f"nmap -sn {subnet} -oG - | awk '/Up$/ {{print $2}}' > live_hosts.txt",
            "while read ip; do echo '=== SMB scan for '$ip' ==='; smbclient -L //$ip -N 2>&1 || enum4linux -a $ip 2>&1 | grep -E 'Sharename|session'; done < live_hosts.txt"
        ]
    if "default credential" in goal_lower or "hydra" in goal_lower or "default password" in goal_lower:
        return [
            f"nmap -sn {subnet} -oG - | awk '/Up$/ {{print $2}}' > live_hosts.txt",
            "while read ip; do hydra -l root -p root ssh://$ip -t 4 -V -f -o hydra_ssh.txt 2>&1; done < live_hosts.txt",
            "while read ip; do hydra -l admin -p admin http-get://$ip -t 4 -V -f -o hydra_http.txt 2>&1; done < live_hosts.txt"
        ]
    if "web" in goal_lower or "gobuster" in goal_lower or "hidden directory" in goal_lower:
        return [
            f"nmap -sn {subnet} -oG - | awk '/Up$/ {{print $2}}' > live_hosts.txt",
            "while read ip; do gobuster dir -u http://$ip -w /usr/share/wordlists/dirb/common.txt -o gobuster_$ip.txt 2>&1; done < live_hosts.txt"
        ]
    if "snmp" in goal_lower or "snmpwalk" in goal_lower:
        return [
            f"nmap -sn {subnet} -oG - | awk '/Up$/ {{print $2}}' > live_hosts.txt",
            "while read ip; do snmpwalk -v2c -c public $ip 2>&1 | head -50; done < live_hosts.txt"
        ]
    if "open port" in goal_lower or "cctv" in goal_lower or "all ports" in goal_lower:
        return [
            f"nmap -sn {subnet} -oG - | awk '/Up$/ {{print $2}}' > live_hosts.txt",
            "while read ip; do nmap -F --min-rate 1000 $ip -oG - | grep -oP '\\d+(?=/open/)' >> open_ports.txt; done < live_hosts.txt",
            f"nmap -sV -p 554,80,443,8080,3702 -iL live_hosts.txt --script=http-title,rtsp-url-brute --open | grep -E '(RTSP|ONVIF|Camera|Hikvision|Dahua|Axis)'"
        ]
    if "arp-scan" in goal_lower or "active ip" in goal_lower:
        return [f"arp-scan --localnet"]
    if "echo" in goal_lower:
        return [goal.split('"')[-2] if '"' in goal else "echo hello world"]
    # ---- LLM fallback ----
    prompt = f"""Output a JSON array of exact command lines for Kali Linux to accomplish this goal:
Goal: {goal}
Example: ["nmap -sV 192.168.1.0/24", "curl http://internal/admin"]
JSON array:"""
    content = call_llm_with_fallback([{"role": "user", "content": prompt}], max_tokens=800)
    if content:
        try:
            json_match = re.search(r'\[\s*".*?"\s*(?:,\s*".*?"\s*)*\]', content, re.DOTALL)
            if json_match:
                commands = json.loads(json_match.group())
                if isinstance(commands, list) and all(isinstance(c, str) for c in commands):
                    return commands
        except:
            pass
    return [f"echo 'No plan for: {goal[:80]}...'"]

def heal_command(failed_command: str, error_output: str) -> str:
    prompt = f"""Fix this command. Output ONLY the corrected command line.
Original: {failed_command}
Error: {error_output}
Corrected:"""
    healed = call_llm_with_fallback([{"role": "user", "content": prompt}], max_tokens=300, temperature=0.2)
    if healed:
        healed = re.sub(r'^```.*?\n|```$', '', healed, flags=re.DOTALL).strip()
        return healed
    return failed_command

def log_session(session_id: str, command: str, attempt: int, stdout: str, stderr: str, success: bool):
    log_file = LOG_DIR / f"{session_id}.log"
    timestamp = datetime.datetime.now().isoformat()
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] CMD: {command}\n")
        f.write(f"[{timestamp}] ATTEMPT: {attempt}\n")
        f.write(f"[{timestamp}] SUCCESS: {success}\n")
        if stdout:
            f.write(f"[{timestamp}] STDOUT:\n{stdout}\n")
        if stderr:
            f.write(f"[{timestamp}] STDERR:\n{stderr}\n")
        f.write("-" * 80 + "\n")

def run_autonomous_redteam(session_id: str, goal: str):
    cprint(f"\n🎯 New session: {session_id}", Colors.BLUE, bold=True)
    cprint(f"📝 Goal: {goal}", Colors.CYAN)
    cprint("🧠 Planning attack sequence...", Colors.YELLOW)
    commands = plan_commands(goal)
    if not commands:
        cprint("✗ No commands generated. Aborting.", Colors.RED)
        return
    cprint(f"✓ Generated {len(commands)} command(s).", Colors.GREEN)
    SCAN_SESSIONS[session_id] = {"status": "running", "commands_total": len(commands), "completed": 0}
    for idx, cmd_str in enumerate(commands, 1):
        cprint(f"\n▶ [{idx}/{len(commands)}] Executing:", Colors.BOLD)
        cprint(f"   $ {cmd_str}", Colors.DIM)
        success = False
        for attempt in range(1, 4):
            # Choose shell or non‑shell execution
            if any(op in cmd_str for op in ["|", ">", ";", "&", "while", "for", "if"]):
                success, stdout, stderr = execute_shell_command(cmd_str, timeout=900)
            else:
                try:
                    argv = shlex.split(cmd_str)
                    proc = subprocess.run(argv, capture_output=True, text=True, timeout=900, shell=False)
                    success = proc.returncode == 0
                    stdout, stderr = proc.stdout, proc.stderr
                except:
                    success, stdout, stderr = execute_shell_command(cmd_str, timeout=900)
            log_session(session_id, cmd_str, attempt, stdout, stderr, success)
            if success:
                cprint(f"   ✓ Success (attempt {attempt})", Colors.GREEN)
                if stdout.strip():
                    cprint("   📄 Output:", Colors.BLUE)
                    for line in stdout.splitlines()[:20]:
                        cprint(f"      {line}", Colors.DIM)
                    if len(stdout.splitlines()) > 20:
                        cprint(f"      ... ({len(stdout.splitlines())-20} more lines)", Colors.DIM)
                break
            else:
                cprint(f"   ✗ Failed (attempt {attempt})", Colors.RED)
                if stderr.strip():
                    cprint(f"   ⚠ Error: {stderr[:200]}", Colors.YELLOW)
                if attempt < 3:
                    healed = heal_command(cmd_str, stderr)
                    cprint(f"   🔄 Healed command: {healed}", Colors.MAGENTA)
                    cmd_str = healed
                else:
                    cprint("   ✗ Command abandoned after 3 attempts.", Colors.RED)
        SCAN_SESSIONS[session_id]["completed"] = idx
    SCAN_SESSIONS[session_id]["status"] = "finished"
    cprint(f"\n✨ Session {session_id} finished. Log saved to {LOG_DIR}/{session_id}.log", Colors.GREEN, bold=True)

# ============================================================
#  FastAPI Endpoints
# ============================================================
@app.post("/scan")
async def scan_endpoint(scan_goal: ScanGoal):
    goal_text = scan_goal.goal.strip()
    if not goal_text:
        raise HTTPException(status_code=400, detail="Goal cannot be empty")
    session_id = str(uuid.uuid4())[:8]
    SCAN_SESSIONS[session_id] = {"status": "queued", "goal": goal_text}
    asyncio.create_task(asyncio.to_thread(run_autonomous_redteam, session_id, goal_text))
    return {"status": "started", "session_id": session_id, "message": "Red teaming started"}

@app.get("/status/{session_id}")
async def status_endpoint(session_id: str):
    if session_id not in SCAN_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    return SCAN_SESSIONS[session_id]

# ============================================================
#  Main
# ============================================================
if __name__ == "__main__":
    print_banner()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
