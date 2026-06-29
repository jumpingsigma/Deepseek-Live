# -*- coding: utf-8 -*-
import os

# --- 核心配置及路径常数 ---
FFMPEG_BIN = "ffmpeg-win-x86_64-v7.1.exe"
SCRCPY_BIN = "scrcpy"
TEMP_WAV = "live_buffer.wav"
CONFIG_FILE = "config.json"

# ==================== 【仅在此处多抄两行 ChromaDB 的变量】 ====================
CHROMA_DB_PATH = "./chroma_db"
CHROMA_COLLECTION = "618testdb"
# =====================================================================

# =====================================================================
# --- 提示词及全局关键词配置 ---
# =====================================================================
SYSTEM_PROMPT = """你是一个ai面试助手，你会收到一段两人的对话文字流，一个是面试者一个是面试官，你需要提取面试官的问题帮助面试者回答问题，提取问题时请务必忠实于原话，不要进行任何润色与 改写，直接提取原话里的问题就好，提取文字流原话里的问题,如果这段话里没有什么问题则直接输出NULL,不要无中生有刻意制造问题如果这段文字流里有问题则务必以最快的速度给出参考答案。
输出格式：
问题：[提取出的问题]
答案：[专业解答]"""
KEYWORDS_TECH = ['crontab', 'mysqldump', 'xtrabackup', 'top', 'free', 'vmstat', 'mpstat', 'ss', 'netstat', 'jstack', 'strace', 'find', 'du', 'truncate', '慢查询日志', 'show processlist', 'desc', 'show index', 'show create table', 'mysqladmin', 'Prometheus', 'node_exporter', 'Alertmanager', 'exporter', 'redis_exporter', 'nginx_exporter', 'systemctl', 'ps', 'docker run', 'docker logs', 'docker exec', 'docker images', 'docker ps', 'docker build', 'docker push', 'docker pull', 'docker rm', 'docker rmi', 'docker save', 'docker load', 'docker volume', 'Kubernetes', 'Deployment', 'kubectl', 'Service', 'Ingress', 'ConfigMap', 'PersistentVolume', 'PersistentVolumeClaim', 'StorageClass']
KEYWORDS = ['什么', '怎么', '如何', '为什么', '讲讲', '解释', '了解', '怎么办', '能否', '是否', '有哪些', '哪些', '能不能', '可以吗', '会吗', '需不需要', '需要吗'] 
DISTANCE_THRESHOLD = 0.7  # 语义距离阈值，越小越严格
# =====================================================================

# ----------------- 以下全部字面照抄 0616config.py 的底层函数 -----------------

def _provider_key_name(provider: str) -> str:
    """根据大模型服务商返回对应的配置键名"""
    if provider == "gemini":
        return "gemini_api_key"
    if provider == "deepseek":
        return "deepseek_api_key"
    if provider == "qwen":
        return "qwen_api_key"
    return "gemini_api_key"


def _default_config():
    """返回默认的配置字典字典结构"""
    return {
        "api_key": "",  # 兼容旧配置
        "gemini_api_key": "",
        "deepseek_api_key": "",
        "qwen_api_key": "",
        "model_type": "gemini",
        "model_name": "gemini-2.5-flash",
        "embedding_model": "Chroma-Default",
        "listening_mode": "scrcpy系统声音(Android)"
    }


def _build_transcription_command(mode: str):
    """
    根据捕获源模式构建对应的音频流命令组合
    返回: (sc_proc_args or None, ffmpeg_cmd)
    """
    # Android 系统声音
    if mode == "scrcpy系统声音(Android)":
        sc_proc_args = [
            SCRCPY_BIN,
            "--no-video",
            "--no-window",          
            "--audio-codec=raw",
            f"--record={TEMP_WAV}",
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
            f"--record={TEMP_WAV}",
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
        f"--record={TEMP_WAV}",
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
