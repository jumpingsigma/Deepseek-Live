# Deepseek-Live
Its a real-time agent that listening your online conversation, get the high-value question,then send it to the LLM like deepseek/gemini/chatgpt.so you can chat with Deepseek like the Gemini Live. You can use it for some online meetings, online interview, even chatting online with your friends,any kinds of online Q&amp;A Session.
The ASR,TTS,RAG re running on your own PC, you need to prepare your document(Like your Linkein) and convert them into the Q&A form, Open your Chromadbconfiguration and load them so the Agent can understand what topic re u focusing on, so the program can filter out the fluff and chitchat in your conversations, and only extract the questions that actually require a response.
Or you can just set the RAG strategy to "Only Question", so the Agent would just ignore you loaded the chromadb or not, just send all the question sentence to your Online LLM.
All the keywords/prompt/LLM/threshold re editable.

This project is developed solely out of personal coding interest. It is named 'Deepseek-live' simply because Deepseek is representative in the field, and it has absolutely no affiliation with the official Deepseek team.
This project is shared for educational exchange only. The author is not responsible for how users utilize the code or the contexts in which it is applied.

这是一个实时对话的AI Agent，通过监听实时的声音或人类对话， 它会从中提取高价值问题并发送给在线大模型进行询问，返回一个答案。 支持Deepseek/gemini/chatgpt/qwen 的API，这样一来deepseek等在线大模型就会不停的给你参考意见，不需要点录音不需要打字，让本来没有实时互动模式的大模型也可以进行实时交互，就像gemini live一样。你可以把它用于以下的使用场景： 在线会议、在线面试、甚至是和你的朋友在线上闲聊，任何形式的线上语音交流它都可以派上用场。
ASR文字转写、TTS语音转换、RAG检索都在你的本机进行，只有LLM是通过api进行在线调用，如果是面试、在线会议等需要一些专业意见的领域那么你需要把你的简历、准备文档、项目说明和其他的一些相关材料提前丢给LLM转化为成百上千个Q&A组成的文档，再把它们导入到你的向量数据库里（这个过程可以由LLM本身代劳，我在项目文件夹里给出了默认的模板和提示词），这样一来程序就会通过RAG来筛选你文本里提到的内容并把它们作为参考资料一并提交给在线大模型，来过滤掉一些没必要回答或者与专业范围不符的问题like:"你几几年生人"/“今天吃了什么”/“大家都到齐了吗”。只有同时符合问句、技术关键词、RAG相关性的问题才会被提交给大模型。
或者你可以把问题筛选模式设置为“仅问句”，那么它就会把所有类似疑问句的问题提交到大模型并返回答案，把答案通过TTS模拟人声朗读。
所有的关键词/提示词/大模型厂商/具体名称/RAG判定阈值 都是在图形化界面上直观可见、可编辑的。

本项目纯粹出于个人兴趣开发。命名为 Deepseek-live，仅因为通过AI Agent与传统模型进行实时交互方面 Deepseek 具有代表性，与 Deepseek 官方团队绝无任何隶属关系。
本人分享这个项目只是为了学习和交流技术。使用者拿它干嘛、如何改造、在什么地方用，与本人完全没有任何关系。
