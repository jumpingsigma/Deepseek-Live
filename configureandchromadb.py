# -*- coding: utf-8 -*-
import os
import re
import uuid
import importlib.util
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import chromadb

class PipelineManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("高级配置与多向量库管理后台")
        self.root.geometry("950x700")
        
        # 基础常数与配置初始化
        self.db_path = "./chroma_db"
        self.collection_name = "tech_interview_knowledge"
        self.collection = None
        self.parsed_qa_data = []

        # 建立数据库连接
        self.init_chroma()

        # 建立多标签页
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.create_config_tab()
        self.create_import_tab()
        self.create_db_tab()

        # 初始化加载数据与同步界面
        self.load_config_to_ui()
        self.refresh_collection_list()
        self.refresh_db_view()

    def init_chroma(self):
        """初始化向量数据库连接并安全读取路径配置"""
        #cfg_path = "0616config.py"
        cfg_path = "deepseeklive-config.py" 
        if os.path.exists(cfg_path):
            try:
                spec = importlib.util.spec_from_file_location("adv_cfg", cfg_path)
                cfg = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cfg)
                self.db_path = getattr(cfg, "CHROMA_DB_PATH", "./chroma_db")
                self.collection_name = getattr(cfg, "CHROMA_COLLECTION", "tech_interview_knowledge")
            except Exception:
                pass
        try:
            self.chroma_client = chromadb.PersistentClient(path=self.db_path)
            self.collection = self.chroma_client.get_or_create_collection(name=self.collection_name)
        except Exception as e:
            messagebox.showerror("数据库错误", f"无法连接到 ChromaDB，请确保 Pipeline 主程序已关闭！\n错误信息: {e}")

    def update_import_target_label(self):
        """同步更新功能二界面的当前目标库提示"""
        self.lbl_target_db.config(text=f"当前数据注入目标库：【 {self.collection_name} 】", foreground="blue")

    # =====================================================================
    # TAB 1: 策略参数配置 (功能一)
    # =====================================================================
    def create_config_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" ⚙️ 策略参数配置 ")

        # 提示词配置区
        lbl_frame_prompt = ttk.LabelFrame(tab, text="AI 系统提示词 (SYSTEM_PROMPT)", padding=10)
        lbl_frame_prompt.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_prompt = tk.Text(lbl_frame_prompt, wrap="word", font=("Consolas", 10))
        self.txt_prompt.pack(fill="both", expand=True)

        # 基础关键词配置区
        lbl_frame_kw = ttk.LabelFrame(tab, text="常规触发关键词 (KEYWORDS，用英文逗号隔开)", padding=10)
        lbl_frame_kw.pack(fill="x", padx=10, pady=5)

        self.ent_keywords = ttk.Entry(lbl_frame_kw, font=("微软雅黑", 10))
        self.ent_keywords.pack(fill="x", expand=True)

        # 【新增】核心技术关键词配置区
        lbl_frame_kw_tech = ttk.LabelFrame(tab, text="技术核心关键词匹配规则 (KEYWORD_TECH，用英文逗号隔开)", padding=10)
        lbl_frame_kw_tech.pack(fill="x", padx=10, pady=5)

        self.ent_keywords_tech = ttk.Entry(lbl_frame_kw_tech, font=("微软雅黑", 10))
        self.ent_keywords_tech.pack(fill="x", expand=True)

        # 动作按钮
        btn_frame = ttk.Frame(tab, padding=5)
        btn_frame.pack(fill="x", side="bottom", padx=10, pady=5)

        ttk.Button(btn_frame, text="刷新/重置配置", command=self.load_config_to_ui).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="💾 保存并应用配置", command=self.save_config_from_ui).pack(side="right", padx=5)

    def load_config_to_ui(self):
        """动态加载 config.py 里的各项高级配置项"""
        #cfg_path = "0616config.py"
        cfg_path = "deepseeklive-config.py"
        if not os.path.exists(cfg_path):
            return
        try:
            spec = importlib.util.spec_from_file_location("adv_cfg", cfg_path)
            cfg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cfg)

            # 读取大模型提示词
            prompt_val = getattr(cfg, "SYSTEM_PROMPT", "")
            self.txt_prompt.delete("1.0", tk.END)
            self.txt_prompt.insert("1.0", prompt_val)

            # 读取常规关键词
            kw_val = getattr(cfg, "KEYWORDS", [])
            self.ent_keywords.delete(0, tk.END)
            self.ent_keywords.insert(0, ", ".join(kw_val))

            # 【新增】读取核心技术关键词规则
            kw_tech_val = getattr(cfg, "KEYWORDS_TECH", [])
            self.ent_keywords_tech.delete(0, tk.END)
            self.ent_keywords_tech.insert(0, ", ".join(kw_tech_val))
            
            # 同步更新本地库表记录名
            self.collection_name = getattr(cfg, "CHROMA_COLLECTION", "tech_interview_knowledge")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置文件失败: {e}")

    def save_config_from_ui(self):
        """【全量照抄 0616config.py 版】"""
        # 1. 从 UI 动态获取用户改过的值
        new_prompt = self.txt_prompt.get("1.0", tk.END).strip()
        
        raw_kws = self.ent_keywords.get().strip()
        keywords_list = [k.strip() for k in raw_kws.split(",") if k.strip()]
        
        raw_tech_kws = self.ent_keywords_tech.get().strip()
        keywords_tech_list = [k.strip() for k in raw_tech_kws.split(",") if k.strip()]

        db_path = getattr(self, "db_path", "./chroma_db")
        coll_name = getattr(self, "collection_name", "tech_interview_knowledge")

        # 2. 这里就是把 0616config.py 的内容完全抄一遍（唯独把大括号双写防报错）
        config_template = f"""# -*- coding: utf-8 -*-
import os

# --- 核心配置及路径常数 ---
FFMPEG_BIN = "ffmpeg-win-x86_64-v7.1.exe"
SCRCPY_BIN = "scrcpy"
TEMP_WAV = "live_buffer.wav"
CONFIG_FILE = "config.json"

# ==================== 【仅在此处多抄两行 ChromaDB 的变量】 ====================
CHROMA_DB_PATH = "{db_path}"
CHROMA_COLLECTION = "{coll_name}"
# =====================================================================

# =====================================================================
# --- 提示词及全局关键词配置 ---
# =====================================================================
SYSTEM_PROMPT = \"\"\"{new_prompt}\"\"\"
KEYWORDS_TECH = {keywords_tech_list}
KEYWORDS = {keywords_list}
DISTANCE_THRESHOLD = 1.2  # 语义距离阈值，越小越严格
# =====================================================================

# ----------------- 以下全部字面照抄 0616config.py 的底层函数 -----------------

def _provider_key_name(provider: str) -> str:
    \"\"\"根据大模型服务商返回对应的配置键名\"\"\"
    if provider == "gemini":
        return "gemini_api_key"
    if provider == "deepseek":
        return "deepseek_api_key"
    if provider == "qwen":
        return "qwen_api_key"
    return "gemini_api_key"


def _default_config():
    \"\"\"返回默认的配置字典字典结构\"\"\"
    return {{
        "api_key": "",  # 兼容旧配置
        "gemini_api_key": "",
        "deepseek_api_key": "",
        "qwen_api_key": "",
        "model_type": "gemini",
        "model_name": "gemini-2.5-flash",
        "embedding_model": "Chroma-Default",
        "listening_mode": "scrcpy系统声音(Android)"
    }}


def _build_transcription_command(mode: str):
    \"\"\"
    根据捕获源模式构建对应的音频流命令组合
    返回: (sc_proc_args or None, ffmpeg_cmd)
    \"\"\"
    # Android 系统声音
    if mode == "scrcpy系统声音(Android)":
        sc_proc_args = [
            SCRCPY_BIN,
            "--no-video",
            "--no-window",          
            "--audio-codec=raw",
            f"--record={{TEMP_WAV}}",
        ]
        ffmpeg_cmd = [
            FFMPEG_BIN,
            "-loglevel", "quiet",
            "-follow", "1",
            "-i", TEMP_WAV,
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "-",
        ]
        return sc_proc_args, ffmpeg_cmd

    # Android 麦克风
    if mode == "scrcpy麦克风(Android)":
        sc_proc_args = [
            SCRCPY_BIN,
            "--no-video",
            "--no-window",
            "--audio-source=mic",
            "--audio-codec=raw",
            "--no-audio-playback",
            f"--record={{TEMP_WAV}}",
        ]
        ffmpeg_cmd = [
            FFMPEG_BIN,
            "-loglevel", "quiet",
            "-follow", "1",
            "-i", TEMP_WAV,
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "-",
        ]
        return sc_proc_args, ffmpeg_cmd

    # PC 麦克风
    if mode == "本机麦克风(PC)":
        ffmpeg_cmd = [
            FFMPEG_BIN,
            "-loglevel", "quiet",
            "-f", "dshow",
            "-i", "audio=default",
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "-",
        ]
        return None, ffmpeg_cmd

    # PC 系统声音（WASAPI loopback）
    if mode == "本机系统声音(PC)":
        ffmpeg_cmd = [
            FFMPEG_BIN,
            "-loglevel", "quiet",
            "-f", "wasapi",
            "-i", "loopback_system=true",
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "-",
        ]
        return None, ffmpeg_cmd

    # 兜底：按 Android 系统声音处理
    sc_proc_args = [
        SCRCPY_BIN,
        "--no-video",
        "--no-window",
        "--audio-source=output",
        "--audio-codec=raw",
        "--no-audio-playback",
        f"--record={{TEMP_WAV}}",
    ]
    ffmpeg_cmd = [
        FFMPEG_BIN,
        "-loglevel", "quiet",
        "-follow", "1",
        "-i", TEMP_WAV,
        "-f", "s16le",
        "-ac", "1",
        "-ar", "16000",
        "-",
    ]
    return sc_proc_args, ffmpeg_cmd
"""

        # 3. 全量写回本地文件
        try:
            #with open("0616config.py", "w", encoding="utf-8") as f:
            with open("deepseeklive-config.py", "w", encoding="utf-8") as f:    
                f.write(config_template)
            messagebox.showinfo("成功", "高级策略参数已无损全量更新！")
        except Exception as e:
            messagebox.showerror("错误", f"全量覆写配置文件失败: {e}")


    # =====================================================================
    # TAB 2: 文本知识切分导入 (功能二)
    # =====================================================================
    def create_import_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 📂 文本知识切分导入 ")

        top_frame = ttk.Frame(tab, padding=10)
        top_frame.pack(fill="x")

        self.lbl_file_path = ttk.Label(top_frame, text="请先选择需要导入的题库/对话脚本文件 (.txt)", foreground="gray")
        self.lbl_file_path.pack(side="left", fill="x", expand=True)

        ttk.Button(top_frame, text="浏览文件", command=self.browse_and_parse_file).pack(side="right", padx=5)

        # 【新增】目标库动态展示行
        self.lbl_target_db = ttk.Label(tab, text="", font=("微软雅黑", 10, "bold"))
        self.lbl_target_db.pack(anchor="w", padx=10, pady=2)
        self.update_import_target_label()

        # 预览区列表
        lbl_preview = ttk.Label(tab, text="💡 智能切分结果预览（双击某行可查看完整文本）：", font=("微软雅黑", 9, "bold"))
        lbl_preview.pack(anchor="w", padx=10, pady=2)

        preview_frame = ttk.Frame(tab, padding=10)
        preview_frame.pack(fill="both", expand=True)

        self.tree_import = ttk.Treeview(preview_frame, columns=("index", "q", "a"), show="headings")
        self.tree_import.heading("index", text="序号")
        self.tree_import.heading("q", text="分析出的问题 (Document)")
        self.tree_import.heading("a", text="对应的参考答案 (Metadata)")
        
        self.tree_import.column("index", width=50, anchor="center")
        self.tree_import.column("q", width=400)
        self.tree_import.column("a", width=400)
        self.tree_import.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree_import.yview)
        sb.pack(fill="y", side="right")
        self.tree_import.configure(yscrollcommand=sb.set)
        self.tree_import.bind("<Double-1>", self.on_preview_double_click)

        # 提交按钮
        self.btn_submit_db = ttk.Button(tab, text="🚀 确认无误，将以上 QA 数据同步注入选中的知识库", state="disabled", command=self.submit_to_chromadb)
        self.btn_submit_db.pack(fill="x", padx=10, pady=10)

    def browse_and_parse_file(self):
        """选择文件并进行 QA 智能语义切分"""
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not file_path:
            return

        self.lbl_file_path.config(text=file_path, foreground="black")
        self.parsed_qa_data = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            for item in self.tree_import.get_children():
                self.tree_import.delete(item)

            lines = content.split("\n")
            curr_q, curr_a = "", ""

            for line in lines:
                line = line.strip()
                if not line: continue
                
                if line.startswith(("面试官：", "面试官:", "问题：", "问题:", "Q:", "q:")):
                    if curr_q and curr_a:
                        self.parsed_qa_data.append((curr_q, curr_a))
                        curr_q, curr_a = "", ""
                    curr_q = re.sub(r'^(面试官：|面试官:|问题：|问题:|Q:|q:)', '', line).strip()
                elif line.startswith(("运维工程师：", "运维工程师:", "答案：", "答案:", "A:", "a:")):
                    curr_a = re.sub(r'^(运维工程师：|运维工程师:|答案：|答案:|A:|a:)', '', line).strip()
                elif curr_q and not curr_a:
                    curr_a = line
                elif curr_q and curr_a:
                    curr_a += "\n" + line

            if curr_q and curr_a:
                self.parsed_qa_data.append((curr_q, curr_a))

            if not self.parsed_qa_data:
                messagebox.showwarning("切分失败", "未能从文本中解析出标准的 QA 格式，请检查前缀符号是否正确。")
                self.btn_submit_db.config(state="disabled")
                return

            for idx, (q, a) in enumerate(self.parsed_qa_data):
                self.tree_import.insert("", "end", values=(idx + 1, q, a))

            self.btn_submit_db.config(state="normal")
            messagebox.showinfo("解析成功", f"成功切分出 {len(self.parsed_qa_data)} 组核心 QA 知识！")
        except Exception as e:
            messagebox.showerror("文件读取错误", str(e))

    def on_preview_double_click(self, event):
        item = self.tree_import.selection()[0]
        vals = self.tree_import.item(item, "values")
        win = tk.Toplevel(self.root)
        win.title(f"QA 详情查看 - 序号 {vals[0]}")
        win.geometry("500x400")
        
        tk.Label(win, text="问题文本 (Document):", font=("微软雅黑", 9, "bold")).pack(anchor="w", padx=10, pady=5)
        t_q = tk.Text(win, height=5, wrap="word")
        t_q.insert("1.0", vals[1])
        t_q.pack(fill="x", padx=10)
        
        tk.Label(win, text="答案文本 (Metadata):", font=("微软雅黑", 9, "bold")).pack(anchor="w", padx=10, pady=5)
        t_a = tk.Text(win, height=12, wrap="word")
        t_a.insert("1.0", vals[2])
        t_a.pack(fill="both", expand=True, padx=10, pady=5)

    def submit_to_chromadb(self):
        """将解析完的数据导入当前切换到的 ChromaDB 库中"""
        if not self.collection or not self.parsed_qa_data:
            return
        try:
            documents, metadatas, ids = [], [], []
            for q, a in self.parsed_qa_data:
                documents.append(q)
                metadatas.append({"answer": a, "source": "user_import"})
                ids.append(f"qa_{uuid.uuid4().hex[:12]}")

            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
            messagebox.showinfo("注入成功", f"数据已成功注入到知识库表【{self.collection_name}】中！")
            self.refresh_db_view()
            self.notebook.select(2)
        except Exception as e:
            messagebox.showerror("写入数据库失败", str(e))


    # =====================================================================
    # TAB 3: 向量数据库管理 (功能三 - 多库管理与无缝切换)
    # =====================================================================
    def create_db_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 🗄️ 向量数据库管理 ")

        # 【核心新增】多知识库（库表）切换和管理面板
        multi_db_frame = ttk.LabelFrame(tab, text=" 🗃️ 知识库多库切换与管理 ", padding=10)
        multi_db_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(multi_db_frame, text="当前可选知识库列表:").pack(side="left", padx=5)
        
        self.col_cmb = ttk.Combobox(multi_db_frame, state="readonly", width=30, font=("微软雅黑", 9))
        self.col_cmb.pack(side="left", padx=5)
        self.col_cmb.bind("<<ComboboxSelected>>", self.on_collection_combo_changed)

        ttk.Button(multi_db_frame, text="➕ 新建知识库", command=self.create_new_collection_ui).pack(side="left", padx=5)
        ttk.Button(multi_db_frame, text="🗑️ 删除当前库", command=self.delete_current_collection_ui).pack(side="left", padx=5)

        # 搜索检索工具栏
        search_frame = ttk.LabelFrame(tab, text=" 🔍 当前库语义高精准检索测试 ", padding=10)
        search_frame.pack(fill="x", padx=10, pady=5)

        self.ent_search = ttk.Entry(search_frame, font=("微软雅黑", 10))
        self.ent_search.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_search.bind("<Return>", lambda e: self.query_db_view())

        ttk.Button(search_frame, text="检索测试", command=self.query_db_view).pack(side="left", padx=5)
        ttk.Button(search_frame, text="刷新/重置全部", command=self.refresh_db_view).pack(side="left", padx=5)

        # 数据库内容列表区
        table_frame = ttk.Frame(tab, padding=10)
        table_frame.pack(fill="both", expand=True)

        self.tree_db = ttk.Treeview(table_frame, columns=("id", "doc", "meta"), show="headings")
        self.tree_db.heading("id", text="唯一标识 (ID)")
        self.tree_db.heading("doc", text="问题特征句 (Document)")
        self.tree_db.heading("meta", text="存储内容 (Metadata)")
        
        self.tree_db.column("id", width=120, anchor="center")
        self.tree_db.column("doc", width=350)
        self.tree_db.column("meta", width=350)
        self.tree_db.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree_db.yview)
        sb.pack(fill="y", side="right")
        self.tree_db.configure(yscrollcommand=sb.set)

        # 底部操作工具栏
        bottom_frame = ttk.Frame(tab, padding=5)
        bottom_frame.pack(fill="x", side="bottom", padx=10, pady=5)

        self.lbl_db_count = ttk.Label(bottom_frame, text="总条数: 0 条", font=("微软雅黑", 9, "bold"))
        self.lbl_db_count.pack(side="left", padx=5)

        ttk.Button(bottom_frame, text="❌ 删除当前库中选中的记录", command=self.delete_selected_db_records).pack(side="right", padx=5)

    def refresh_collection_list(self):
        """拉取现有持久化目录中所有的库表，并在下拉框中展示"""
        try:
            cols = self.chroma_client.list_collections()
            # 兼容处理高低版本 chromadb 返回对象或字符串不同的情况
            names = [c.name if hasattr(c, "name") else str(c) for c in cols]
            
            if not names:
                names = ["tech_interview_knowledge"]
            
            self.col_cmb['values'] = names
            if self.collection_name in names:
                self.col_cmb.set(self.collection_name)
            else:
                self.col_cmb.set(names[0])
                self.collection_name = names[0]
        except Exception as e:
            print("扫描知识库列表失败:", e)

    def on_collection_combo_changed(self, event=None):
        """用户下拉切换库事件绑定"""
        selected = self.col_cmb.get()
        if not selected:
            return
        self.collection_name = selected
        self.collection = self.chroma_client.get_or_create_collection(name=self.collection_name)
        
        # 联动更新：同步刷新导入界面的目标提示标签、刷新库展示数据、同步写回配置文件
        self.update_import_target_label()
        self.refresh_db_view()
        self.save_config_from_ui()

    def create_new_collection_ui(self):
        """新建知识库弹窗控制"""
        new_name = simpledialog.askstring("新建知识库", "请输入新知识库表的英文字符名称(如: linux_rules):")
        if not new_name:
            return
        new_name = new_name.strip()
        if not re.match(r'^[a-zA-Z0-9_-]+$', new_name):
            messagebox.showerror("格式错误", "库名只能由字母、数字、下划线和连字符组成！")
            return
        try:
            self.collection = self.chroma_client.get_or_create_collection(name=new_name)
            self.collection_name = new_name
            messagebox.showinfo("成功", f"新知识库【{new_name}】创建成功并已自动切换！")
            
            self.refresh_collection_list()
            self.update_import_target_label()
            self.refresh_db_view()
            self.save_config_from_ui() # 实时将当前激活库锁定到 config 中
        except Exception as e:
            messagebox.showerror("新建失败", str(e))

    def delete_current_collection_ui(self):
        """删除当前选中的整个知识库"""
        target_del = self.collection_name
        if messagebox.askyesno("危险操作确认", f"你确定要永久删除整个知识库【 {target_del} 】及其内部全部数据吗？此操作不可逆！"):
            try:
                self.chroma_client.delete_collection(name=target_del)
                messagebox.showinfo("成功", f"知识库【{target_del}】已彻底被卸载抹除。")
                
                # 重归默认并刷新
                self.collection_name = "tech_interview_knowledge"
                self.collection = self.chroma_client.get_or_create_collection(name=self.collection_name)
                self.refresh_collection_list()
                self.update_import_target_label()
                self.refresh_db_view()
                self.save_config_from_ui()
            except Exception as e:
                messagebox.showerror("删除失败", str(e))

    def refresh_db_view(self):
        """全量拉取当前库的数据并渲染到表格上"""
        if self.collection is None:
            return
        for item in self.tree_db.get_children():
            self.tree_db.delete(item)
        try:
            res = self.collection.get()
            ids = res.get("ids", [])
            docs = res.get("documents", [])
            metas = res.get("metadatas", [])

            for i in range(len(ids)):
                ans_text = metas[i].get("answer", "") if metas[i] else ""
                self.tree_db.insert("", "end", values=(ids[i], docs[i], ans_text))

            self.lbl_db_count.config(text=f"当前库表【{self.collection_name}】内共有: {len(ids)} 条独立特征数据")
        except Exception as e:
            print("刷新库表视图失败:", e)

    def query_db_view(self):
        """对选中的向量库执行高精密匹配搜索"""
        q_text = self.ent_search.get().strip()
        if not q_text:
            self.refresh_db_view()
            return
        if self.collection is None:
            return
        for item in self.tree_db.get_children():
            self.tree_db.delete(item)
        try:
            res = self.collection.query(query_texts=[q_text], n_results=5)
            ids = res.get("ids", [[]])[0]
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            distances = res.get("distances", [[]])[0]

            for i in range(len(ids)):
                ans_text = metas[i].get("answer", "") if metas[i] else ""
                display_doc = f"[{distances[i]:.3f}] {docs[i]}"
                self.tree_db.insert("", "end", values=(ids[i], display_doc, ans_text))

            self.lbl_db_count.config(text=f"语义检索匹配完成，已为您返回与当前库最相似的 {len(ids)} 条数据")
        except Exception as e:
            messagebox.showerror("检索失败", str(e))

    def delete_selected_db_records(self):
        """硬删除选中的某条或多条具体记录"""
        selected_items = self.tree_db.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请先在下方列表中选择要抹除的数据行！")
            return
        if not messagebox.askyesno("确认删除", f"确定要永久从当前库【{self.collection_name}】中剔除这 {len(selected_items)} 条记录吗？"):
            return
        try:
            ids_to_del = [self.tree_db.item(item, "values")[0] for item in selected_items]
            self.collection.delete(ids=ids_to_del)
            messagebox.showinfo("删除成功", "所选记录已从当前库中注销。")
            self.refresh_db_view()
        except Exception as e:
            messagebox.showerror("删除失败", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = PipelineManagerApp(root)
    root.mainloop()