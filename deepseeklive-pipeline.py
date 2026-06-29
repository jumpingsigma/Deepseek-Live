import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")

# 强制重写二进制路径，使其指向打包好的 bin 文件夹
FFMPEG_BIN = os.path.join(BIN_DIR, "ffmpeg-win-x86_64-v7.1.exe")
SCRCPY_BIN = os.path.join(BIN_DIR, "scrcpy.exe")
TEMP_WAV = os.path.join(BASE_DIR, "live_buffer.wav")
# ==================== 请在 pipeline.py 顶部加上这三行 ====================
FFMPEG_BIN = "ffmpeg-win-x86_64-v7.1.exe"
SCRCPY_BIN = "scrcpy"
TEMP_WAV = "live_buffer.wav"
# =====================================================================
# -*- coding: utf-8 -*-
import asyncio
import subprocess
import numpy as np
import soundcard as sc
import warnings
import chromadb
import queue
import threading
import importlib.util
from faster_whisper import WhisperModel
from dotenv import load_dotenv

# --- 引入 LangChain 核心组件 ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # 【新增】引入历史占位符
from langchain_core.messages import HumanMessage, AIMessage               # 【新增】引入标准消息类

load_dotenv()

# --- 强行加载同目录下的配置文件 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
cfg_path = os.path.join(current_dir, "deepseeklive-config.py")
spec_cfg = importlib.util.spec_from_file_location("advanced_config", cfg_path)
cfg = importlib.util.module_from_spec(spec_cfg)
spec_cfg.loader.exec_module(cfg)

warnings.filterwarnings(
    "ignore",
    message="data discontinuity in recording"
)

audio_capture_queue = queue.Queue(maxsize=500)

# 本地化辅助逻辑，防范外部配置模块版本差异
def _local_provider_key_name(provider: str) -> str:
    if provider == "gemini": return "gemini_api_key"
    if provider == "deepseek": return "deepseek_api_key"
    if provider == "qwen": return "qwen_api_key"
    return "gemini_api_key"

def _build_transcription_command(mode: str):
    if mode == "scrcpy系统声音(Android)":
        sc_proc_args = [cfg.SCRCPY_BIN, "--no-video", "--no-window", "--audio-codec=raw", f"--record={cfg.TEMP_WAV}"]
        ffmpeg_cmd = [cfg.FFMPEG_BIN, "-loglevel", "quiet", "-follow", "1", "-i", cfg.TEMP_WAV, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        return sc_proc_args, ffmpeg_cmd
    if mode == "scrcpy麦克风(Android)":
        sc_proc_args = [cfg.SCRCPY_BIN, "--no-video", "--no-window", "--audio-source=mic", "--audio-codec=raw", "--no-audio-playback", f"--record={cfg.TEMP_WAV}"]
        ffmpeg_cmd = [cfg.FFMPEG_BIN, "-loglevel", "quiet", "-follow", "1", "-i", cfg.TEMP_WAV, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        return sc_proc_args, ffmpeg_cmd
    if mode == "本机麦克风(PC)":
        ffmpeg_cmd = [cfg.FFMPEG_BIN, "-loglevel", "quiet", "-f", "dshow", "-i", "audio=default", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        return None, ffmpeg_cmd
    if mode == "本机系统声音(PC)":
        ffmpeg_cmd = [cfg.FFMPEG_BIN, "-loglevel", "quiet", "-f", "wasapi", "-i", "loopback_system=true", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        return None, ffmpeg_cmd
    sc_proc_args = [cfg.SCRCPY_BIN, "--no-video", "--no-window", "--audio-source=output", "--audio-codec=raw", "--no-audio-playback", f"--record={cfg.TEMP_WAV}"]
    ffmpeg_cmd = [cfg.FFMPEG_BIN, "-loglevel", "quiet", "-follow", "1", "-i", cfg.TEMP_WAV, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    return sc_proc_args, ffmpeg_cmd


class InterviewAgent:
    # def __init__(self, config):
    #     self.config = config
    #     model_type = config.get("model_type", "gemini")
    #     model_name = config.get("model_name", "gemini-2.5-flash")
        
    #     # self.chroma_client = chromadb.PersistentClient(path="./chroma_db")
    #     # self.collection = self.chroma_client.get_or_create_collection(name="tech_interview_knowledge")
    #     db_path = getattr(cfg, "CHROMA_DB_PATH", "./chroma_db")
    #     coll_name = getattr(cfg, "CHROMA_COLLECTION", "tech_interview_knowledge")

    #     self.chroma_client = chromadb.PersistentClient(path=db_path)
    #     self.collection = self.chroma_client.get_or_create_collection(name=coll_name)
    def __init__(self, config):
        self.config = config
        self.is_active = True # 【新增】生命周期控制锁，用于防止重启动时外部 Native 线程重叠
        model_type = config.get("model_type", "gemini")
        model_name = config.get("model_name", "gemini-2.5-flash")
        
        # ------------------ 【核心修改点 1】 ------------------
        # 从静态组件 cfg 切换到动态传入的 config 字典
        db_path = getattr(cfg, "CHROMA_DB_PATH", "./chroma_db")
        coll_name = config.get("chroma_collection", getattr(cfg, "CHROMA_COLLECTION", "tech_interview_knowledge"))

        self.chroma_client = chromadb.PersistentClient(path=db_path)
        self.collection = self.chroma_client.get_or_create_collection(name=coll_name)
        # -----------------------------------------------------
        

        if model_type == "gemini":
            api_key = config.get("gemini_api_key", "") or config.get("api_key", "")
            self.llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0.2)
        elif model_type in ["deepseek", "qwen"]:
            from langchain_openai import ChatOpenAI
            api_key = config.get(_local_provider_key_name(model_type), "") or config.get("api_key", "")
            base_url = "https://api.deepseek.com/v1" if model_type == "deepseek" else "https://dashscope.aliyuncs.com/compatible-mode/v1"
            self.llm = ChatOpenAI(model=model_name, openai_api_key=api_key, openai_api_base=base_url, temperature=0.2)
        else:
            api_key = config.get("gemini_api_key", "") or config.get("api_key", "")
            self.llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0.2)

        # 【升级点 1】：初始化多轮对话记忆列表
        self.history = []

        # 【升级点 2】：利用 MessagesPlaceholder 将记忆无缝编入 Prompt 模板中
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", cfg.SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),  # 动态挂载历史交互
            ("human", "处理这段对话：{question_context}")
        ])
        self.chain = self.prompt | self.llm
        self.raw_queue = asyncio.Queue()
        self.ai_queue = asyncio.Queue()
        self.tts_queue = asyncio.Queue()
        self.buffer = ""
        self.last_triggered_text = ""

    async def filter_worker(self):
        import time
        print(">>> [线程2] 语义过滤器已就绪...")
        
        # 在 agent 内部初始化两个新变量（如果不想改 __init__ 也可以直接写在这里）
        if not hasattr(self, 'last_trigger_time'):
            self.last_trigger_time = 0
        self.cooldown_duration = 4.0  # 4秒防抖冷却期：触发一次后，4秒内不重复触发
        
        while True:
            text = await self.raw_queue.get()
            
            # ================== 1. 铁闸防御：AI正在说话，直接丢弃 ==================
            if getattr(self, 'is_speaking', False):
                self.raw_queue.task_done()
                continue

            # ================== 2. 噪音防御：过滤无意义的超短文本 ==================
            clean_text = text.strip()
            if len(clean_text) < 4:  # 类似 "对"、"好的"、"嗯" 直接过滤
                self.raw_queue.task_done()
                continue

            # ================== 3. 时间防抖：防止单句流式输出疯狂触发 ==================
            current_time = time.time()
            if current_time - self.last_trigger_time < self.cooldown_duration:
                # 处于冷却期内，我们把文本存入 buffer 积攒上下文，但不惊动 AI
                self.buffer += text
                self.raw_queue.task_done()
                continue

            # 满足基础条件，进入核心语义计算
            self.buffer += text
            loop = asyncio.get_event_loop()
            
            # 查询向量数据库
            results = await loop.run_in_executor(None, lambda: self.collection.query(query_texts=[clean_text], n_results=1))

            if results.get('distances') and len(results['distances']) > 0 and len(results['distances'][0]) > 0:
                raw_distance = results['distances'][0][0]
            else:
                raw_distance = 1.1
            # 动态获取当前最新的距离阈值
            current_threshold = self.config.get("distance_threshold", 1.0)
            # 动态获取当前最新的距离阈值与触发判定模式
            current_threshold = self.config.get("distance_threshold", 1.0)
            trigger_mode = self.config.get("trigger_mode", "RAG and 问句 and 技术关键词")
            
            # ================== 4. 【系统升级】四类可选复合判定矩阵 ==================
            is_question = any(kw in clean_text for kw in cfg.KEYWORDS)
            is_tech = any(kw in clean_text for kw in cfg.KEYWORDS_TECH)
            is_rag = (raw_distance < current_threshold)
            
            # 执行多分支策略评估
            if trigger_mode == "RAG and 问句 and 技术关键词":
                should_trigger = is_rag and is_question and is_tech
            elif trigger_mode == "RAG and 问句":
                should_trigger = is_rag and is_question
            elif trigger_mode == "问句":
                should_trigger = is_question
            elif trigger_mode == "技术关键词 and 问句":
                should_trigger = is_tech and is_question
            else:
                should_trigger = is_question and is_tech # 极端防呆兜底

            # Debug 日志，实时追踪过滤器的拦截轨迹
            print(f"\n[过滤器分析] 当前生效模式: 【{trigger_mode}】")
            print(f"  -> 输入文本: \"{clean_text}\"")
            print(f"  -> 特征匹配: 问句特征={is_question} | 技术词特征={is_tech}")
            print(f"  -> 知识库召回(RAG): {is_rag} (当前计算语义距离: {raw_distance:.3f} / 设定阈值: {current_threshold})")
            print(f"  -> [判定结果] 是否允许放行送入大模型: {should_trigger}")

            # ================== 5. 执行触发 ==================
            if should_trigger:
                if clean_text != self.last_triggered_text:
                    print(f"!!! 🎯 [判定成功] 捕获到有效问题，已送入LLM队列...")
                    
                    await self.ai_queue.put(self.buffer)
                    
                    # 更新状态锁
                    self.last_triggered_text = clean_text
                    self.last_trigger_time = current_time  # 刷新最近一次触发的时间戳
                    self.buffer = ""                       # 触发后清空缓冲区
                else:
                    print(f"  -> [拦截] 与上次触发文本完全一致，防重复拦截。")
            else:
                print(f"  -> [拦截] 未同时满足 问句特征 与 技术相关性，静默丢弃。")
                
            if len(self.buffer) > 300:
                self.buffer = self.buffer[-50:]
                
            self.raw_queue.task_done()

    async def ai_worker(self):
        print(">>> [线程3] AI 响应引擎已就绪...")
        while True:
            task = await self.ai_queue.get()
            
            # 解包任务字典，兼容原有可能存在的纯文本边界情况
            if isinstance(task, dict):
                question_context = task["question_context"]
                ref_doc = task.get("ref_doc", "")
            else:
                question_context = task
                ref_doc = ""
                
            print(f"\n[AI 捕捉到有效提问，正在分析...]")
            try:
                print("-" * 30)
                full_answer = ""
                
                # 【上下文拼装】：最大程度保持原有的 Prompt 链条结构，直接把重排好的参考资料融合输入 question_context 变量中
                llm_input_context = question_context
                if ref_doc:
                    llm_input_context = f"{question_context}\n\n【知识库最相近参考资料】:\n{ref_doc}"
                
                # 【升级点 3】：流式生成时传入 self.history 多轮记忆
                async for chunk in self.chain.astream({
                    "history": self.history,
                    "question_context": llm_input_context
                }):
                    if chunk.content:
                        print(chunk.content, end="", flush=True)
                        full_answer += chunk.content
                print("\n" * 2 + "-" * 30)

                # 【升级点 4】：如果大模型成功生成了有效回答，就把这一轮存入历史记忆
                if full_answer and "答案：" in full_answer:
                    # 将这一轮的对话片段和AI回答固化进 LangChain 消息历史
                    self.history.append(HumanMessage(content=f"上下文对话片段: {question_context}"))
                    self.history.append(AIMessage(content=full_answer))
                    
                    # 记忆窗口控制：只保留最近 4 轮交互（8 条记录），防止时间久了 token 暴增导致延迟增加
                    if len(self.history) > 6:
                        self.history = self.history[-6:]

                    speech_text = full_answer.split("答案：")[-1].strip()
                    if speech_text and speech_text != "NULL":
                        await self.tts_queue.put(speech_text)
            except Exception as e:
                if "429" in str(e):
                    print("\n[Quota Error] 触发频率限制，静默 15 秒...")
                    await asyncio.sleep(15)
                else:
                    print(f"\n[API Error]: {e}")
            finally:
                self.ai_queue.task_done()

    #0619 23：01，tts改动，尚未测试
    #async def tts_worker(self):
        import edge_tts
        import winsound
        print(">>> [线程4] Edge-TTS 语音引擎已就绪...")
        while True:
            text = await self.tts_queue.get()
            try:
                # ─── 【核心修复 3】开始播放前，强制加锁 ───
                self.is_speaking = True
                
                communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                await communicate.save("tts_temp.mp3")

                def play_audio():
                    subprocess.run(
                        [cfg.FFMPEG_BIN, "-y", "-i", "tts_temp.mp3", "tts_temp.wav"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    if os.path.exists("tts_temp.wav"):
                        winsound.PlaySound("tts_temp.wav", winsound.SND_FILENAME)

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, play_audio)
            except Exception as e:
                print(f"\n[TTS 错误]: {e}")
            finally:
                # ─── 【核心修复 4】无论播放成功还是报错，释放锁 ───
                self.is_speaking = False
                self.tts_queue.task_done()
    async def tts_worker(self):
        import edge_tts
        import winsound
        print(">>> [线程4] Edge-TTS 语音引擎已就绪...")
        while True:
            text = await self.tts_queue.get()
            try:
                # ─── 【核心修复】TTS 开始工作，立刻激活状态锁 ───
                self.is_speaking = True 
                
                communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                await communicate.save("tts_temp.mp3")

                def play_audio():
                    subprocess.run(
                        [cfg.FFMPEG_BIN, "-y", "-i", "tts_temp.mp3", "tts_temp.wav"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    if os.path.exists("tts_temp.wav"):
                        winsound.PlaySound("tts_temp.wav", winsound.SND_FILENAME)

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, play_audio)
            except Exception as e:
                print(f"\n[TTS 错误]: {e}")
            finally:
                # ─── 【核心修复】无论播放成功还是报错，释放状态锁 ───
                self.is_speaking = False
                self.tts_queue.task_done()


# 1. 调整函数签名，接收 agent 实例
def pc_loopback_capture_worker(agent):
    try:
        mics = sc.all_microphones(include_loopback=True)
        default_spk = sc.default_speaker()
        loopback_mic = None
        for mic in mics:
            if default_spk.name.lower() in mic.name.lower():
                loopback_mic = mic
                break
        if loopback_mic is None and mics:
            loopback_mic = mics[0]

        print(f">>> [采集线程] 使用 Loopback: {loopback_mic.name}")
        with loopback_mic.recorder(samplerate=16000, channels=1) as recorder:
            # 【核心修改点】将 while True 替换为生命周期检查
            # 一旦热更新或急停导致旧 agent 的 is_active 变为 False，该线程将自动彻底消亡释放硬件
            while getattr(agent, 'is_active', True):
                data = recorder.record(numframes=4096)
                if len(data.shape) > 1:
                    data = np.mean(data, axis=1)
                try:
                    audio_capture_queue.put_nowait(data.astype(np.float32))
                except queue.Full:
                    pass
        print(">>> [采集线程] 检测到上层热重载/急停指令，Loopback 录音线程已安全退出释放。")
    except Exception as e:
        print("[Loopback Error]", e)


async def transcription_worker(agent):
    print(">>> [线程1] Whisper 监听中...")
    loop = asyncio.get_event_loop()
    model = WhisperModel("turbo", device="cuda", compute_type="float16")
# async def transcription_worker(agent):
#     print(">>> [线程1] Whisper 监听中...")
#     loop = asyncio.get_event_loop()
#     model_path = os.path.join(BASE_DIR, "whisper_models", "turbo")
    # if not os.path.exists(model_path):
    #     print(f"[警告] 离线模型不存在，将尝试自动下载至: {model_path}")
    #     model = WhisperModel("turbo", device="cuda", compute_type="float16", download_root=os.path.join(BASE_DIR, "whisper_models"))
    # else:
    #     model = WhisperModel(model_path, device="cuda", compute_type="float16")    
    subprocess.run("taskkill /f /im scrcpy.exe /t", shell=True, capture_output=True)
    subprocess.run("taskkill /f /im ffmpeg.exe /t", shell=True, capture_output=True)
    if os.path.exists(TEMP_WAV):
        os.remove(TEMP_WAV)

    mode = agent.config.get("listening_mode", "scrcpy系统声音(Android)")

    # ==================== 模式 A：PC 系统声音 ====================
    if mode == "本机系统声音(PC)":
        # 【修改】将当前所在的 agent 实例作为实参传入
        threading.Thread(target=pc_loopback_capture_worker, args=(agent,), daemon=True).start()
        loop = asyncio.get_event_loop()
        audio_buffer = []
        silence_count = 0

        while True:
            chunk_f32 = await loop.run_in_executor(None, audio_capture_queue.get)

            # ─── 【核心修复 1】AI说话时，直接熔断并清空音频流，防止录入自身TTS ───
            if getattr(agent, 'is_speaking', False):
                audio_buffer = []
                silence_count = 0
                continue

            if np.max(np.abs(chunk_f32)) > 0.02:
                audio_buffer.append(chunk_f32)
                silence_count = 0
            else:
                silence_count += 1

            #if len(audio_buffer) >= 6 and (silence_count >= 2 or len(audio_buffer) >= 16): #在这修改每个块的字数
            if len(audio_buffer) >= 3 and (silence_count >= 2 or len(audio_buffer) >= 8):
                full_audio = np.concatenate(audio_buffer)
                audio_buffer = []
                silence_count = 0

                if len(full_audio) > 12000:
                    def run_whisper(audio):
                        segs, _ = model.transcribe(audio, language="zh", beam_size=3, initial_prompt=", ".join(cfg.KEYWORDS_TECH))
                        return list(segs)

                    segments = await loop.run_in_executor(None, run_whisper, full_audio)

                    for s in segments:
                        text = s.text.strip()
                        if text:
                            print(f"\n[实时]: {text}")
                            await agent.raw_queue.put(text)
        return

    # ==================== 模式 B：Android / scrcpy 模式 ====================
    subprocess.run("taskkill /f /im scrcpy.exe /t", shell=True, capture_output=True)
    subprocess.run("taskkill /f /im ffmpeg.exe /t", shell=True, capture_output=True)
    if os.path.exists("live_buffer.wav"):
        os.remove("live_buffer.wav")

    scrcpy_cmd = [SCRCPY_BIN, "--no-video", "--no-window", "--audio-codec=raw", "--record=live_buffer.wav"]
    sc_proc = subprocess.Popen(scrcpy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print(">>> [系统提示] 等待 scrcpy 写入音频流...")
    while not os.path.exists("live_buffer.wav") or os.path.getsize("live_buffer.wav") < 100:
        await asyncio.sleep(0.5)

    ffmpeg_cmd = [FFMPEG_BIN, "-loglevel", "quiet", "-follow", "1", "-i", "live_buffer.wav", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    ff_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=0)

    audio_buffer = []
    SILENCE_COUNT = 0
    loop = asyncio.get_event_loop()

    print(">>> [系统提示] 音频流已通过 file IO 建立，正在实时转录...")
    
    try:
        while True:
            raw_data = await loop.run_in_executor(None, ff_proc.stdout.read, 3200)
            if not raw_data:
                await asyncio.sleep(0.1)
                continue

            # ─── 【核心修复 2】AI说话时，直接熔断并清空音频流，防止录入自身TTS ───
            if getattr(agent, 'is_speaking', False):
                audio_buffer = []
                SILENCE_COUNT = 0
                continue

            chunk_f32 = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            max_amplitude = np.max(np.abs(chunk_f32))

            if max_amplitude > 0.001:
                print(".", end="", flush=True)
                audio_buffer.append(chunk_f32)
                SILENCE_COUNT = 0
            else:
                if len(audio_buffer) > 0:
                    SILENCE_COUNT += 1

            if len(audio_buffer) > 0 and (SILENCE_COUNT >= 10 or len(audio_buffer) >= 25):
                full_audio = np.concatenate(audio_buffer)
                audio_buffer = []
                SILENCE_COUNT = 0

                if len(full_audio) > 16000:
                    print(f"\n>>> [检测到有效语音] 正在送入 Whisper (长度: {len(full_audio)})...")
                    
                    def run_whisper(audio):
                        segs, _ = model.transcribe(audio, language="zh", beam_size=5)
                        return list(segs)

                    segments = await loop.run_in_executor(None, run_whisper, full_audio)
                    for s in segments:
                        text = s.text.strip()
                        if text:
                            print(f"\n[实时]: {text}")
                            await agent.raw_queue.put(text)
    finally:
        if ff_proc: ff_proc.terminate()
        if sc_proc: sc_proc.terminate()
#async def transcription_worker(agent):
    print(">>> [线程1] Whisper 监听中...")
    loop = asyncio.get_event_loop()
    model = WhisperModel("turbo", device="cuda", compute_type="float16")

    # model_path = os.path.join(BASE_DIR, "whisper_models", "turbo")
    # if not os.path.exists(model_path):
    #     print(f"[警告] 离线模型不存在，将尝试自动下载至: {model_path}")
    #     model = WhisperModel("turbo", device="cuda", compute_type="float16", download_root=os.path.join(BASE_DIR, "whisper_models"))
    # else:
    #     model = WhisperModel(model_path, device="cuda", compute_type="float16")
    
    subprocess.run("taskkill /f /im scrcpy.exe /t", shell=True, capture_output=True)
    subprocess.run("taskkill /f /im ffmpeg.exe /t", shell=True, capture_output=True)
    if os.path.exists(TEMP_WAV):
        os.remove(TEMP_WAV)

    mode = agent.config.get("listening_mode", "scrcpy系统声音(Android)")

    if mode == "本机系统声音(PC)":
        threading.Thread(target=pc_loopback_capture_worker, daemon=True).start()
        loop = asyncio.get_event_loop()
        audio_buffer = []
        silence_count = 0

        while True:
            chunk_f32 = await loop.run_in_executor(None, audio_capture_queue.get)

            if np.max(np.abs(chunk_f32)) > 0.02:
                audio_buffer.append(chunk_f32)
                silence_count = 0
            else:
                silence_count += 1

            if len(audio_buffer) >= 3 and (silence_count >= 2 or len(audio_buffer) >= 8):
                full_audio = np.concatenate(audio_buffer)
                audio_buffer = []
                silence_count = 0

                if len(full_audio) > 12000:
                    def run_whisper(audio):
                        segs, _ = model.transcribe(audio, language="zh", beam_size=3, initial_prompt=", ".join(cfg.KEYWORDS_TECH))
                        return list(segs)

                    segments = await loop.run_in_executor(None, run_whisper, full_audio)

                    for s in segments:
                        text = s.text.strip()
                        if text:
                            print(f"\n[实时]: {text}")
                            await agent.raw_queue.put(text)
        return

    subprocess.run("taskkill /f /im scrcpy.exe /t", shell=True, capture_output=True)
    subprocess.run("taskkill /f /im ffmpeg.exe /t", shell=True, capture_output=True)
    if os.path.exists("live_buffer.wav"):
        os.remove("live_buffer.wav")

    scrcpy_cmd = [SCRCPY_BIN, "--no-video", "--no-window", "--audio-codec=raw", "--record=live_buffer.wav"]
    sc_proc = subprocess.Popen(scrcpy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print(">>> [系统提示] 等待 scrcpy 写入音频流...")
    while not os.path.exists("live_buffer.wav") or os.path.getsize("live_buffer.wav") < 100:
        await asyncio.sleep(0.5)

    ffmpeg_cmd = [FFMPEG_BIN, "-loglevel", "quiet", "-follow", "1", "-i", "live_buffer.wav", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    ff_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=0)

    audio_buffer = []
    SILENCE_COUNT = 0
    loop = asyncio.get_event_loop()

    print(">>> [系统提示] 音频流已通过 file IO 建立，正在实时转录...")
    
    try:
        while True:
            raw_data = await loop.run_in_executor(None, ff_proc.stdout.read, 3200)
            if not raw_data:
                await asyncio.sleep(0.1)
                continue

            chunk_f32 = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            max_amplitude = np.max(np.abs(chunk_f32))

            if max_amplitude > 0.001:
                print(".", end="", flush=True)
                audio_buffer.append(chunk_f32)
                SILENCE_COUNT = 0
            else:
                if len(audio_buffer) > 0:
                    SILENCE_COUNT += 1

            if len(audio_buffer) > 0 and (SILENCE_COUNT >= 10 or len(audio_buffer) >= 25):
                full_audio = np.concatenate(audio_buffer)
                audio_buffer = []
                SILENCE_COUNT = 0

                if len(full_audio) > 16000:
                    print(f"\n>>> [检测到有效语音] 正在送入 Whisper (长度: {len(full_audio)})...")
                    
                    def run_whisper(audio):
                        segs, _ = model.transcribe(audio, language="zh", beam_size=5)
                        return list(segs)

                    segments = await loop.run_in_executor(None, run_whisper, full_audio)
                    for s in segments:
                        text = s.text.strip()
                        if text:
                            print(f"\n[实时]: {text}")
                            await agent.raw_queue.put(text)
    finally:
        if ff_proc: ff_proc.terminate()
        if sc_proc: sc_proc.terminate()