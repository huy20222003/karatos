import tkinter as tk
import customtkinter as ctk
import os
import sys
import threading
import time
import subprocess
from pathlib import Path
from datetime import datetime

# Add root directory to sys.path to import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from config.settings import settings
from utils.logger import get_logger
from utils.telemetry import telemetry

logger = get_logger()

# Set appearance mode and color theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class SidebarFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_rowconfigure(4, weight=1)  # Bottom spacer
        
        # Logo / Title
        self.logo_label = ctk.CTkLabel(self, text="KARATOS", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Navigation Buttons
        self.home_button = ctk.CTkButton(self, text="Dashboard", command=self.master.show_home, 
                                        fg_color="transparent", text_color=("gray10", "gray90"), 
                                        hover_color=("gray70", "gray30"), anchor="w")
        self.home_button.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.settings_button = ctk.CTkButton(self, text="Settings", command=self.master.show_settings, 
                                            fg_color="transparent", text_color=("gray10", "gray90"), 
                                            hover_color=("gray70", "gray30"), anchor="w")
        self.settings_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        
        self.logs_button = ctk.CTkButton(self, text="Logs", command=self.master.show_logs, 
                                        fg_color="transparent", text_color=("gray10", "gray90"), 
                                        hover_color=("gray70", "gray30"), anchor="w")
        self.logs_button.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        # Appearance Mode
        self.appearance_mode_label = ctk.CTkLabel(self, text="Appearance Mode:", anchor="w")
        self.appearance_mode_label.grid(row=5, column=0, padx=20, pady=(10, 0))
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(self, values=["Light", "Dark", "System"],
                                                               command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=6, column=0, padx=20, pady=(10, 10))
        self.appearance_mode_optionemenu.set("Dark")

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

class HomeFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.label = ctk.CTkLabel(self, text="Agent Dashboard", font=ctk.CTkFont(size=24, weight="bold"))
        self.label.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        # 1. Stats Container (NOW AT TOP)
        self.stats_frame = ctk.CTkFrame(self)
        self.stats_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.stats_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self._create_stat_card(self.stats_frame, "Pulse", "STABLE", 0, 0, "pulse")
        self._create_stat_card(self.stats_frame, "Avg Response", "0s", 1, 0, "latency")
        self._create_stat_card(self.stats_frame, "Uptime", "0h 0m", 2, 0, "uptime")
        
        self._create_stat_card(self.stats_frame, "Total Tokens", "0", 0, 1, "tokens")
        self._create_stat_card(self.stats_frame, "Memory Units", "0", 1, 1, "memory")
        self._create_stat_card(self.stats_frame, "Skills Active", "0", 2, 1, "skills")
        
        # 2. Compact LED Status Row
        # ... (rest of led_frame stays same)
        
        # 2. Compact LED Status Row
        self.led_frame = ctk.CTkFrame(self, height=40)
        self.led_frame.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        
        # Centering the tiny row
        self.led_inner = ctk.CTkFrame(self.led_frame, fg_color="transparent")
        self.led_inner.pack(pady=5)
        
        self.led_brain = self._create_led(self.led_inner, "Brain Hub", 0)
        self.led_telegram = self._create_led(self.led_inner, "Telegram", 1)
        self.led_db = self._create_led(self.led_inner, "Database", 2)

        # 3. Chart Area
        self.chart_frame = ctk.CTkFrame(self)
        self.chart_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        self.grid_rowconfigure(3, weight=2)
        
        self.token_chart_label = ctk.CTkLabel(self.chart_frame, text="Neural Activity (Tokens)", font=ctk.CTkFont(size=12, weight="bold"))
        self.token_chart_label.grid(row=0, column=0, padx=10, pady=(5, 0))
        
        self.latency_chart_label = ctk.CTkLabel(self.chart_frame, text="Latency Trend (Seconds)", font=ctk.CTkFont(size=12, weight="bold"))
        self.latency_chart_label.grid(row=0, column=1, padx=10, pady=(5, 0))
        
        self.token_canvas = tk.Canvas(self.chart_frame, background="#2b2b2b", highlightthickness=0, height=120)
        self.token_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        self.latency_canvas = tk.Canvas(self.chart_frame, background="#2b2b2b", highlightthickness=0, height=120)
        self.latency_canvas.grid(row=1, column=1, sticky="nsew", padx=10, pady=5)
        
        self.chart_frame.grid_columnconfigure((0, 1), weight=1)
        
        self.update_real_stats()
        self.after(2000, self._draw_charts_loop)
        
        # Bottom area for control (Moved from 3 to 4)
        self.control_frame = ctk.CTkFrame(self, height=80)
        self.control_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        
        self.start_button = ctk.CTkButton(self.control_frame, text="Start Agent", fg_color="green", 
                                        hover_color="darkgreen", command=self.master.start_agent)
        self.start_button.pack(side="left", padx=20, pady=20)
        
        self.stop_button = ctk.CTkButton(self.control_frame, text="Stop Agent", fg_color="red", 
                                        hover_color="darkred", command=self.master.stop_agent)
        self.stop_button.pack(side="left", padx=20, pady=20)

    def _create_led(self, master, label_text, column):
        container = ctk.CTkFrame(master, fg_color="transparent")
        container.pack(side="left", padx=20)
        
        led = ctk.CTkLabel(container, text="●", font=ctk.CTkFont(size=20), text_color="gray")
        led.pack(side="left", padx=2)
        
        lbl = ctk.CTkLabel(container, text=label_text, font=ctk.CTkFont(size=11))
        lbl.pack(side="left")
        return led

    def _draw_simulated_chart(self):
        """Draw a simple line chart for visual aesthetics."""
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width <= 1: return # Not yet rendered
        
        points = [40, 60, 45, 80, 55, 90, 70, 100, 85, 110, 95, 120]
        max_p = max(points)
        
        # Draw background lines
        for i in range(1, 4):
            y = height - (height / 4 * i)
            self.canvas.create_line(0, y, width, y, fill="#3d3d3d", dash=(4, 4))
            
        step = width / (len(points) - 1)
        for i in range(len(points) - 1):
            x1 = i * step
            y1 = height - (points[i] / max_p * (height - 20)) - 10
            x2 = (i + 1) * step
            y2 = height - (points[i+1] / max_p * (height - 20)) - 10
            self.canvas.create_line(x1, y1, x2, y2, fill="#1f538d", width=3, smooth=True)
            self.canvas.create_oval(x2-3, y2-3, x2+3, y2+3, fill="#1f538d", outline="")

    def set_led_status(self, component, status):
        color = "green" if status else "red"
        if component == "brain": self.led_brain.configure(text_color=color)
        if component == "telegram": self.led_telegram.configure(text_color=color)
        if component == "db": self.led_db.configure(text_color=color)

    def _create_stat_card(self, master, title, value, column, row, key):
        card = ctk.CTkFrame(master)
        card.grid(row=row, column=column, padx=10, pady=10, sticky="nsew")
        
        title_label = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12))
        title_label.pack(pady=(10, 0))
        
        value_label = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=20, weight="bold"))
        value_label.pack(pady=(0, 10))
        
        if not hasattr(self, "stat_labels"): self.stat_labels = {}
        self.stat_labels[key] = value_label

    def update_real_stats(self):
        """Update cards with real data from telemetry and filesystem."""
        stats = telemetry.get_stats()
        
        # 1. Update from telemetry
        if "tokens" in self.stat_labels: self.stat_labels["tokens"].configure(text=stats["tokens"])
        if "latency" in self.stat_labels: self.stat_labels["latency"].configure(text=stats["latency"])
        if "uptime" in self.stat_labels: self.stat_labels["uptime"].configure(text=stats["uptime"])
        
        # 2. Update Pulse
        is_running = self.master.agent_process is not None and self.master.agent_process.poll() is None
        if "pulse" in self.stat_labels: self.stat_labels["pulse"].configure(text="ACTIVE" if is_running else "IDLE")
        
        # 3. Scan Filesystem for Memory & Skills
        try:
            skill_base = Path("skills/definitions")
            if skill_base.exists():
                skill_count = len([d for d in os.listdir(skill_base) 
                                 if os.path.isdir(skill_base / d) and not d.startswith("_")])
                if "skills" in self.stat_labels: self.stat_labels["skills"].configure(text=str(skill_count))
            
            # Count markdown files in memory subdirs
            mem_count = 0
            # Try multiple common paths
            for p in ["data/storage/memory", "data/memory", "memory"]:
                path = Path(p)
                if path.exists():
                    for root, _, files in os.walk(path):
                        mem_count += len([f for f in files if f.endswith(".md")])
            if "memory" in self.stat_labels: self.stat_labels["memory"].configure(text=str(mem_count))
        except Exception:
            pass

        self.after(5000, self.update_real_stats)

    def _draw_charts_loop(self):
        self._draw_canvas_chart(self.token_canvas, "tokens", "#1f538d")
        self._draw_canvas_chart(self.latency_canvas, "latency", "#e07a5f")
        self.after(5000, self._draw_charts_loop)

    def _draw_canvas_chart(self, canvas, data_key, color):
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1: return
        
        history = telemetry.data.get("history", [])
        if not history:
            # Draw placeholder line
            canvas.create_line(0, height/2, width, height/2, fill="#3d3d3d", dash=(4, 4))
            return
            
        points = [h.get(data_key, 0) for h in history]
        if len(points) < 2: points = [0] + points
        
        max_p = max(points) if max(points) > 0 else 1
        
        # Background lines
        for i in range(1, 4):
            y = height - (height / 4 * i)
            canvas.create_line(0, y, width, y, fill="#3d3d3d", dash=(2, 2))
            
        step = width / (len(points) - 1)
        for i in range(len(points) - 1):
            x1 = i * step
            y1 = height - (points[i] / max_p * (height - 20)) - 10
            x2 = (i + 1) * step
            y2 = height - (points[i+1] / max_p * (height - 20)) - 10
            canvas.create_line(x1, y1, x2, y2, fill=color, width=2, smooth=True)

class SettingsFrame(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.label = ctk.CTkLabel(self, text="System Configurations", font=ctk.CTkFont(size=24, weight="bold"))
        self.label.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        self.entries = {}
        self.blacklist = ["MEMORY_KEY", "MCP_CONFIG_PATH", "LOG_DIR", "LOG_LEVEL", "OLLAMA_HEADERS", "DATABASE_URL"]
        
        self.load_dynamic_settings()

    def load_dynamic_settings(self):
        # Clear existing entries if any
        for widget in self.winfo_children():
            if widget != self.label:
                widget.destroy()
        self.entries = {}
        
        # Read .env to get all available keys
        env_keys = []
        env_path = Path(".env")
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        key = line.split("=")[0].strip()
                        if key and key not in self.blacklist:
                            env_keys.append(key)
        
        # Grouping logic
        sections = {}
        for key in env_keys:
            prefix = key.split("_")[0] if "_" in key else "GENERAL"
            if prefix not in sections: sections[prefix] = []
            sections[prefix].append(key)
            
        row = 1
        for section, keys in sorted(sections.items()):
            # Section Header
            section_label = ctk.CTkLabel(self, text=f" {section} PARAMS ", font=ctk.CTkFont(size=14, weight="bold"), 
                                        fg_color="#1f538d", corner_radius=5)
            section_label.grid(row=row, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="ew")
            row += 1
            
            for key in sorted(keys):
                # Readable label (remove prefix if matches section)
                label_text = key.replace(f"{section}_", "").replace("_", " ").title()
                if not label_text: label_text = key
                
                label = ctk.CTkLabel(self, text=label_text, font=ctk.CTkFont(size=12))
                label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
                
                entry = ctk.CTkEntry(self, width=400)
                # Get current value
                current_val = os.getenv(key, str(getattr(settings, key.lower(), "")))
                entry.insert(0, str(current_val))
                entry.grid(row=row, column=1, padx=20, pady=5, sticky="ew")
                
                self.entries[key] = entry
                row += 1
                
        self.save_button = ctk.CTkButton(self, text="Sync & Commit to .env", command=self.save_settings,
                                         fg_color="#28a745", hover_color="#218838")
        self.save_button.grid(row=row, column=0, columnspan=2, padx=20, pady=30)

    def save_settings(self):
        updates = {key: entry.get() for key, entry in self.entries.items()}
        try:
            settings.save_to_env(updates)
            # Force refresh to show new keys if any
            # self.load_dynamic_settings() 
            tk.messagebox.showinfo("Karatos Sync", "Environment updated and committed to .env successfully.")
        except Exception as e:
            tk.messagebox.showerror("Sync Error", f"Failed to save settings: {e}")

class LogsFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.label = ctk.CTkLabel(self, text="System Logs", font=ctk.CTkFont(size=24, weight="bold"))
        self.label.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        self.log_textbox = ctk.CTkTextbox(self, state="disabled")
        self.log_textbox.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Karatos Agent Manager")
        self.geometry("1100x600")
        
        # Process and Threading State
        self.agent_process = None
        self.stop_logging = threading.Event()
        self.log_thread = None

        # Set up grid layout (1x2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Create sidebar
        self.sidebar = SidebarFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Create frames for pages
        self.home_frame = HomeFrame(self, corner_radius=0, fg_color="transparent")
        self.settings_frame = SettingsFrame(self, corner_radius=0, fg_color="transparent")
        self.logs_frame = LogsFrame(self, corner_radius=0, fg_color="transparent")

        # Show default page
        self.show_home()
        
        # Check initial status
        self.after(1000, self.update_status_loop)

    def start_agent(self):
        if self.agent_process and self.agent_process.poll() is None:
            tk.messagebox.showwarning("Warning", "Agent is already running!")
            return
            
        try:
            self._is_starting_agent = True
            # Simple start: standard python command
            # Using CREATE_NEW_PROCESS_GROUP is required on Windows to send CTRL_C_EVENT
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

            self.agent_process = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creation_flags
            )
            
            # Start log streaming if not running
            if not self.log_thread:
                self.start_log_stream()
                
            self.home_frame.set_led_status("brain", True)
            logger.info("[GUI] Agent started via GUI")
            
        except Exception as e:
            tk.messagebox.showerror("Error", f"Failed to start agent: {e}")

    def stop_agent(self):
        if not self.agent_process or self.agent_process.poll() is not None:
            tk.messagebox.showwarning("Warning", "Agent is not running.")
            return
            
        try:
            # --- NGO FIX: Use SIGINT (Ctrl+C) for graceful shutdown, matching user request ---
            if sys.platform == "win32":
                import signal
                # Sending CTRL_C_EVENT to the process group
                os.kill(self.agent_process.pid, signal.CTRL_C_EVENT)
                logger.info(f"[GUI] Sent CTRL_C_EVENT to PID {self.agent_process.pid}")
            else:
                self.agent_process.send_signal(signal.SIGINT)
            
            # Wait for it to exit (Graceful)
            try:
                self.agent_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("[GUI] Agent did not stop via SIGINT, force killing...")
                self.agent_process.kill()

            self.home_frame.set_led_status("brain", False)
            self._is_starting_agent = False
            logger.info("[GUI] Agent stopped successfully.")
        except Exception as e:
            if self.agent_process:
                self.agent_process.kill()
            self.home_frame.set_led_status("brain", False)
            logger.error(f"[GUI] Force killed agent: {e}")

    def start_log_stream(self):
        self.stop_logging.clear()
        self.log_thread = threading.Thread(target=self._tail_logs, daemon=True)
        self.log_thread.start()

    def _tail_logs(self):
        """Monitor the subprocess stdout and newest log file."""
        while not self.stop_logging.is_set():
            if self.agent_process and self.agent_process.poll() is None:
                line = self.agent_process.stdout.readline()
                if line:
                    self.update_log_ui(line)
            else:
                time.sleep(1)

    def update_log_ui(self, message):
        """Thread-safe UI update for logs."""
        self.after(0, lambda: self._append_to_log_textbox(message))

    def _append_to_log_textbox(self, message):
        self.logs_frame.log_textbox.configure(state="normal")
        self.logs_frame.log_textbox.insert("end", message)
        self.logs_frame.log_textbox.see("end")
        self.logs_frame.log_textbox.configure(state="disabled")

    def update_status_loop(self):
        """Periodically check if agent is running and update LEDs and Buttons."""
        is_running = self.agent_process is not None and self.agent_process.poll() is None
        is_starting = getattr(self, "_is_starting_agent", False)
        
        # Reset starting flag once running
        if is_running:
            self._is_starting_agent = False

        self.home_frame.set_led_status("brain", is_running)
        
        # Disable/Enable buttons based on status
        if is_running:
            self.home_frame.start_button.configure(state="disabled", text="RUNNING")
            self.home_frame.stop_button.configure(state="normal")
        elif is_starting:
            self.home_frame.start_button.configure(state="disabled", text="STARTING...")
            self.home_frame.stop_button.configure(state="disabled")
        else:
            self.home_frame.start_button.configure(state="normal", text="Start Agent")
            self.home_frame.stop_button.configure(state="disabled")
        
        # In a real app, we'd check DB and Telegram connectivity too
        # For now, simplistic mapping:
        self.home_frame.set_led_status("telegram", is_running)
        self.home_frame.set_led_status("db", True) # Assuming DB is always up
        
        self.after(2000, self.update_status_loop)

    def show_home(self):
        self._hide_all_frames()
        self.home_frame.grid(row=0, column=1, sticky="nsew")
        self.sidebar.home_button.configure(fg_color=("gray75", "gray25"))

    def show_settings(self):
        self._hide_all_frames()
        self.settings_frame.grid(row=0, column=1, sticky="nsew")
        self.sidebar.settings_button.configure(fg_color=("gray75", "gray25"))

    def show_logs(self):
        self._hide_all_frames()
        self.logs_frame.grid(row=0, column=1, sticky="nsew")
        self.sidebar.logs_button.configure(fg_color=("gray75", "gray25"))

    def _hide_all_frames(self):
        self.home_frame.grid_forget()
        self.settings_frame.grid_forget()
        self.logs_frame.grid_forget()
        # Reset colors
        self.sidebar.home_button.configure(fg_color="transparent")
        self.sidebar.settings_button.configure(fg_color="transparent")
        self.sidebar.logs_button.configure(fg_color="transparent")

if __name__ == "__main__":
    app = App()
    app.mainloop()
