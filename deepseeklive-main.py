# -*- coding: utf-8 -*-
import asyncio
import os
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import importlib.util
import soundcard as sc
import datetime
import ctypes  # <--- 【新增】引入 Windows 底层核心 API 库
import time    # <--- 【新增】引入时间库用于构造唯一临时标题


# =========================================================
# 本地防错机制：不再依赖外部 config 脚本的函数，防止因文件覆盖不全崩溃
# =========================================================
CONFIG_FILE = "deepseeklive-config.json"

def get_provider_key_name(provider: str) -> str:
    if provider == "gemini": return "gemini_api_key"
    if provider == "deepseek": return "deepseek_api_key"
    if provider == "qwen": return "qwen_api_key"
    return "gemini_api_key"

def get_default_config():
    return {
        "api_key": "",  
        "gemini_api_key": "",
        "deepseek_api_key": "",
        "qwen_api_key": "",
        "model_type": "gemini",
        "model_name": "gemini-2.5-flash",
        "embedding_model": "Chroma-Default",
        "listening_mode": "scrcpy系统声音(Android)",
        "chroma_collection": "tech_interview_knowledge",  
        "distance_threshold": 1.3,
        "trigger_mode": "RAG and 问句 and 技术关键词"  # 【新增】默认判定模式
    }

current_dir = os.path.dirname(os.path.abspath(__file__))

try:
    # 1. 动态加载配置模块（保留它以供 pipeline 脚本读取硬件/路径常量）
    cfg_path = os.path.join(current_dir, "deepseeklive-config.py")
    spec_cfg = importlib.util.spec_from_file_location("advanced_config", cfg_path)
    cfg = importlib.util.module_from_spec(spec_cfg)
    spec_cfg.loader.exec_module(cfg)

    # 2. 动态加载核心流水线模块
    pipe_path = os.path.join(current_dir, "deepseeklive-pipeline.py")
    spec_pipe = importlib.util.spec_from_file_location("advanced_pipeline", pipe_path)
    pipe = importlib.util.module_from_spec(spec_pipe)
    spec_pipe.loader.exec_module(pipe)
    
    print(">>> [SUCCESS] 核心业务引擎脚本动态加载成功！")
except Exception as e:
    print("\n" + "!"*60)
    print("【加载失败】请确认当前运行目录中是否存在相关的脚本，或检查 Conda 环境依赖库是否完整！")
    print("!"*60 + "\n")
    raise e

gui_log_queue = queue.Queue()

class QueueTextRedirector:
    def write(self, string):
        if string:
            gui_log_queue.put(string)
    def flush(self):
        pass

try:
    speaker = sc.default_speaker()
    print(f">>> 当前系统默认播放设备: {speaker}")
except Exception as e:
    print(f">>> 硬件检测警告: {e}")


class AppGUI:
    def __init__(self, root):
        self.root = root
        
        # =========================================================
        # 【核心修改点 1】：生成全局唯一的临时标题，协助 Win32 API 精准定位真实的系统 HWND
        # =========================================================
        self.unique_id = f"SECURE_MAGIC_WINDOW_{int(time.time())}"
        self.root.title(self.unique_id)
        
        self.root.geometry("760x650")  # 【微调】小幅增加窗口初始高度，完美容纳新增的控制行
        # =========================================================
        # 【核心修改点】：开启窗口永远置顶属性
        # 配合任务栏隐藏使用，使其切换到其他窗口（游戏/网页）时依然悬浮可见
        # =========================================================
        self.root.attributes("-topmost", True)
        self.loop_thread = None
        self.is_running = False

        # 【新增：行首状态标记】用于判断当前是否需要打印时间戳
        self.at_start_of_line = True

        self.config = self.load_config()
        self.current_provider = self.config.get("model_type", "gemini")
        self.create_widgets()
        
        # =========================================================
        # 【核心修改点 2】：强制 Tkinter 率先完成布局渲染并生成顶级窗口句柄
        # =========================================================
        self.root.update()
        
        # =========================================================
        # 【核心修改点 3】：注入商业级防 OBS 独立采集链 + 任务栏图标彻底隐形
        # =========================================================
        self.apply_advanced_anti_obs()
        
        # 还原为其原本期望的真实控制台标题
        self.root.title("OVERMIND")
        
        # 界面安全初始化通过后，再接管输出流
        sys.stdout = QueueTextRedirector()
        sys.stderr = QueueTextRedirector()
        self.poll_logs()

    def apply_advanced_anti_obs(self):
        """跨越 Tkinter 组件壁垒，接管顶级 DWM 渲染树进行防 OBS 拦截与任务栏隐藏"""
        try:
            # 1. 跨过 Tkinter 内部框架，在 Windows 系统树中打捞真正的顶级 HWND 句柄
            true_hwnd = ctypes.windll.user32.FindWindowW(None, self.unique_id)
            if not true_hwnd:
                tk_hwnd = self.root.winfo_id()
                true_hwnd = ctypes.windll.user32.GetAncestor(tk_hwnd, 2) # GA_ROOT = 2

            if true_hwnd:
                # 2. 注入工具窗口样式 (WS_EX_TOOLWINDOW = 0x00000080)，使程序在任务栏/Alt+Tab中彻底消失
                GWL_EXSTYLE = -20
                WS_EX_TOOLWINDOW = 0x00000080
                
                old_style = ctypes.windll.user32.GetWindowLongW(true_hwnd, GWL_EXSTYLE)
                new_style = old_style | WS_EX_TOOLWINDOW
                ctypes.windll.user32.SetWindowLongW(true_hwnd, GWL_EXSTYLE, new_style)
                
                # 刷新窗口的样式框架以应用任务栏隐藏
                # SWP_FRAMECHANGED = 0x0020, SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_NOZORDER=4
                ctypes.windll.user32.SetWindowPos(true_hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)

                # 3. 注入 DWM 最高安全防御指令 (WDA_EXCLUDEFROMCAPTURE = 0x00000011)
                # 强行让系统在输出视频流给 OBS/屏幕分享时，直接挖空本窗口坐标区域
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                result = ctypes.windll.user32.SetWindowDisplayAffinity(true_hwnd, WDA_EXCLUDEFROMCAPTURE)
                
                if result:
                    print(">>> [SECURITY] 任务栏缩略图已成功剥离，且防 OBS 采集链注入成功！")
                else:
                    print(">>> [SECURITY 警告] 亲和性指令被系统拒绝。")
            else:
                print(">>> [SECURITY 错误] 未能定位到当前窗口在 Windows 中的顶级句柄。")
        except Exception as e:
            print(f">>> [SECURITY 错误] 注入底层样式发生异常: {e}")

    def load_config(self):
        default = get_default_config()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                default.update(loaded)
                legacy_api_key = loaded.get("api_key", "")
                has_new_keys = any(loaded.get(k, "") for k in ("gemini_api_key", "deepseek_api_key", "qwen_api_key"))
                if legacy_api_key and not has_new_keys:
                    provider = loaded.get("model_type", "gemini")
                    default[get_provider_key_name(provider)] = legacy_api_key
                    default["api_key"] = legacy_api_key
            except Exception:
                pass
        return default

    def _store_current_api_key(self):
        provider = self.current_provider or self.model_type_cmb.get()
        current_key = self.api_key_ent.get().strip()
        key_name = get_provider_key_name(provider)
        self.config[key_name] = current_key
        self.config["api_key"] = current_key

    def on_model_type_changed(self, event=None):
        self._store_current_api_key()
        self.current_provider = self.model_type_cmb.get()
        self.config["model_type"] = self.current_provider
        self.refresh_api_key_display()

    def refresh_api_key_display(self, event=None):
        provider = self.model_type_cmb.get()
        key_name = get_provider_key_name(provider)
        key = self.config.get(key_name, "")
        self.api_key_ent.delete(0, tk.END)
        self.api_key_ent.insert(0, key)

    def get_chroma_collections(self):
        """【新增组件函数】动态扫描当前工作目录下 chroma_db 中现有的所有数据库集合名称"""
        collections = ["tech_interview_knowledge"] # 兜底默认值
        try:
            import chromadb
            if os.path.exists("chroma_db"):
                client = chromadb.PersistentClient(path="chroma_db")
                cols = client.list_collections()
                for c in cols:
                    if c.name not in collections:
                        collections.append(c.name)
        except Exception:
            pass
        return collections

    def save_config(self):
        self._store_current_api_key()
        self.config["model_type"] = self.model_type_cmb.get()
        self.config["model_name"] = self.model_name_ent.get().strip()
        self.config["embedding_model"] = self.embed_model_cmb.get()
        self.config["listening_mode"] = self.listen_mode_cmb.get()
        
        # 【新增】：从图形下拉/输入框内捕获最新的参数
        self.config["chroma_collection"] = self.chroma_coll_cmb.get().strip()
        self.config["trigger_mode"] = self.trigger_mode_cmb.get() # 【新增】捕获问句触发模式
        try:
            self.config["distance_threshold"] = float(self.dist_thresh_ent.get().strip())
        except ValueError:
            self.config["distance_threshold"] = 1.3 # 转换失败时默认兜底

        self.current_provider = self.config["model_type"]

        # 【核心同步点】：实时更新动态载入的内存 cfg 模块属性，让下游 pipeline 引擎立即生效
        if 'cfg' in globals() or 'cfg' in sys.modules:
            try:
                cfg.DISTANCE_THRESHOLD = float(self.config["distance_threshold"])
                cfg.CHROMA_COLLECTION = self.config["chroma_collection"]
            except Exception:
                pass

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

        with open(".env", "w", encoding="utf-8") as f:
            f.write(f"GOOGLE_API_KEY={self.config.get('gemini_api_key', '')}\n")
            f.write(f"DEEPSEEK_API_KEY={self.config.get('deepseek_api_key', '')}\n")
            f.write(f"QWEN_API_KEY={self.config.get('qwen_api_key', '')}\n")

    def create_widgets(self):
        cfg_frame = ttk.LabelFrame(self.root, text=" 核心配置面板 ", padding=10)
        cfg_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(cfg_frame, text="API Key:").grid(row=0, column=0, sticky="w", pady=5)
        self.api_key_ent = ttk.Entry(cfg_frame, width=45, show="*")
        self.api_key_ent.grid(row=0, column=1, columnspan=3, sticky="w", padx=5)

        ttk.Label(cfg_frame, text="模型提供商:").grid(row=1, column=0, sticky="w", pady=5)
        self.model_type_cmb = ttk.Combobox(cfg_frame, values=["gemini", "deepseek", "qwen"], width=12, state="readonly")
        self.model_type_cmb.set(self.config.get("model_type", "gemini"))
        self.model_type_cmb.grid(row=1, column=1, sticky="w", padx=5)
        self.model_type_cmb.bind("<<ComboboxSelected>>", self.on_model_type_changed)

        ttk.Label(cfg_frame, text="模型名称:").grid(row=1, column=2, sticky="w", padx=10)
        self.model_name_ent = ttk.Entry(cfg_frame, width=22)
        self.model_name_ent.insert(0, self.config.get("model_name", "gemini-2.5-flash"))
        self.model_name_ent.grid(row=1, column=3, sticky="w")

        ttk.Label(cfg_frame, text="嵌入模型:").grid(row=2, column=0, sticky="w", pady=5)
        self.embed_model_cmb = ttk.Combobox(cfg_frame, values=["Chroma-Default", "text-embedding-3-small"], width=15, state="readonly")
        self.embed_model_cmb.set(self.config.get("embedding_model", "Chroma-Default"))
        self.embed_model_cmb.grid(row=2, column=1, sticky="w", padx=5)

        ttk.Label(cfg_frame, text="声音捕捉源:").grid(row=2, column=2, sticky="w", padx=10)
        self.listen_mode_cmb = ttk.Combobox(
            cfg_frame,
            values=["scrcpy系统声音(Android)", "scrcpy麦克风(Android)", "本机麦克风(PC)", "本机系统声音(PC)"],
            width=22,
            state="readonly"
        )
        self.listen_mode_cmb.set(self.config.get("listening_mode", "scrcpy系统声音(Android)"))
        self.listen_mode_cmb.grid(row=2, column=3, sticky="w")

        # =====================================================================
        # 【新增 Row 3 控制流】ChromaDB 数据库集合下拉项（可自选或自行输入）与距离阈值输入框
        # =====================================================================
        ttk.Label(cfg_frame, text="ChromaDB集合:").grid(row=3, column=0, sticky="w", pady=5)
        chroma_vals = self.get_chroma_collections()
        self.chroma_coll_cmb = ttk.Combobox(cfg_frame, values=chroma_vals, width=15)
        self.chroma_coll_cmb.set(self.config.get("chroma_collection", "tech_interview_knowledge"))
        self.chroma_coll_cmb.grid(row=3, column=1, sticky="w", padx=5)

        ttk.Label(cfg_frame, text="距离阈值:").grid(row=3, column=2, sticky="w", padx=10)
        self.dist_thresh_ent = ttk.Entry(cfg_frame, width=24)
        self.dist_thresh_ent.insert(0, str(self.config.get("distance_threshold", 1.3)))
        self.dist_thresh_ent.grid(row=3, column=3, sticky="w")
        # =====================================================================
        # =====================================================================
        # 【新增 Row 4 控制流】问句触发判定模式选择器
        # =====================================================================
        ttk.Label(cfg_frame, text="判定模式:").grid(row=4, column=0, sticky="w", pady=5)
        self.trigger_mode_cmb = ttk.Combobox(cfg_frame, values=[
            "RAG and 问句 and 技术关键词",
            "RAG and 问句",
            "问句",
            "技术关键词 and 问句"
        ], width=25, state="readonly")
        self.trigger_mode_cmb.set(self.config.get("trigger_mode", "RAG and 问句 and 技术关键词"))
        self.trigger_mode_cmb.grid(row=4, column=1, columnspan=2, sticky="w", padx=5)
        # =====================================================================

        btn_frame = ttk.Frame(self.root, padding=5)
        btn_frame.pack(fill="x", padx=10)

        self.start_btn = ttk.Button(btn_frame, text="🔒 保存配置并开启监听", command=self.start_pipeline)
        self.start_btn.pack(side="left", padx=5)

        # 【新增】急停按钮组件，初始状态为禁用
        self.stop_btn = ttk.Button(btn_frame, text="🛑 终止监听", command=self.stop_pipeline, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        # =====================================================================
        btn_frame = ttk.Frame(self.root, padding=5)
        btn_frame.pack(fill="x", padx=10)

        # self.start_btn = ttk.Button(btn_frame, text="🔒 保存配置并开启监听", command=self.start_pipeline)
        # self.start_btn.pack(side="left", padx=5)

        log_frame = ttk.LabelFrame(self.root, text=" 实时状态监控（Console Logs） ")
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_text = tk.Text(log_frame, bg="#1e1e1e", fg="#d4d4d4", insertbackground="white", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        self.refresh_api_key_display()

    def poll_logs(self):
        """定时从队列中提取 print 的内容刷新到 Text 控件中"""
        while not gui_log_queue.empty():
            msg = gui_log_queue.get_nowait()
            
            # 【核心修改】：逐字检查文本，只在真正的“新行开头”插入时间戳
            for char in msg:
                # 如果处于行首，且当前字符不是换行符，说明新的一行文字开始了
                if self.at_start_of_line and char != '\n':
                    timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
                    self.log_text.insert(tk.END, timestamp)
                    self.at_start_of_line = False # 关闭标记，让后续流式的字紧随其后
                
                # 正常插入字符
                self.log_text.insert(tk.END, char)
                
                # 如果遇到换行符，重置行首标记，下一行字来的时候重新加时间戳
                if char == '\n':
                    self.at_start_of_line = True
            
            self.log_text.see(tk.END)
            
        # 【Bug修复】：将 after 移到 while 循环外面！
        # 原代码放在循环内，一旦队列为空，定时器就会彻底死掉，导致后续再也无法刷新界面
        self.root.after(50, self.poll_logs)

    def stop_pipeline(self):
        """【新增】暴露给UI急停按钮的点击回调事件"""
        if not self.is_running:
            messagebox.showwarning("提示", "当前没有正在运转的监听服务。")
            return
        self.stop_pipeline_sync()
        messagebox.showinfo("成功", "所有流水线队列与音频采集链已强制关停！")

    def stop_pipeline_sync(self):
        """【新增】同步急停核心实现：安全解除底层锁、取消异步任务、清洗外挂系统进程"""
        if not self.is_running:
            return
        self.is_running = False
        print("\n>>> [急停触发] 正在强行中断底层的异步流水线与硬件采集链...")
        
        # 1. 停用当前 Agent 内部生命周期标识，让常驻外部的 Loopback 采集线程安全退出
        if hasattr(self, 'current_agent') and self.current_agent:
            self.current_agent.is_active = False
            
        # 2. 线程安全地发送 Task 取消异常信号给 asyncio 循环并安全收尾
        if hasattr(self, 'current_loop') and self.current_loop and self.current_loop.is_running():
            try:
                def cancel_all_tasks():
                    for task in asyncio.all_tasks(self.current_loop):
                        task.cancel()
                    self.current_loop.stop()
                self.current_loop.call_soon_threadsafe(cancel_all_tasks)
            except Exception as e:
                print(f">>> 终止事件循环时遭遇异常: {e}")

        # 3. 彻底击杀外部系统关联进程链，防止 Windows 文件 IO 句柄悬空挂死
        import subprocess
        subprocess.run("taskkill /f /im scrcpy.exe /t", shell=True, capture_output=True)
        subprocess.run("taskkill /f /im ffmpeg.exe /t", shell=True, capture_output=True)
        
        self.start_btn.config(text="🔒 保存配置并开启监听", state="normal")
        self.stop_btn.config(state="disabled")
        print(">>> [清理完毕] 全局监听信道已关闭，已回归静默就绪状态。")

    def start_pipeline(self):
        """改造后的启动入口：支持检测运行状态自动热重启并应用新变动的配置参数"""
        if self.is_running:
            print(">>> [动态热更新] 检测到配置或模式被改动，正在自动重置当前流水线...")
            self.stop_pipeline_sync()
            time.sleep(0.4)  # 为底层驱动释放预留短暂的缓冲净空时间

        self.save_config()
        if not (self.config.get("gemini_api_key", "") or self.config.get("deepseek_api_key", "") or self.config.get("qwen_api_key", "")):
            messagebox.showerror("错误", "请输入有效的 API Key 才能启动服务！")
            return

        self.is_running = True
        self.start_btn.config(text="🔄 流水线运行中...")
        self.stop_btn.config(state="normal")

        self.loop_thread = threading.Thread(target=self.async_thread_main, daemon=True)
        self.loop_thread.start()

    def async_thread_main(self):
        """异步线程调度塔：挂载生命周期句柄以供急停定位"""
        async def main_pipeline():
            agent = pipe.InterviewAgent(config=self.config)
            self.current_agent = agent  # 【关键】将当前 agent 实例挂载到 GUI 对象上以控制内部状态
            print(">>> 正在启动图形端交互Pipeline...")
            await asyncio.gather(
                pipe.transcription_worker(agent),
                agent.filter_worker(),
                agent.ai_worker(),
                agent.tts_worker()
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.current_loop = loop  # 【关键】将事件循环句柄挂载到 GUI 对象，供主线程跨线程急停
        try:
            loop.run_until_complete(main_pipeline())
        except asyncio.CancelledError:
            print(">>> [Pipeline] 异步流管道已被上层指令成功安全终止。")
        except Exception as e:
            print(f">>> [Pipeline 运行时异常]: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass


if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n>>> 程序已手动停止")